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

from .base import StagingBase, TimeStampedModel
from .enums import (
    CasaLegislativaEnum,
    StatusTramitacaoEnum,
    TipoAutoriaEnum,
    TipoDeliberacaoEnum,
    TipoPresencaEnum,
    TipoProposicaoEnum,
    VotoOpcaoEnum,
)


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
    deliberacoes: Mapped[List["VotacaoProposicao"]] = relationship(
        "VotacaoProposicao",
        back_populates="proposicao",
        cascade="all, delete-orphan",
    )
    authors_detail: Mapped[List["PropositionAuthor"]] = relationship(
        "PropositionAuthor",
        back_populates="proposition",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_proposition_type_num_year", "tipo", "numero", "ano"),
        Index("idx_proposition_structural", "isReformaEstrutural"),
        Index("idx_proposicoes_autor", "autorPoliticoId"),
        Index("idx_proposicoes_ano", "ano"),
    )


class VotingSession(StagingBase):
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
    # Orientação da bancada "Governo" nesta votação (SIM, NAO, LIBERADO, ABSTENCAO, OBSTRUCAO) — nula quando a
    # fonte não registrou orientação do governo. `party_orientations` guarda o JSON {bancada: orientação}.
    government_orientation: Mapped[Optional[str]] = mapped_column("orientacaoGoverno", String(20), nullable=True)
    party_orientations: Mapped[Optional[str]] = mapped_column("orientacoesBancadas", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    proposition: Mapped["Proposition"] = relationship(back_populates="voting_sessions")
    votes: Mapped[List["ParliamentaryVote"]] = relationship(
        back_populates="voting_session", cascade="all, delete-orphan"
    )


class ParliamentaryVote(StagingBase):
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
    )
    party_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("partidos_politicos.id"),
        nullable=True,
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


class AttendanceRecord(StagingBase):
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


class PropositionAuthor(StagingBase):
    __tablename__ = "proposicoes_autores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposition_id: Mapped[uuid.UUID] = mapped_column(
        "proposicaoId",
        UUID(as_uuid=True),
        ForeignKey("proposicoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    politician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=True,
    )
    author_name: Mapped[str] = mapped_column("nomeAutor", Text, nullable=False)
    authorship_type: Mapped[TipoAutoriaEnum] = mapped_column(
        "tipoAutoria",
        Enum(TipoAutoriaEnum),
        default=TipoAutoriaEnum.AUTOR_PRINCIPAL,
        nullable=False,
    )
    order: Mapped[int] = mapped_column("ordem", Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    proposition: Mapped["Proposition"] = relationship(back_populates="authors_detail")
    politician: Mapped[Optional["Politician"]] = relationship("Politician", backref="propositions_authored")

    __table_args__ = (
        Index("idx_prop_autor_pol_tipo", "politicoId", "tipoAutoria"),
        Index("idx_prop_autor_prop_ordem", "proposicaoId", "ordem"),
    )


class VotacaoProposicao(StagingBase):
    __tablename__ = "votacoes_proposicao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposicao_id: Mapped[uuid.UUID] = mapped_column(
        "proposicao_id",
        UUID(as_uuid=True),
        ForeignKey("proposicoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_hora: Mapped[datetime] = mapped_column("data_hora", DateTime(timezone=True), nullable=False)
    local_deliberacao: Mapped[str] = mapped_column("local_deliberacao", String(100), nullable=False)
    tipo_deliberacao: Mapped[str] = mapped_column("tipo_deliberacao", String(30), nullable=False)
    resumo_decisao: Mapped[str] = mapped_column("resumo_decisao", Text, nullable=False)

    # Metadados adicionais para DELIBERACAO_COMISSAO (Módulo 3 - Especificação 6.3)
    nome_comissao: Mapped[Optional[str]] = mapped_column("nome_comissao", String(150), nullable=True)
    link_ata_reuniao: Mapped[Optional[str]] = mapped_column("link_ata_reuniao", Text, nullable=True)
    relator_nome: Mapped[Optional[str]] = mapped_column("relator_nome", String(150), nullable=True)
    parecer_relator_numero: Mapped[Optional[str]] = mapped_column("parecer_relator_numero", String(80), nullable=True)
    parecer_relator_texto: Mapped[Optional[str]] = mapped_column("parecer_relator_texto", Text, nullable=True)
    link_parecer_relator: Mapped[Optional[str]] = mapped_column("link_parecer_relator", Text, nullable=True)

    # Placar agregado
    total_sim: Mapped[int] = mapped_column("total_sim", Integer, default=0, nullable=False)
    total_nao: Mapped[int] = mapped_column("total_nao", Integer, default=0, nullable=False)
    total_abstencao: Mapped[int] = mapped_column("total_abstencao", Integer, default=0, nullable=False)
    total_obstrucao: Mapped[int] = mapped_column("total_obstrucao", Integer, default=0, nullable=False)
    aprovada: Mapped[bool] = mapped_column("aprovada", Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    proposicao: Mapped["Proposition"] = relationship("Proposition", back_populates="deliberacoes")
    votos_nominais: Mapped[List["VotoNominal"]] = relationship(
        "VotoNominal", back_populates="votacao", cascade="all, delete-orphan"
    )
    orientacoes_partidarias: Mapped[List["OrientacaoPartidaria"]] = relationship(
        "OrientacaoPartidaria", back_populates="votacao", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_votacoes_prop_id", "proposicao_id"),
        Index("idx_votacoes_prop_tipo", "tipo_deliberacao"),
        Index("idx_votacoes_prop_data", "data_hora"),
    )


class VotoNominal(StagingBase):
    __tablename__ = "votos_nominais"

    votacao_id: Mapped[uuid.UUID] = mapped_column(
        "votacao_id",
        UUID(as_uuid=True),
        ForeignKey("votacoes_proposicao.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parlamentar_id: Mapped[uuid.UUID] = mapped_column(
        "parlamentar_id",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    voto: Mapped[str] = mapped_column("voto", String(20), nullable=False)  # 'SIM', 'NAO', 'ABSTENCAO', 'OBSTRUCAO'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    votacao: Mapped["VotacaoProposicao"] = relationship("VotacaoProposicao", back_populates="votos_nominais")
    parlamentar: Mapped["Politician"] = relationship("Politician")

    __table_args__ = (
        Index("idx_votos_nominais_voto", "voto"),
        Index("idx_votos_nominais_parlamentar", "parlamentar_id"),
    )


class OrientacaoPartidaria(StagingBase):
    __tablename__ = "orientacoes_partidarias"

    votacao_id: Mapped[uuid.UUID] = mapped_column(
        "votacao_id",
        UUID(as_uuid=True),
        ForeignKey("votacoes_proposicao.id", ondelete="CASCADE"),
        primary_key=True,
    )
    partido_bancada: Mapped[str] = mapped_column("partido_bancada", String(50), primary_key=True)
    orientacao: Mapped[str] = mapped_column(
        "orientacao", String(20), nullable=False
    )  # 'SIM', 'NAO', 'LIBERADO', 'OBSTRUCAO'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    votacao: Mapped["VotacaoProposicao"] = relationship("VotacaoProposicao", back_populates="orientacoes_partidarias")

    __table_args__ = (Index("idx_orientacoes_partido", "partido_bancada"),)
