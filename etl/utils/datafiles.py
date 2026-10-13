"""Leitura dos arquivos processados, sempre deduplicando parlamentares por identificador oficial."""

import json
from pathlib import Path
from typing import Any, Dict, List, Union

PathLike = Union[str, Path]


def load_json(path: PathLike, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dedupe_by_key(records: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Um registro por `key`; campos não nulos de ocorrências posteriores completam os anteriores."""
    por_id: Dict[Any, Dict[str, Any]] = {}
    for rec in records:
        ident = rec.get(key)
        if ident is None:
            continue
        atual = por_id.get(ident, {})
        por_id[ident] = {**atual, **{k: v for k, v in rec.items() if v is not None}}
    return list(por_id.values())


def load_deputados(data_dir: PathLike) -> List[Dict[str, Any]]:
    """O arquivo legado tem repetições do mesmo deputado (882 registros para 648 ids): deduplica."""
    return dedupe_by_key(load_json(Path(data_dir) / "deputados_camara.json", []) or [], "camara_id")


def load_senadores(data_dir: PathLike) -> List[Dict[str, Any]]:
    return dedupe_by_key(load_json(Path(data_dir) / "senadores_senado.json", []) or [], "senado_id")
