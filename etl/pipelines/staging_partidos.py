"""
Os partidos políticos da carga (`stg.curadoria_partido`).

`montar_partidos` é puro (lê só os arquivos processados e os dados curados de `dados_partidos`) e devolve uma linha por
partido, na ordem em que a carga a processa; `etl.pipelines.planas_cadastro` a despeja na tabela plana. Quem junta essas linhas
aos partidos de `core.partido` (o `uid` público nunca muda) é a função SQL `etl.preparar_cadastro`.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.pipelines.dados_partidos import (
    PARTIDOS_BASE,
    PARTY_LOGOS_MAP,
    PARTY_METADATA_MAP,
    PARTY_SPECTRUM_MAP,
    nome_do_partido,
)
from etl.utils.datafiles import load_deputados, load_json, load_senadores

logger = logging.getLogger("StagingPartidos")


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
