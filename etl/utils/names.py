"""Normalização e indexação de nomes de parlamentares — sem correspondência por substring."""

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Set

_HONORIFICS = [
    r"\bsenador\b",
    r"\bsenadora\b",
    r"\bdeputado\b",
    r"\bdeputada\b",
    r"\bfederal\b",
    r"\bestadual\b",
    r"\bdr\b",
    r"\bdra\b",
    r"\bdoutor\b",
    r"\bdoutora\b",
    r"\bprofessor\b",
    r"\bprofessora\b",
    r"\bprof\b",
    r"\bpastor\b",
    r"\bpastora\b",
    r"\bbispo\b",
    r"\bdelegado\b",
    r"\bdelegada\b",
    r"\bcoronel\b",
    r"\bcapitao\b",
    r"\bsargento\b",
    r"\bpadre\b",
]

NON_PERSON_AUTHORS = frozenset(
    {"poder executivo", "comissao parlamentares", "comissao", "mesa diretora", "senado federal"}
)


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ASCII", "ignore").decode("utf-8")


def normalize_name_tokens(text: Optional[str]) -> str:
    """Remove acentos, siglas entre parênteses/colchetes, títulos honoríficos e pontuação."""
    if not text:
        return ""
    s = strip_accents(text).lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    for pattern in _HONORIFICS:
        s = re.sub(pattern, " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(w for w in s.split() if w)


def normalize_plain(text: Optional[str]) -> str:
    """Normalização leve (acentos, caixa, pontuação), preservando honoríficos."""
    if not text:
        return ""
    s = strip_accents(text).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return " ".join(s.split())


def first_signatory(author: Optional[str]) -> str:
    """Primeiro signatário de uma lista 'A, B; C'."""
    if not author:
        return ""
    return re.split(r"[,;]", author)[0].strip()


class NameIndex:
    """
    Índice nome normalizado -> ids. Só devolve resultado quando o nome é INEQUÍVOCO:
    nomes repetidos (homônimos) retornam None em vez de escolher o primeiro.
    """

    def __init__(self, entries: Iterable[tuple]):
        """entries: iterável de (id, nome). Nomes vazios são ignorados."""
        self._by_name: Dict[str, Set[object]] = {}
        for ident, name in entries:
            key = normalize_name_tokens(name)
            if not key:
                continue
            self._by_name.setdefault(key, set()).add(ident)

    def __len__(self) -> int:
        return len(self._by_name)

    def lookup(self, name: Optional[str]) -> Optional[object]:
        key = normalize_name_tokens(name)
        if not key:
            return None
        ids = self._by_name.get(key)
        if ids and len(ids) == 1:
            return next(iter(ids))
        return None

    def is_ambiguous(self, name: Optional[str]) -> bool:
        ids = self._by_name.get(normalize_name_tokens(name))
        return bool(ids) and len(ids) > 1


def build_unique_name_map(pairs: Iterable[tuple]) -> Dict[str, object]:
    """Mapa nome normalizado -> id apenas para nomes que aparecem uma única vez."""
    seen: Dict[str, List[object]] = {}
    for ident, name in pairs:
        key = normalize_name_tokens(name)
        if key:
            seen.setdefault(key, []).append(ident)
    return {k: v[0] for k, v in seen.items() if len(set(v)) == 1}
