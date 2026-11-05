"""
Etapa 1 da carga do staging: os partidos políticos (`stg.partidos_politicos`).

`montar_partidos` é puro (lê só os arquivos processados e os dados curados de `dados_partidos`) e devolve uma linha por
partido, na ordem em que a carga a processa. `gravar_partidos` despeja essas linhas por `COPY` numa tabela temporária e
faz o upsert no staging, na transação do cursor recebido. O `id` de um partido que já está no staging nunca muda: é ele
que a fusão usa como `uid` público em `core.partido`.
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.pipelines.dados_partidos import (
    PARTIDOS_BASE,
    PARTY_LOGOS_MAP,
    PARTY_METADATA_MAP,
    PARTY_SPECTRUM_MAP,
    nome_do_partido,
)
from etl.utils.copia import copiar_linhas
from etl.utils.datafiles import load_deputados, load_json, load_senadores

logger = logging.getLogger("StagingPartidos")

COLUNAS = ["sigla", "nome", "espectro", "ideologia", "lema", "numero", "logo_url"]


def _siglas_das_fontes(data_dir: Path) -> List[Optional[str]]:
    """Siglas citadas nas fontes, inclusive partidos extintos que aparecem só em filiações históricas."""
    siglas: List[Optional[str]] = [d.get("partido_sigla") for d in load_deputados(data_dir)]
    siglas += [s.get("partido_sigla") for s in load_senadores(data_dir)]
    siglas += [f.get("partido_sigla") for f in (load_json(Path(data_dir) / "filiacoes_partidarias.json", []) or [])]
    siglas += [p.get("partido_sigla") for p in (load_json(Path(data_dir) / "presidentes_historico.json", []) or [])]
    return siglas


def montar_partidos(data_dir: Path) -> List[Dict[str, Any]]:
    """
    Os partidos da carga: os de `PARTIDOS_BASE`, os citados nas fontes e os que só têm metadado curado. Partido sem
    metadado curado fica sem ideologia, lema e espectro (nunca texto inventado). Um número eleitoral já usado por outro
    partido da lista não se repete: o primeiro a chegar fica com ele.
    """
    a_inserir = dict(PARTIDOS_BASE)
    conhecidas = {sigla.upper() for sigla in a_inserir}
    for sigla in _siglas_das_fontes(data_dir):
        if sigla and isinstance(sigla, str) and sigla.upper() not in conhecidas:
            a_inserir[sigla] = nome_do_partido(sigla)
            conhecidas.add(sigla.upper())
    existentes = {sigla.upper(): sigla for sigla in a_inserir}
    for sigla in PARTY_METADATA_MAP:  # chaves já em maiúsculas
        if sigla not in existentes and sigla != "PODEMOS":
            a_inserir[sigla] = f"Partido {sigla}"
            existentes[sigla] = sigla

    partidos: List[Dict[str, Any]] = []
    numeros_usados: Dict[int, str] = {}
    for sigla, nome in a_inserir.items():
        if sigla.upper() == "PODEMOS" and "PODE" in existentes:
            continue
        meta = PARTY_METADATA_MAP.get(sigla.upper(), {})
        numero = meta.get("numero")
        if numero and numeros_usados.get(numero, sigla).upper() != sigla.upper():
            numero = None  # já é de outro partido: não repetir (evita violar a unicidade)
        if numero:
            numeros_usados.setdefault(numero, sigla)
        partidos.append(
            {
                "sigla": sigla,
                "nome": nome,
                "espectro": meta.get("espectro") or PARTY_SPECTRUM_MAP.get(sigla.upper()),
                "ideologia": meta.get("ideologia"),
                "lema": meta.get("lema"),
                "numero": numero,
                "logo_url": meta.get("logo_url") or PARTY_LOGOS_MAP.get(sigla.upper()),
            }
        )
    return partidos


def gravar_partidos(cursor: Any, partidos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Upsert dos partidos em `stg.partidos_politicos` pela sigla sem distinguir maiúsculas. Partido novo recebe um `id`
    novo; o que já existe mantém o `id` e só ganha os metadados que a carga traz (valor ausente não apaga o que já
    estava, e o nome completo não muda); a linha que nada mudaria não é tocada (sem trava nem `updated_at` novo numa
    recarga idempotente). Número eleitoral que outro partido do staging já usa é descartado. Devolve
    `{sigla: id}` dos partidos da lista, com a sigla como veio e em maiúsculas.
    """
    cursor.execute(
        "CREATE TEMP TABLE _partido (sigla text, nome text, espectro text, ideologia text, lema text, numero int, "
        "logo_url text) ON COMMIT DROP"
    )
    copiar_linhas(cursor, "_partido", COLUNAS, ([p[c] for c in COLUNAS] for p in partidos))
    cursor.execute(
        "UPDATE _partido p SET numero = NULL WHERE numero IS NOT NULL AND EXISTS (SELECT 1 FROM stg.partidos_politicos o "
        'WHERE o."numeroEleitoral" = p.numero AND upper(o.sigla) <> upper(p.sigla))'
    )
    cursor.execute(
        """
        UPDATE stg.partidos_politicos s SET
            "espectroPolitico" = coalesce(p.espectro::espectropoliticoenum, s."espectroPolitico"),
            ideologia = coalesce(p.ideologia, s.ideologia), lema = coalesce(p.lema, s.lema),
            "logoUrl" = coalesce(p.logo_url, s."logoUrl"),
            "numeroEleitoral" = coalesce(p.numero, s."numeroEleitoral"), updated_at = now()
        FROM _partido p WHERE upper(s.sigla) = upper(p.sigla)
          AND (coalesce(p.espectro::espectropoliticoenum, s."espectroPolitico"),
               coalesce(p.ideologia, s.ideologia), coalesce(p.lema, s.lema), coalesce(p.logo_url, s."logoUrl"),
               coalesce(p.numero, s."numeroEleitoral"))
              IS DISTINCT FROM (s."espectroPolitico", s.ideologia, s.lema, s."logoUrl", s."numeroEleitoral")
        """
    )
    cursor.execute(
        """
        INSERT INTO stg.partidos_politicos (id, sigla, "nomeCompleto", "espectroPolitico", ideologia, lema,
                                            "numeroEleitoral", "logoUrl")
        SELECT gen_random_uuid(), p.sigla, p.nome, p.espectro::espectropoliticoenum, p.ideologia, p.lema, p.numero,
               p.logo_url
        FROM _partido p WHERE NOT EXISTS (SELECT 1 FROM stg.partidos_politicos s WHERE upper(s.sigla) = upper(p.sigla))
        """
    )
    cursor.execute(
        "SELECT p.sigla, s.id FROM _partido p JOIN stg.partidos_politicos s ON upper(s.sigla) = upper(p.sigla)"
    )
    mapa: Dict[str, Any] = {}
    for sigla, identificador in cursor.fetchall():
        identificador = uuid.UUID(str(identificador))
        mapa[sigla] = identificador
        mapa.setdefault(sigla.upper(), identificador)
    logger.info("-> %d partidos mapeados/carregados.", len({v for v in mapa.values()}))
    return mapa
