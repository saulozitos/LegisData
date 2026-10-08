"""Proveniência dos dados: separa dado oficial de dado sintético/estimado e impede mistura silenciosa."""

from typing import Any, Dict, Optional

SYNTHETIC_TAG = "[DADO SINTÉTICO] "
SYNTHETIC_CODE_PREFIX = "SINT-"


def mark_synthetic(record: Dict[str, Any], fonte: str = "Gerado pelo LegisData (não oficial)") -> Dict[str, Any]:
    """Marca o registro como sintético/estimado, de forma explícita e auditável."""
    record["is_synthetic"] = True
    record["fonte"] = fonte
    return record


def mark_official(record: Dict[str, Any], fonte: str) -> Dict[str, Any]:
    record["is_synthetic"] = False
    record["fonte"] = fonte
    return record


def is_synthetic(record: Dict[str, Any]) -> bool:
    return bool(record.get("is_synthetic") or record.get("is_estimate"))


def has_provenance(record: Dict[str, Any]) -> bool:
    """Registro 'legado' (gerado antes da rastreabilidade) não traz `fonte`; não é confiável por padrão."""
    return bool(record.get("fonte")) and "is_synthetic" in record


def is_trusted(record: Dict[str, Any]) -> bool:
    return has_provenance(record) and not is_synthetic(record)


def tag_text(text: Optional[str]) -> str:
    return f"{SYNTHETIC_TAG}{text or ''}".strip()
