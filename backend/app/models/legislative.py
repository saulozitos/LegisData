import enum
import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimeStampedModel


class TipoProposicaoEnum(str, enum.Enum):
    PEC = "PEC"
    PL = "PL"
    PLP = "PLP"
    MPV = "MPV"
    PDL = "PDL"
    DECRETO_PRES = "DECRETO_PRES"
    LEI_DELEGADA = "LEI_DELEGADA"


class StatusTramitacaoEnum(str, enum.Enum):
    APROVADA_E_SANCIONADA = "APROVADA_E_SANCIONADA"
    APROVADA_E_PROMULGADA = "APROVADA_E_PROMULGADA"
    VETADA_TOTAL = "VETADA_TOTAL"
    VETADA_PARCIAL = "VETADA_PARCIAL"
    REJEITADA = "REJEITADA"
    EM_TRAMITACAO = "EM_TRAMITACAO"
    ARQUIVADA = "ARQUIVADA"


class CasaLegislativaEnum(str, enum.Enum):
    CAMARA_DOS_DEPUTADOS = "CAMARA_DOS_DEPUTADOS"
    SENADO_FEDERAL = "SENADO_FEDERAL"
    CONGRESSO_NACIONAL = "CONGRESSO_NACIONAL"
    ASSEMBLEIA_LEGISLATIVA = "ASSEMBLEIA_LEGISLATIVA"


class VotoOpcaoEnum(str, enum.Enum):
    SIM = "SIM"
    NAO = "NAO"
    ABSTENCAO = "ABSTENCAO"
    OBSTRUCAO = "OBSTRUCAO"
    AUSENTE = "AUSENTE"
    ARTIGO_17 = "ARTIGO_17"


class TipoPresencaEnum(str, enum.Enum):
    PRESENTE = "PRESENTE"
    AUSENCIA_JUSTIFICADA = "AUSENCIA_JUSTIFICADA"
    AUSENCIA_NAO_JUSTIFICADA = "AUSENCIA_NAO_JUSTIFICADA"
    LICENCA_MEDICA = "LICENCA_MEDICA"
    MISSAO_OFICIAL = "MISSAO_OFICIAL"


class Proposition(TimeStampedModel):
    __tablename__ = "proposicoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_camara_id: Mapped[Optional[int]] = mapped_column("idExternoCamara", Integer, unique=True, nullable=True)
    external_senado_id: Mapped[Optional[int]] = mapped_column("idExternoSenado", Integer, unique=True, nullable=True)
    proposition_type: Mapped[TipoProposicaoEnum] = mapped_column("tipo", Enum(TipoProposicaoEnum), nullable=False)
    number: Mapped[int] = mapped_column("numero", Integer, nullable=False)
    year: Mapped[int] = mapped_column("ano", Integer, nullable=False)
    title: Mapped[str] = mapped_column("titulo", String(255), nullable=False)
    summary: Mapped[str] = mapped_column("ementa", Text, nullable=False)
    detailed_summary: Mapped[Optional[str]] = mapped_column("explicacaoEmenta", Text, nullable=True)
    thematic_area: Mapped[Optional[str]] = mapped_column("areaTematica", String(100), nullable=True)
    presentation_date: Mapped[date] = mapped_column("dataApresentacao", Date, nullable=False)
    sanction_date: Mapped[Optional[date]] = mapped_column("dataSancaoPromulgacao", Date, nullable=True)
    status: Mapped[StatusTramitacaoEnum] = mapped_column(
        "statusTramitacao",
        Enum(StatusTramitacaoEnum),
        default=StatusTramitacaoEnum.EM_TRAMITACAO,
        nullable=False,
    )
    full_text_url: Mapped[Optional[str]] = mapped_column("urlTextoOriginal", Text, nullable=True)
    is_structural_reform: Mapped[bool] = mapped_column("isReformaEstrutural", Boolean, default=False, nullable=False)
    author_name: Mapped[Optional[str]] = mapped_column("autorNome", Text, nullable=True)
    author_politician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "autorPoliticoId", UUID(as_uuid=True), ForeignKey("politicos.id"), nullable=True
    )
    is_executive_initiative: Mapped[bool] = mapped_column(
        "iniciativaPoderExecutivo", Boolean, default=False, nullable=False
    )
    impact_axis: Mapped[Optional[str]] = mapped_column("eixoImpacto", String(100), nullable=True, index=True)
    impact_tags: Mapped[Optional[str]] = mapped_column("eixosImpacto", String(255), nullable=True)
    official_url: Mapped[Optional[str]] = mapped_column("urlOficial", Text, nullable=True)

    # Relationships
    author_politician: Mapped[Optional["Politician"]] = relationship("Politician", back_populates="propositions")
    voting_sessions: Mapped[List["VotingSession"]] = relationship(
        back_populates="proposition", cascade="all, delete-orphan"
    )
    economic_impacts: Mapped[List["PolicyEconomicImpact"]] = relationship(
        "PolicyEconomicImpact",
        back_populates="proposition",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_proposition_type_num_year", "tipo", "numero", "ano"),
        Index("idx_proposition_structural", "isReformaEstrutural"),
        Index("idx_proposicoes_autor", "autorPoliticoId"),
        Index("idx_proposicoes_ano", "ano"),
    )


class VotingSession(Base):
    __tablename__ = "sessoes_votacao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[Optional[str]] = mapped_column("idExterno", String(100), unique=True, nullable=True)
    proposition_id: Mapped[uuid.UUID] = mapped_column(
        "proposicaoId",
        UUID(as_uuid=True),
        ForeignKey("proposicoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    legislative_house: Mapped[CasaLegislativaEnum] = mapped_column(
        "casaLegislativa", Enum(CasaLegislativaEnum), nullable=False
    )
    session_datetime: Mapped[datetime] = mapped_column("dataHoraVotacao", DateTime(timezone=True), nullable=False)
    agenda_title: Mapped[str] = mapped_column("tituloPauta", String(255), nullable=False)
    detailed_description: Mapped[Optional[str]] = mapped_column("descricaoDetalhada", Text, nullable=True)
    is_secret_vote: Mapped[bool] = mapped_column("isVotacaoSecreta", Boolean, default=False, nullable=False)
    is_approved: Mapped[bool] = mapped_column("aprovada", Boolean, nullable=False)
    votes_yes_count: Mapped[int] = mapped_column("totalSim", Integer, default=0, nullable=False)
    votes_no_count: Mapped[int] = mapped_column("totalNao", Integer, default=0, nullable=False)
    votes_abstain_count: Mapped[int] = mapped_column("totalAbstencao", Integer, default=0, nullable=False)
    votes_obstruction_count: Mapped[int] = mapped_column("totalObstrucao", Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    proposition: Mapped["Proposition"] = relationship(back_populates="voting_sessions")
    votes: Mapped[List["ParliamentaryVote"]] = relationship(
        back_populates="voting_session", cascade="all, delete-orphan"
    )


class ParliamentaryVote(Base):
    __tablename__ = "votos_parlamentares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voting_session_id: Mapped[uuid.UUID] = mapped_column(
        "sessaoVotacaoId",
        UUID(as_uuid=True),
        ForeignKey("sessoes_votacao.id", ondelete="CASCADE"),
        nullable=False,
    )
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    party_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("partidos_politicos.id"),
        nullable=True,
        index=True,
    )
    vote_choice: Mapped[VotoOpcaoEnum] = mapped_column("voto", Enum(VotoOpcaoEnum), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    voting_session: Mapped["VotingSession"] = relationship(back_populates="votes")
    politician: Mapped["Politician"] = relationship("Politician", back_populates="votes")
    party: Mapped[Optional["PoliticalParty"]] = relationship("PoliticalParty")

    __table_args__ = (
        UniqueConstraint("sessaoVotacaoId", "politicoId", name="uq_session_politician_vote"),
        Index("idx_parliamentary_vote_choice", "voto"),
        Index("idx_votos_politico", "politicoId"),
        Index("idx_votos_partido", "partidoId"),
    )


class AttendanceRecord(Base):
    __tablename__ = "registros_presenca"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        "mandatoId",
        UUID(as_uuid=True),
        ForeignKey("mandatos.id", ondelete="CASCADE"),
        nullable=False,
    )
    legislative_house: Mapped[CasaLegislativaEnum] = mapped_column(
        "casaLegislativa", Enum(CasaLegislativaEnum), nullable=False
    )
    session_date: Mapped[date] = mapped_column("dataSessao", Date, nullable=False)
    attendance_status: Mapped[TipoPresencaEnum] = mapped_column("tipoPresenca", Enum(TipoPresencaEnum), nullable=False)
    justification: Mapped[Optional[str]] = mapped_column("justificativa", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="attendances")
    mandate: Mapped["Mandate"] = relationship("Mandate", back_populates="attendances")

    __table_args__ = (Index("idx_attendance_politician_date", "politicoId", "dataSessao"),)
