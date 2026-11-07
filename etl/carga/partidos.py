"""Partidos: o catálogo vive em `ref.partido_semente` (banco); o arquivo só acrescenta as siglas que as fontes citam."""

from pathlib import Path
from typing import Any, Iterable, List, Set

from etl.carga.base import Resultado, contagem_de, escalar, executar_sql, tabela_temporaria
from etl.utils.datafiles import load_deputados, load_json, load_senadores


def siglas_das_fontes(data_dir: Path) -> List[str]:
    """Siglas citadas nos arquivos de deputados, senadores e presidentes."""
    data_dir = Path(data_dir)
    brutas: List[Any] = [d.get("partido_sigla") for d in load_deputados(data_dir)]
    brutas += [s.get("partido_sigla") for s in load_senadores(data_dir)]
    brutas += [p.get("partido_sigla") for p in (load_json(data_dir / "presidentes_historico.json", []) or [])]
    return sorted({s.strip() for s in brutas if isinstance(s, str) and s.strip()})


def carregar_partidos(cursor: Any, siglas: Iterable[str]) -> Resultado:
    lista: Set[str] = {s for s in siglas if s}
    tabela_temporaria(cursor, "_in_sigla", {"sigla": "text"}, ([s] for s in sorted(lista)))
    executar_sql(cursor, "partidos")
    gravados = int(escalar(cursor, "SELECT count(*) FROM core.partido"))
    return Resultado(contagem_de(gravados, {}), extras={"partidos": gravados, "siglas_citadas": len(lista)})
