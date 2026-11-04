import uuid
from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import StagingBase, StagingTimeStampedModel
from .enums import (
    CargoPoliticoEnum,
    EspectroPoliticoEnum,
    MotivoDesfiliacaoEnum,
    SituacaoMandatoEnum,
    StatusMandatoEnum,
    TipoEsferaEnum,
)


class Politician(StagingTimeStampedModel):
    __tablename__ = "politicos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    civil_name: Mapped[str] = mapped_column("nomeCivil", String(255), nullable=False)
    electoral_name: Mapped[str] = mapped_column("nomeEleitoral", String(150), nullable=False, index=True)
    tse_id: Mapped[Optional[str]] = mapped_column("tseId", String(50), unique=True, nullable=True)
    camara_id: Mapped[Optional[int]] = mapped_column("camaraId", Integer, unique=True, nullable=True, index=True)
    senado_id: Mapped[Optional[int]] = mapped_column("senadoId", Integer, unique=True, nullable=True, index=True)
    birth_date: Mapped[Optional[date]] = mapped_column("dataNascimento", Date, nullable=True)
    death_date: Mapped[Optional[date]] = mapped_column("dataFalecimento", Date, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column("genero", String(20), nullable=True)
    birthplace_city: Mapped[Optional[str]] = mapped_column("naturalidadeMunicipio", String(100), nullable=True)
    birthplace_state: Mapped[Optional[str]] = mapped_column("naturalidadeUf", String(2), nullable=True)
    photo_url: Mapped[Optional[str]] = mapped_column("fotoUrl", Text, nullable=True)
    biography: Mapped[Optional[str]] = mapped_column("biografia", Text, nullable=True)
    email: Mapped[Optional[str]] = mapped_column("email", String(255), nullable=True)
    cabinet_room: Mapped[Optional[str]] = mapped_column("gabineteSala", String(100), nullable=True)
    cabinet_phone: Mapped[Optional[str]] = mapped_column("gabineteTelefone", String(50), nullable=True)
    social_links: Mapped[Optional[dict]] = mapped_column("redesSociais", JSON, nullable=True)
    possui_processos_declarados: Mapped[bool] = mapped_column(
        "possuiProcessosDeclarados", Boolean, default=False, nullable=False
    )

    # Relationships
    affiliations: Mapped[List["PartyAffiliation"]] = relationship(
        back_populates="politician", cascade="all, delete-orphan"
    )
    mandates: Mapped[List["Mandate"]] = relationship(back_populates="politician", cascade="all, delete-orphan")
    propositions: Mapped[List["Proposition"]] = relationship("Proposition", back_populates="author_politician")
    votes: Mapped[List["ParliamentaryVote"]] = relationship("ParliamentaryVote", back_populates="politician")
    attendances: Mapped[List["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="politician")


class PoliticalParty(StagingTimeStampedModel):
    __tablename__ = "partidos_politicos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    acronym: Mapped[str] = mapped_column("sigla", String(20), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column("nomeCompleto", String(255), nullable=False)
    electoral_number: Mapped[Optional[int]] = mapped_column("numeroEleitoral", Integer, unique=True, nullable=True)
    foundation_date: Mapped[Optional[date]] = mapped_column("dataFundacao", Date, nullable=True)
    dissolution_date: Mapped[Optional[date]] = mapped_column("dataExtincao", Date, nullable=True)
    successor_party_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "partidoSucessorId",
        UUID(as_uuid=True),
        ForeignKey("partidos_politicos.id"),
        nullable=True,
    )
    logo_url: Mapped[Optional[str]] = mapped_column("logoUrl", Text, nullable=True)
    political_spectrum: Mapped[Optional[EspectroPoliticoEnum]] = mapped_column(
        "espectroPolitico", Enum(EspectroPoliticoEnum), nullable=True
    )
    ideology: Mapped[Optional[str]] = mapped_column("ideologia", String(255), nullable=True)
    motto: Mapped[Optional[str]] = mapped_column("lema", String(255), nullable=True)

    # Relationships
    affiliations: Mapped[List["PartyAffiliation"]] = relationship(back_populates="party")
    mandates: Mapped[List["Mandate"]] = relationship(back_populates="party")
    # Auto-referência: muitos partidos extintos -> um sucessor
    successor_party: Mapped[Optional["PoliticalParty"]] = relationship(
        "PoliticalParty",
        remote_side="PoliticalParty.id",
        back_populates="predecessors",
        foreign_keys="PoliticalParty.successor_party_id",
    )
    predecessors: Mapped[List["PoliticalParty"]] = relationship(
        "PoliticalParty",
        back_populates="successor_party",
        foreign_keys="PoliticalParty.successor_party_id",
    )


class PartyAffiliation(StagingBase):
    __tablename__ = "filiacoes_partidarias"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("partidos_politicos.id"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column("dataFiliacao", Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column("dataDesfiliacao", Date, nullable=True)
    is_current: Mapped[bool] = mapped_column("isAtual", Boolean, default=False, nullable=False)
    disaffiliation_reason: Mapped[Optional[MotivoDesfiliacaoEnum]] = mapped_column(
        "motivoDesfiliacao", Enum(MotivoDesfiliacaoEnum), nullable=True
    )
    state: Mapped[Optional[str]] = mapped_column("uf", String(2), nullable=True)
    created_at: Mapped[date] = mapped_column(Date, default=date.today)

    # Relationships
    politician: Mapped["Politician"] = relationship(back_populates="affiliations")
    party: Mapped["PoliticalParty"] = relationship(back_populates="affiliations")

    __table_args__ = (
        Index("idx_affiliation_politician_date", "politicoId", "dataFiliacao"),
        Index("idx_affiliation_politician", "politicoId"),
        Index("idx_affiliation_party", "partidoId"),
    )


class Mandate(StagingTimeStampedModel):
    __tablename__ = "mandatos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("partidos_politicos.id"),
        nullable=False,
    )
    office: Mapped[CargoPoliticoEnum] = mapped_column("cargo", Enum(CargoPoliticoEnum), nullable=False)
    sphere: Mapped[TipoEsferaEnum] = mapped_column(
        "esfera", Enum(TipoEsferaEnum), default=TipoEsferaEnum.FEDERAL, nullable=False
    )
    jurisdiction_state: Mapped[str] = mapped_column("ufJurisdicao", String(2), default="BR", nullable=False)
    election_year: Mapped[int] = mapped_column("anoEleicao", Integer, nullable=False)
    term_number: Mapped[int] = mapped_column("numeroMandato", Integer, default=1, nullable=False)
    start_date: Mapped[date] = mapped_column("dataInicio", Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column("dataFim", Date, nullable=True)
    status: Mapped[StatusMandatoEnum] = mapped_column(
        "status",
        Enum(StatusMandatoEnum),
        default=StatusMandatoEnum.TITULAR_ATIVO,
        nullable=False,
    )
    coalition_name: Mapped[Optional[str]] = mapped_column("coligacaoNome", String(255), nullable=True)
    total_votes: Mapped[Optional[int]] = mapped_column("totalVotos", Integer, nullable=True)
    vote_percentage: Mapped[Optional[Decimal]] = mapped_column("percentualVotos", Numeric(5, 2), nullable=True)

    # Relationships
    politician: Mapped["Politician"] = relationship(back_populates="mandates")
    party: Mapped["PoliticalParty"] = relationship(back_populates="mandates")
    attendances: Mapped[List["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="mandate")
    cabinet_members: Mapped[List["CabinetMember"]] = relationship(
        back_populates="mandate", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "politicoId",
            "cargo",
            "anoEleicao",
            "numeroMandato",
            name="uq_mandate_politician_office_year_term",
        ),
        Index("idx_mandate_office_year", "cargo", "anoEleicao"),
        Index("idx_mandate_dates", "dataInicio", "dataFim"),
        Index("idx_mandates_politico", "politicoId"),
        Index("idx_mandates_partido", "partidoId"),
        Index("idx_mandates_ano", "anoEleicao"),
    )


class CabinetMember(StagingBase):
    __tablename__ = "membros_gabinete"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        "mandatoId",
        UUID(as_uuid=True),
        ForeignKey("mandatos.id", ondelete="CASCADE"),
        nullable=False,
    )
    politician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "politicoId", UUID(as_uuid=True), ForeignKey("politicos.id"), nullable=True
    )
    occupant_name: Mapped[str] = mapped_column("nomeOcupante", String(255), nullable=False)
    ministry_name: Mapped[str] = mapped_column("ministerioNome", String(200), nullable=False)
    inauguration_date: Mapped[date] = mapped_column("dataPosse", Date, nullable=False)
    departure_date: Mapped[Optional[date]] = mapped_column("dataExoneracao", Date, nullable=True)
    is_economy_minister: Mapped[bool] = mapped_column("isMinistroEconomia", Boolean, default=False, nullable=False)

    mandate: Mapped["Mandate"] = relationship(back_populates="cabinet_members")
