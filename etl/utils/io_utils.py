"""Escrita atômica e validação de saídas: nunca sobrescreve um arquivo bom com resultado vazio."""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional, Union

logger = logging.getLogger("IOUtils")

PathLike = Union[str, Path]


class EmptyResultError(RuntimeError):
    """Levantada quando um extractor devolve um resultado vazio e o arquivo existente seria destruído."""


def atomic_write_bytes(path: PathLike, data: bytes) -> Path:
    """Grava em arquivo temporário no mesmo diretório e troca com os.replace (atômico no POSIX)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        # mkstemp cria o arquivo com 0600; os dados processados precisam ser legíveis por outros usuários
        # (ex.: o contêiner do backend, que monta etl/data como somente leitura).
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp_name, 0o666 & ~umask)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    return target


def atomic_write_text(path: PathLike, text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: PathLike, obj: Any, indent: Optional[int] = 2, **dump_kwargs) -> Path:
    dump_kwargs.setdefault("ensure_ascii", False)
    return atomic_write_text(path, json.dumps(obj, indent=indent, **dump_kwargs))


def is_empty_payload(obj: Any) -> bool:
    """True para None, coleções vazias e DataFrames vazios."""
    if obj is None:
        return True
    empty_attr = getattr(obj, "empty", None)
    if isinstance(empty_attr, bool):
        return empty_attr
    try:
        return len(obj) == 0
    except TypeError:
        return False


def write_json_if_valid(
    path: PathLike,
    obj: Any,
    validator: Optional[Callable[[Any], bool]] = None,
    indent: Optional[int] = 2,
    label: Optional[str] = None,
) -> bool:
    """
    Grava `obj` somente se for válido (não vazio e aprovado por `validator`).
    Se inválido e já existir arquivo anterior, preserva o anterior e devolve False.
    Se inválido e não existir arquivo, também não cria nada (nunca persiste lista vazia como se fosse dado).
    """
    name = label or Path(path).name
    valid = not is_empty_payload(obj) and (validator(obj) if validator else True)
    if not valid:
        previous = "preservado o arquivo anterior" if Path(path).exists() else "nenhum arquivo criado"
        logger.error("Resultado vazio/inválido para %s: %s.", name, previous)
        return False
    atomic_write_json(path, obj, indent=indent)
    return True
