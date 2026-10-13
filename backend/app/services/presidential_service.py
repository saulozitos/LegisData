"""
Serviço Unificado de Mandatos Presidenciais (Single Source of Truth).

Unifica as três fontes de dados presidenciais:
1. Model PresidentialMandate (tabela presidential_mandates / executivo)
2. Model Mandate com office == CargoPoliticoEnum.PRESIDENTE (mandatos no dossiê de políticos)
3. Arquivo canônico presidentes_historico.json (metadados oficiais, vice, ministros, fotos)
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from app.models.executivo import PresidentialMandate
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _load_presidents_json(data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    if data_dir is None:
        try:
            from app.api.v1 import politicians

            data_dir = getattr(politicians, "DATA_DIR", None)
        except Exception:
            data_dir = None

    if data_dir is None:
        from app.core import config

        data_dir = config.PROCESSED_DATA_DIR

    json_path = Path(data_dir) / "presidentes_historico.json"
    if not json_path.exists():
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as exc:
        logger.error("Erro ao carregar presidentes_historico.json: %s", exc)

    return []


def get_all_presidents(db: Optional[Session] = None, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retorna a lista canônica unificada de todos os presidentes da República."""
    json_data = _load_presidents_json(data_dir)
    return json_data


def get_president_by_reference(
    reference_id_or_uuid: str, db: Optional[Session] = None, data_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Busca presidente unificado por id_referencia (ex: 'lula-2023') ou por UUID."""
    ref_clean = reference_id_or_uuid.strip().lower()
    for pres in _load_presidents_json(data_dir):
        if pres.get("id_referencia", "").lower() == ref_clean:
            return pres

    # Tenta por db_id se for UUID
    if db:
        try:
            val_uuid = UUID(reference_id_or_uuid)
            mandate = db.query(PresidentialMandate).filter(PresidentialMandate.id == val_uuid).first()
            if mandate:
                for pres in _load_presidents_json(data_dir):
                    if (
                        pres.get("nome_civil", "").upper() == mandate.nome.upper()
                        or pres.get("nome_eleitoral", "").upper() == mandate.nome.upper()
                    ):
                        item = dict(pres)
                        item["db_id"] = str(mandate.id)
                        return item
        except (ValueError, TypeError):
            pass

    return None


def get_mandate_date_range(
    reference_id_or_uuid: str, db: Optional[Session] = None, data_dir: Optional[Path] = None
) -> Optional[Tuple[date, date]]:
    """Retorna (start_date, end_date) para um mandato presidencial."""
    pres = get_president_by_reference(reference_id_or_uuid, db, data_dir)
    if not pres:
        return None

    try:
        dt_inicio = datetime.strptime(pres["data_inicio"], "%Y-%m-%d").date()
        dt_fim = datetime.strptime(pres["data_fim"], "%Y-%m-%d").date() if pres.get("data_fim") else date.today()
        return dt_inicio, dt_fim
    except (ValueError, KeyError, TypeError):
        return None
