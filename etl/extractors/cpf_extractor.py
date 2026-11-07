"""
Gera `cpf_identificadores.json`: para cada parlamentar o HMAC do CPF (nunca o CPF), vindo de duas fontes oficiais.

1. Câmara: o detalhe `/deputados/{id}` traz o CPF (deputados atuais e ex-deputados), via `IdentidadesParlamentares`.
2. TSE: `consulta_cand` (1998-2022) traz o CPF de todo candidato. O Senado não publica CPF, então o senador (e o presidente)
   é ligado ao candidato pelo nome civil completo + data de nascimento, e só quando esse par aponta para um único CPF.
O arquivo só tem identificadores oficiais da pessoa e o HMAC; o carregador liga ao cadastro pelo SQL.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.senadores_basicos_extractor import ler_senadores_basicos
from etl.extractors.tse_core import TSE_RAW_DIR, ler_candidatos
from etl.utils.cpf import chave_configurada, identificador_cpf
from etl.utils.datafiles import load_deputados, load_json, load_senadores
from etl.utils.identidades import IdentidadesParlamentares, parse_date
from etl.utils.io_utils import atomic_write_json
from etl.utils.names import normalize_plain

logger = logging.getLogger("CpfExtractor")

SAIDA = "cpf_identificadores.json"
ANOS_COM_CPF = (1998, 2002, 2006, 2010, 2014, 2018, 2022)  # 1994 e 2024 não trazem CPF utilizável


def indice_do_tse(anos: Iterable[int] = ANOS_COM_CPF, raw_dir: Path = TSE_RAW_DIR) -> Dict[Tuple[str, Any], Set[str]]:
    """(nome civil normalizado, nascimento) -> CPFs dos candidatos com esse par, de todos os anos."""
    indice: Dict[Tuple[str, Any], Set[str]] = {}
    for ano in anos:
        arquivo = Path(raw_dir) / "consulta_cand" / f"consulta_cand_{ano}.zip"
        if not arquivo.exists():
            arquivo = Path(raw_dir) / f"consulta_cand_{ano}.zip"
        if not arquivo.exists():
            logger.warning("consulta_cand %s não baixado: pulado.", ano)
            continue
        df = ler_candidatos(arquivo)
        for civil, nasc, cpf in zip(df["_civil"], df["_nasc"], df["_cpf"]):
            if civil and nasc and isinstance(cpf, str) and cpf:
                indice.setdefault((civil, nasc), set()).add(cpf)
    return indice


def _por_nome_e_nascimento(indice: Dict[Tuple[str, Any], Set[str]], nome: Any, nascimento: Any) -> Optional[str]:
    nasc, civil = parse_date(nascimento), normalize_plain(str(nome or ""))
    cpfs = indice.get((civil, nasc)) if civil and nasc else None
    return next(iter(cpfs)) if cpfs and len(cpfs) == 1 else None  # par ambíguo: melhor omitir do que errar a pessoa


def gerar(
    processed_dir: Path = PROCESSED_DATA_DIR,
    raw_dir: Path = RAW_DATA_DIR,
    consultar_apis: bool = True,
    indice: Optional[Dict[Tuple[str, Any], Set[str]]] = None,
    identidades: Optional[IdentidadesParlamentares] = None,
) -> Dict[str, Any]:
    if not chave_configurada():
        logger.warning(
            "CPF_HMAC_KEY não configurada: identificadores de CPF não gerados (arquivo existente preservado)."
        )
        return {"gerados": 0, "motivo": "sem_chave"}
    processed_dir = Path(processed_dir)
    deputados = load_deputados(processed_dir)
    senadores = load_senadores(processed_dir)
    anteriores = load_json(processed_dir / "parlamentares_legislaturas_anteriores.json", {}) or {}
    presidentes = load_json(processed_dir / "presidentes_historico.json", []) or []
    ex_deputados = [d for d in anteriores.get("deputados") or [] if isinstance(d, dict)]
    ex_senadores = [s for s in anteriores.get("senadores") or [] if isinstance(s, dict)]

    camara_ids = sorted({int(d["camara_id"]) for d in deputados + ex_deputados if d.get("camara_id")})
    identidades = identidades or IdentidadesParlamentares(raw_dir, offline=not consultar_apis)
    identidades.enrich(camara_ids, [])
    indice = indice if indice is not None else indice_do_tse()

    saida: List[Dict[str, Any]] = []
    vistos: Set[Tuple[str, str]] = set()

    def anotar(id_tipo: str, id_valor: Any, cpf: Optional[str], origem: str) -> None:
        h = identificador_cpf(cpf)
        if h and (id_tipo, str(id_valor)) not in vistos:
            vistos.add((id_tipo, str(id_valor)))
            saida.append({"id_tipo": id_tipo, "id_valor": str(id_valor), "cpf_hmac": h, "origem": origem})

    for cid in camara_ids:
        anotar("CAMARA_ID", cid, (identidades.get(f"camara:{cid}") or {}).get("cpf"), "CAMARA_API")
    for s in senadores + ex_senadores:
        if s.get("senado_id"):
            anotar(
                "SENADO_ID",
                s["senado_id"],
                _por_nome_e_nascimento(indice, s.get("nome_civil"), s.get("data_nascimento")),
                "TSE",
            )
    for s in ler_senadores_basicos(processed_dir):  # quem só aparece em votos e presença do Senado
        anotar(
            "SENADO_ID",
            s["senado_id"],
            _por_nome_e_nascimento(indice, s.get("nome_civil"), s.get("data_nascimento")),
            "TSE",
        )
    for p in presidentes:
        nome = p.get("nome_civil")
        if nome:
            anotar(
                "CURADORIA_ID", f"pessoa:{nome}", _por_nome_e_nascimento(indice, nome, p.get("data_nascimento")), "TSE"
            )

    if not saida:
        logger.error("Nenhum identificador de CPF gerado: arquivo existente preservado.")
        return {"gerados": 0, "motivo": "vazio"}
    atomic_write_json(processed_dir / SAIDA, saida, indent=None)
    por_tipo: Dict[str, int] = {}
    for item in saida:
        por_tipo[item["id_tipo"]] = por_tipo.get(item["id_tipo"], 0) + 1
    logger.info("Identificadores de CPF (HMAC): %s", por_tipo)
    return {"gerados": len(saida), **por_tipo}
