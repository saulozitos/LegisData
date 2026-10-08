"""
ETL Pipeline: carga de presença em plenário e de remuneração a partir de dados OFICIAIS extraídos.

Entradas (geradas por `etl/run_etl.py --presenca` e `--remuneracao`):
  * etl/data/processed/presenca_plenario_dias.json.gz     (um registro por parlamentar/dia)
  * etl/data/processed/remuneracao_parlamentares.json     (um registro por deputado/mês)

Antes esta carga era sorteada com `random` (presença, "licença médica", CEAP mensal): isso foi removido. Nada é
gerado aqui; se o arquivo não existir ou não tiver proveniência oficial (`fonte` + `is_synthetic: false`), a carga
é recusada. Linhas sintéticas gravadas por versões antigas são substituídas ao carregar o mesmo parlamentar/período.

Idempotência: para cada (parlamentar, casa, ano) presente no arquivo, as linhas existentes do período são apagadas e
reinseridas na mesma transação; rodar duas vezes produz o mesmo estado.
"""

import argparse
import json
import logging
from bisect import bisect_right
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from app.core.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AttendanceRecord,
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    Mandate,
    Politician,
    PoliticianRemuneration,
    TipoPresencaEnum,
)

from etl.extractors.presenca_extractor import carregar_dias  # noqa: E402
from etl.extractors.remuneracao_extractor import ARQ_REMUNERACAO  # noqa: E402

logger = logging.getLogger("AttendanceRemuneration")

BATCH = 5000
CARGO_POR_CASA = {
    "camara": CargoPoliticoEnum.DEPUTADO_FEDERAL,
    "senado": CargoPoliticoEnum.SENADOR,
}
CASA_ENUM = {
    "camara": CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
    "senado": CasaLegislativaEnum.SENADO_FEDERAL,
}
FONTE_REMUNERACAO_CURTA = "Câmara dos Deputados - Portal da Transparência"


class MandateResolver:
    """Escolhe o mandato de um parlamentar para uma data: o vigente na data; senão o mais próximo (aproximado)."""

    def __init__(self, mandatos: Iterable[Mandate]):
        por_chave: Dict[Tuple[Any, CargoPoliticoEnum], List[Mandate]] = defaultdict(list)
        for m in mandatos:
            por_chave[(m.politician_id, m.office)].append(m)
        self._por_chave = {k: sorted(v, key=lambda m: m.start_date) for k, v in por_chave.items()}
        self._inicios = {k: [m.start_date for m in v] for k, v in self._por_chave.items()}
        self.aproximados = 0

    def resolver(self, politician_id: Any, cargo: CargoPoliticoEnum, dia: date) -> Optional[Mandate]:
        chave = (politician_id, cargo)
        lista = self._por_chave.get(chave)
        if not lista:
            return None
        idx = bisect_right(self._inicios[chave], dia) - 1
        if idx >= 0:
            candidato = lista[idx]
            if candidato.end_date is None or dia <= candidato.end_date:
                return candidato
        # Sem mandato vigente cadastrado na data (ex.: legislatura anterior não carregada): usa o mais próximo
        # e contabiliza como aproximação — o parlamentar existe e exerceu o cargo, mas o mandato não está no banco.
        self.aproximados += 1
        if idx >= 0:
            return lista[idx]
        return lista[0]


def _assert_oficial(corpo: Dict[str, Any], nome: str) -> None:
    if corpo.get("is_synthetic") is not False or not corpo.get("fonte"):
        raise ValueError(f"{nome}: sem proveniência oficial (exige `fonte` e `is_synthetic: false`); carga recusada.")


def _mapa_ids(session, coluna) -> Dict[int, Any]:
    return {cid: pid for cid, pid in session.query(coluna, Politician.id).filter(coluna.isnot(None)).all()}


def _data(valor: str) -> date:
    return date.fromisoformat(valor)


def load_attendances(session, processed_dir: Path = PROCESSED_DATA_DIR) -> Dict[str, int]:
    """Carrega a presença por dia; retorna contadores (inseridos, apagados, ignorados por motivo)."""
    corpo = carregar_dias(processed_dir)
    stats: Dict[str, int] = {
        "inseridos": 0,
        "apagados": 0,
        "sem_politico": 0,
        "sem_mandato": 0,
        "mandato_aproximado": 0,
    }
    if corpo is None:
        logger.warning("Presença: arquivo ausente/ilegível em %s — execute `--presenca` primeiro.", processed_dir)
        stats["arquivo_ausente"] = 1
        return stats
    _assert_oficial(corpo, "presenca_plenario_dias")

    ids = {"camara": _mapa_ids(session, Politician.camara_id), "senado": _mapa_ids(session, Politician.senado_id)}
    resolver = MandateResolver(
        session.query(Mandate)
        .filter(Mandate.office.in_([CargoPoliticoEnum.DEPUTADO_FEDERAL, CargoPoliticoEnum.SENADOR]))
        .all()
    )

    for casa in ("camara", "senado"):
        linhas = corpo.get(casa) or []
        por_pol: Dict[Any, List[List[Any]]] = defaultdict(list)
        for linha in linhas:
            pid = ids[casa].get(int(linha[0]))
            if pid is None:
                stats["sem_politico"] += 1
                continue
            por_pol[pid].append(linha)

        lote: List[Dict[str, Any]] = []
        for pid, regs in por_pol.items():
            anos = sorted({int(r[1][:4]) for r in regs})
            for ano in anos:
                stats["apagados"] += (
                    session.query(AttendanceRecord)
                    .filter(
                        AttendanceRecord.politician_id == pid,
                        AttendanceRecord.legislative_house == CASA_ENUM[casa],
                        AttendanceRecord.session_date >= date(ano, 1, 1),
                        AttendanceRecord.session_date <= date(ano, 12, 31),
                    )
                    .delete(synchronize_session=False)
                )
            vistos = set()
            for _cid, dia_txt, status, justificativa in regs:
                if dia_txt in vistos:
                    continue  # (parlamentar, dia) é único por construção; protege contra arquivo duplicado
                vistos.add(dia_txt)
                dia = _data(dia_txt)
                mandato = resolver.resolver(pid, CARGO_POR_CASA[casa], dia)
                if mandato is None:
                    stats["sem_mandato"] += 1
                    continue
                lote.append(
                    {
                        "politician_id": pid,
                        "mandate_id": mandato.id,
                        "legislative_house": CASA_ENUM[casa],
                        "session_date": dia,
                        "attendance_status": TipoPresencaEnum(status),
                        "justification": justificativa,
                    }
                )
                if len(lote) >= BATCH:
                    session.bulk_insert_mappings(AttendanceRecord, lote)
                    stats["inseridos"] += len(lote)
                    lote = []
        if lote:
            session.bulk_insert_mappings(AttendanceRecord, lote)
            stats["inseridos"] += len(lote)
    stats["mandato_aproximado"] = resolver.aproximados
    session.commit()
    logger.info("Presença carregada: %s", stats)
    return stats


def load_remunerations(session, processed_dir: Path = PROCESSED_DATA_DIR) -> Dict[str, int]:
    """Carrega a remuneração mensal dos deputados (bruto sempre; líquido só quando coletado; demais campos NULL)."""
    stats: Dict[str, int] = {"inseridos": 0, "apagados": 0, "sem_politico": 0, "sem_mandato": 0}
    caminho = Path(processed_dir) / ARQ_REMUNERACAO
    try:
        corpo = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Remuneração: arquivo ausente/ilegível em %s — execute `--remuneracao` primeiro.", caminho)
        stats["arquivo_ausente"] = 1
        return stats
    _assert_oficial(corpo, ARQ_REMUNERACAO)

    ids = _mapa_ids(session, Politician.camara_id)
    resolver = MandateResolver(
        session.query(Mandate).filter(Mandate.office == CargoPoliticoEnum.DEPUTADO_FEDERAL).all()
    )

    por_pol: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for r in corpo.get("registros", []):
        pid = ids.get(int(r["camara_id"]))
        if pid is None:
            stats["sem_politico"] += 1
            continue
        por_pol[pid].append(r)

    lote: List[Dict[str, Any]] = []
    for pid, regs in por_pol.items():
        for ano in sorted({int(r["ano"]) for r in regs}):
            stats["apagados"] += (
                session.query(PoliticianRemuneration)
                .filter(PoliticianRemuneration.politician_id == pid, PoliticianRemuneration.reference_year == ano)
                .delete(synchronize_session=False)
            )
        vistos = set()
        for r in regs:
            chave = (int(r["ano"]), int(r["mes"]))
            if chave in vistos:
                continue
            vistos.add(chave)
            mandato = resolver.resolver(pid, CargoPoliticoEnum.DEPUTADO_FEDERAL, date(chave[0], chave[1], 1))
            if mandato is None:
                stats["sem_mandato"] += 1
                continue
            liquido = r.get("salario_liquido")
            lote.append(
                {
                    "politician_id": pid,
                    "mandate_id": mandato.id,
                    "reference_year": chave[0],
                    "reference_month": chave[1],
                    "gross_salary": Decimal(str(r["salario_bruto"])),
                    "net_salary": Decimal(str(liquido)) if liquido is not None else None,
                    "parliamentary_quota_ceap": None,
                    "housing_allowance": None,
                    "other_benefits": None,
                    "data_source": FONTE_REMUNERACAO_CURTA,
                }
            )
            if len(lote) >= BATCH:
                session.bulk_insert_mappings(PoliticianRemuneration, lote)
                stats["inseridos"] += len(lote)
                lote = []
    if lote:
        session.bulk_insert_mappings(PoliticianRemuneration, lote)
        stats["inseridos"] += len(lote)
    session.commit()
    logger.info("Remuneração carregada: %s", stats)
    return stats


def main(argv: Optional[list] = None) -> None:
    parser = argparse.ArgumentParser(description="Carga de presença e remuneração oficiais no PostgreSQL.")
    parser.add_argument("--so-presenca", action="store_true")
    parser.add_argument("--so-remuneracao", action="store_true")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        if not args.so_remuneracao:
            print("Presença:", load_attendances(db))
        if not args.so_presenca:
            print("Remuneração:", load_remunerations(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
