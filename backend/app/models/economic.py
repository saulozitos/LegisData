import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional
import enum

from sqlalchemy import (
    String, Text, Integer, Numeric, Date,
    ForeignKey, UniqueConstraint, Index, Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimeStampedModel


class CategoriaIndicadorEnum(str, enum.Enum):
    INFLACAO = "INFLACAO"
    PIB = "PIB"
    CESTA_BASICA = "CESTA_BASICA"
    COMBUSTIVEL = "COMBUSTIVEL"
    COMMODITY = "COMMODITY"
    DIVIDA_PUBLICA = "DIVIDA_PUBLICA"
    JUROS_SELIC = "JUROS_SELIC"
    CAMBIO_DOLAR = "CAMBIO_DOLAR"
    DESEMPREGO = "DESEMPREGO"
    SALARIO_MINIMO = "SALARIO_MINIMO"
    MERCADO_FINANCEIRO = "MERCADO_FINANCEIRO"


class PeriodicidadeIndicadorEnum(str, enum.Enum):
    DIARIA = "DIARIA"
    MENSAL = "MENSAL"
    TRIMESTRAL = "TRIMESTRAL"
    ANUAL = "ANUAL"


class UnidadeMedidaEnum(str, enum.Enum):
    PERCENTUAL = "PERCENTUAL"
    BRL = "BRL"
    USD = "USD"
    PONTOS_INDICE = "PONTOS_INDICE"
    TONELADAS = "TONELADAS"


class EconomicIndicatorSeries(TimeStampedModel):
    __tablename__ = "series_indicadores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_code: Mapped[str] = mapped_column("codigoSerie", String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column("nome", String(200), nullable=False)
    category: Mapped[CategoriaIndicadorEnum] = mapped_column("categoria", Enum(CategoriaIndicadorEnum), nullable=False, index=True)
    frequency: Mapped[PeriodicidadeIndicadorEnum] = mapped_column("periodicidade", Enum(PeriodicidadeIndicadorEnum), nullable=False)
    unit: Mapped[UnidadeMedidaEnum] = mapped_column("unidade", Enum(UnidadeMedidaEnum), nullable=False)
    source_agency: Mapped[str] = mapped_column("orgaoFonte", String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column("descricao", Text, nullable=True)

    data_points: Mapped[List["EconomicIndicatorValue"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )


class EconomicIndicatorValue(Base):
    __tablename__ = "pontos_dados_indicadores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    series_id: Mapped[uuid.UUID] = mapped_column("serieId", UUID(as_uuid=True), ForeignKey("series_indicadores.id", ondelete="CASCADE"), nullable=False)
    reference_date: Mapped[date] = mapped_column("dataReferencia", Date, nullable=False)
    reference_year: Mapped[int] = mapped_column("ano", Integer, nullable=False)
    reference_month: Mapped[Optional[int]] = mapped_column("mes", Integer, nullable=True)
    raw_value: Mapped[Decimal] = mapped_column("valorBruto", Numeric(18, 6), nullable=False)
    deflated_value: Mapped[Optional[Decimal]] = mapped_column("valorDeflacionado", Numeric(18, 6), nullable=True)
    original_currency: Mapped[str] = mapped_column("moedaOriginal", String(10), default="BRL", nullable=False)
    observation: Mapped[Optional[str]] = mapped_column("observacao", String(255), nullable=True)

    series: Mapped["EconomicIndicatorSeries"] = relationship(back_populates="data_points")

    __table_args__ = (
        UniqueConstraint("serieId", "dataReferencia", name="uq_series_reference_date"),
        Index("idx_economic_year_month", "ano", "mes"),
        Index("idx_economic_ref_date", "dataReferencia"),
    )


class AnnualMacroeconomicSummary(TimeStampedModel):
    __tablename__ = "resumos_macroeconomicos_anuais"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column("ano", Integer, unique=True, nullable=False, index=True)
    ipca_accumulated_year: Mapped[Optional[Decimal]] = mapped_column("ipcaAcumuladoAno", Numeric(14, 4), nullable=True)
    gdp_total_brl: Mapped[Optional[Decimal]] = mapped_column("pibTotalBrl", Numeric(18, 2), nullable=True)
    gdp_real_growth: Mapped[Optional[Decimal]] = mapped_column("pibCrescimentoReal", Numeric(6, 2), nullable=True)
    gdp_per_capita_brl: Mapped[Optional[Decimal]] = mapped_column("pibPerCapitaBrl", Numeric(12, 2), nullable=True)
    selic_average_year: Mapped[Optional[Decimal]] = mapped_column("selicMediaAno", Numeric(6, 2), nullable=True)
    usd_brl_average: Mapped[Optional[Decimal]] = mapped_column("cambioDolarMedioBrl", Numeric(18, 4), nullable=True)
    basic_basket_avg_brl: Mapped[Optional[Decimal]] = mapped_column("cestaBasicaMediaBrl", Numeric(10, 2), nullable=True)
    gasoline_avg_brl: Mapped[Optional[Decimal]] = mapped_column("gasolinaPrecoMedioBrl", Numeric(8, 3), nullable=True)
    beef_avg_brl: Mapped[Optional[Decimal]] = mapped_column("carneBovinaPrecoMedioBrl", Numeric(8, 2), nullable=True)
    net_debt_pct_gdp: Mapped[Optional[Decimal]] = mapped_column("dividaLiquidaPctPib", Numeric(6, 2), nullable=True)
    unemployment_avg: Mapped[Optional[Decimal]] = mapped_column("desempregoMedio", Numeric(5, 2), nullable=True)
    minimum_wage_nominal_brl: Mapped[Optional[Decimal]] = mapped_column("salarioMinimoNominalBrl", Numeric(10, 2), nullable=True)
    dominant_president_name: Mapped[Optional[str]] = mapped_column("presidenteDominanteNome", String(150), nullable=True)
    ibovespa_close: Mapped[Optional[Decimal]] = mapped_column("ibovespaFechamentoAno", Numeric(12, 2), nullable=True)

    # Indicadores Socioambientais e Macroeconômicos Expandidos
    crescimento_pib_percentual: Mapped[Optional[Decimal]] = mapped_column("crescimentoPibPercentual", Numeric(6, 2), nullable=True)
    inflacao_anual_ipca: Mapped[Optional[Decimal]] = mapped_column("inflacaoAnualIpca", Numeric(14, 4), nullable=True)
    inflacao_acumulada_mandato: Mapped[Optional[Decimal]] = mapped_column("inflacaoAcumuladaMandato", Numeric(14, 4), nullable=True)
    taxa_desemprego_anual: Mapped[Optional[Decimal]] = mapped_column("taxaDesempregoAnual", Numeric(5, 2), nullable=True)
    taxa_desmatamento_amazonia: Mapped[Optional[Decimal]] = mapped_column("taxaDesmatamentoAmazonia", Numeric(10, 2), nullable=True)
    inseguranca_alimentar_pct: Mapped[Optional[Decimal]] = mapped_column("insegurancaAlimentarPct", Numeric(5, 2), nullable=True)

    # Indicadores Expandidos de Câmbio, Renda e Segurança Pública
    cotacao_dolar_fechamento: Mapped[Optional[Decimal]] = mapped_column("cotacaoDolarFechamento", Numeric(12, 4), nullable=True)
    salario_minimo: Mapped[Optional[Decimal]] = mapped_column("salarioMinimo", Numeric(10, 2), nullable=True)
    taxa_homicidios: Mapped[Optional[Decimal]] = mapped_column("taxaHomicidios", Numeric(6, 2), nullable=True)
    taxa_feminicidios: Mapped[Optional[Decimal]] = mapped_column("taxaFeminicidios", Numeric(6, 2), nullable=True)


class AnnualSocialIndicator(TimeStampedModel):
    __tablename__ = "indicadores_sociais_anuais"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column("ano", Integer, unique=True, nullable=False, index=True)
    illiteracy_rate_pct: Mapped[Optional[Decimal]] = mapped_column("taxaAnalfabetismoPct", Numeric(5, 2), nullable=True)
    extreme_poverty_pct: Mapped[Optional[Decimal]] = mapped_column("populacaoExtremaPobrezaPct", Numeric(5, 2), nullable=True)
    extreme_poverty_millions: Mapped[Optional[Decimal]] = mapped_column("populacaoExtremaPobrezaMilhoes", Numeric(6, 2), nullable=True)
    food_insecurity_pct: Mapped[Optional[Decimal]] = mapped_column("populacaoInsegurancaAlimentarPct", Numeric(5, 2), nullable=True)
    food_insecurity_millions: Mapped[Optional[Decimal]] = mapped_column("populacaoInsegurancaAlimentarMilhoes", Numeric(6, 2), nullable=True)
    gini_index: Mapped[Optional[Decimal]] = mapped_column("indiceGini", Numeric(5, 3), nullable=True)
    data_source: Mapped[str] = mapped_column("fonteDados", String(100), default="IBGE / IPEA / FAO / Penssan", nullable=False)


class StateSocialIndicator(TimeStampedModel):
    __tablename__ = "indicadores_sociais_uf"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year: Mapped[int] = mapped_column("ano", Integer, nullable=False, index=True)
    uf: Mapped[str] = mapped_column("uf", String(2), nullable=False, index=True)
    state_name: Mapped[str] = mapped_column("estadoNome", String(100), nullable=False)
    region: Mapped[str] = mapped_column("regiao", String(30), nullable=False)
    illiteracy_rate_pct: Mapped[Optional[Decimal]] = mapped_column("taxaAnalfabetismoPct", Numeric(5, 2), nullable=True)
    extreme_poverty_pct: Mapped[Optional[Decimal]] = mapped_column("extremaPobrezaPct", Numeric(5, 2), nullable=True)
    food_insecurity_pct: Mapped[Optional[Decimal]] = mapped_column("insegurancaAlimentarPct", Numeric(5, 2), nullable=True)
    gini_index: Mapped[Optional[Decimal]] = mapped_column("indiceGini", Numeric(5, 3), nullable=True)

    __table_args__ = (
        UniqueConstraint("ano", "uf", name="uq_social_indicator_year_uf"),
        Index("idx_social_indicator_uf", "uf"),
    )


class StatePresidentialElectionResult(TimeStampedModel):
    __tablename__ = "resultados_eleicoes_presidenciais_uf"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    election_year: Mapped[int] = mapped_column("anoEleicao", Integer, nullable=False, index=True)
    mandate_ref_id: Mapped[str] = mapped_column("mandatoIdRef", String(50), nullable=False)
    uf: Mapped[str] = mapped_column("uf", String(2), nullable=False, index=True)
    state_name: Mapped[str] = mapped_column("estadoNome", String(100), nullable=False)
    region: Mapped[str] = mapped_column("regiao", String(30), nullable=False)
    winner_candidate_name: Mapped[str] = mapped_column("candidatoVencedorNome", String(150), nullable=False)
    winner_party_acronym: Mapped[str] = mapped_column("partidoVencedorSigla", String(20), nullable=False)
    winner_votes_pct: Mapped[Decimal] = mapped_column("votosVencedorPct", Numeric(5, 2), nullable=False)
    runner_up_candidate_name: Mapped[str] = mapped_column("candidatoSegundoNome", String(150), nullable=False)
    runner_up_party_acronym: Mapped[str] = mapped_column("partidoSegundoSigla", String(20), nullable=False)
    runner_up_votes_pct: Mapped[Decimal] = mapped_column("votosSegundoPct", Numeric(5, 2), nullable=False)
    total_valid_votes: Mapped[Optional[int]] = mapped_column("totalVotosValidos", Integer, nullable=True)
    round_number: Mapped[int] = mapped_column("turno", Integer, default=2, nullable=False)

    __table_args__ = (
        UniqueConstraint("anoEleicao", "uf", "turno", name="uq_election_year_uf_round"),
        Index("idx_election_year_uf", "anoEleicao", "uf"),
    )
