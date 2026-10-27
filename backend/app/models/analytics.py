import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimeStampedModel


class MandateEconomicPerformance(TimeStampedModel):
    __tablename__ = "mandatos_performance_economica"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        "mandatoId",
        UUID(as_uuid=True),
        ForeignKey("mandatos.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    ipca_accumulated: Mapped[Decimal] = mapped_column("ipcaAcumuladoMandato", Numeric(14, 4), nullable=False)
    gdp_accumulated_growth: Mapped[Decimal] = mapped_column("pibCrescimentoAcumulado", Numeric(8, 4), nullable=False)
    gdp_annual_avg_growth: Mapped[Decimal] = mapped_column("pibCrescimentoMedioAno", Numeric(6, 2), nullable=False)
    initial_debt_pct: Mapped[Optional[Decimal]] = mapped_column("dividaLiquidaInicialPct", Numeric(6, 2), nullable=True)
    final_debt_pct: Mapped[Optional[Decimal]] = mapped_column("dividaLiquidaFinalPct", Numeric(6, 2), nullable=True)
    debt_delta_pct: Mapped[Optional[Decimal]] = mapped_column("dividaLiquidaDeltaPct", Numeric(6, 2), nullable=True)
    initial_usd_brl: Mapped[Optional[Decimal]] = mapped_column("cambioInicialUsdBrl", Numeric(18, 4), nullable=True)
    final_usd_brl: Mapped[Optional[Decimal]] = mapped_column("cambioFinalUsdBrl", Numeric(18, 4), nullable=True)
    usd_variation_pct: Mapped[Optional[Decimal]] = mapped_column("cambioVariacaoPct", Numeric(14, 2), nullable=True)
    initial_min_wage_brl: Mapped[Optional[Decimal]] = mapped_column(
        "salarioMinimoInicialBrl", Numeric(12, 2), nullable=True
    )
    final_min_wage_brl: Mapped[Optional[Decimal]] = mapped_column(
        "salarioMinimoFinalBrl", Numeric(12, 2), nullable=True
    )
    initial_min_wage_usd: Mapped[Optional[Decimal]] = mapped_column(
        "salarioMinimoInicialUsd", Numeric(10, 2), nullable=True
    )
    final_min_wage_usd: Mapped[Optional[Decimal]] = mapped_column(
        "salarioMinimoFinalUsd", Numeric(10, 2), nullable=True
    )
    initial_unemployment_rate: Mapped[Optional[Decimal]] = mapped_column(
        "taxaDesempregoInicial", Numeric(5, 2), nullable=True
    )
    final_unemployment_rate: Mapped[Optional[Decimal]] = mapped_column(
        "taxaDesempregoFinal", Numeric(5, 2), nullable=True
    )
    analytical_summary: Mapped[Optional[str]] = mapped_column("resumoAnalitico", Text, nullable=True)

    # Relationships
    mandate: Mapped["Mandate"] = relationship("Mandate", back_populates="economic_performance")


class PolicyEconomicImpact(TimeStampedModel):
    __tablename__ = "analises_impacto_politica"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposition_id: Mapped[uuid.UUID] = mapped_column(
        "proposicaoId",
        UUID(as_uuid=True),
        ForeignKey("proposicoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluation_window_months: Mapped[int] = mapped_column("janelaMesesAvaliacao", Integer, default=12, nullable=False)
    ipca_window_delta: Mapped[Optional[Decimal]] = mapped_column("variacaoIpcaJanela", Numeric(8, 4), nullable=True)
    gdp_window_delta: Mapped[Optional[Decimal]] = mapped_column("variacaoPibJanela", Numeric(8, 4), nullable=True)
    selic_window_delta: Mapped[Optional[Decimal]] = mapped_column("variacaoSelicJanela", Numeric(6, 2), nullable=True)
    usd_window_delta: Mapped[Optional[Decimal]] = mapped_column("variacaoCambioJanela", Numeric(8, 4), nullable=True)
    correlation_score: Mapped[Optional[Decimal]] = mapped_column("grauCorrelacaoScore", Numeric(5, 2), nullable=True)
    scientific_opinion: Mapped[Optional[str]] = mapped_column("parecerCientifico", Text, nullable=True)

    # Relationships
    proposition: Mapped["Proposition"] = relationship("Proposition", back_populates="economic_impacts")

    __table_args__ = (Index("idx_impact_proposition", "proposicaoId"),)


class LogExecucaoCron(Base):
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
    )
