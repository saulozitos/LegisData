import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import MigratedBase


class LogExecucaoCron(MigratedBase):
    """Registro das execuções do cron diário (`etl.log_execucao_cron`, criada pela migração 0036)."""

    __tablename__ = "log_execucao_cron"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_execucao: Mapped[datetime] = mapped_column(
        "dataExecucao", DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    status_execucao: Mapped[str] = mapped_column("statusExecucao", String(20), nullable=False)
    registros_atualizados: Mapped[int] = mapped_column("registrosAtualizados", Integer, default=0, nullable=False)
    tempo_processamento_segundos: Mapped[int] = mapped_column(
        "tempoProcessamentoSegundos", Integer, default=0, nullable=False
    )
    erro_mensagem: Mapped[Optional[str]] = mapped_column("erroMensagem", Text, nullable=True)
    etapa: Mapped[Optional[str]] = mapped_column("etapa", String(50), nullable=True)

    __table_args__ = (
        Index("idx_cron_data", "dataExecucao"),
        Index("idx_cron_status", "statusExecucao"),
        {"schema": "etl"},
    )
