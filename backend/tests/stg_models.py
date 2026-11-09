"""
Modelos declarativos das tabelas de entrada da fusão, SÓ para os testes do backend.

Em produção a fusão (`etl.merge_cadastro`, `etl.merge_legislativo`) lê tabelas TEMPORÁRIAS de trabalho (`w_politicos`,
`w_mandatos`...) que `etl.preparar_staging` monta a partir das tabelas planas de `stg` e de `core`/`leg`. Nos testes essas
oito são tabelas comuns em `public` (criadas só no banco de teste, ver `conftest`): o teste semeia linhas com objetos
(`Politician(...)`, `db.add`) e chama `merge_staging(db, preparar=False)`; sem tabela temporária no caminho, a fusão acha as
persistentes pelo `search_path`. As cinco tabelas congeladas de `stg` (autores, presença, votações e votos nominais do legado)
são as migradas de verdade. A API nunca lê nada disso. A guarda de deriva (`test_staging_orm_models_match_the_migrated_database`)
confere os modelos contra o schema migrado e contra `etl.criar_trabalho`.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from app.models.enums import (
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    EspectroPoliticoEnum,
    MotivoDesfiliacaoEnum,
    StatusMandatoEnum,
    StatusTramitacaoEnum,
    TipoAutoriaEnum,
    TipoEsferaEnum,
    TipoPresencaEnum,
    TipoProposicaoEnum,
    VotoOpcaoEnum,
)
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class StagingBase(DeclarativeBase):
    """Tabelas de entrada da fusão: `w_*` em `public` (só nos testes) e as cinco congeladas de `stg`."""

    metadata = MetaData()


class StagingTimeStampedModel(StagingBase):
    """Abstract staging model (schema `stg`) adding created_at and updated_at timestamps."""

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Politician(StagingTimeStampedModel):
    __tablename__ = "w_politicos"

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
    __tablename__ = "w_partidos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    acronym: Mapped[str] = mapped_column("sigla", String(20), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column("nomeCompleto", String(255), nullable=False)
    electoral_number: Mapped[Optional[int]] = mapped_column("numeroEleitoral", Integer, unique=True, nullable=True)
    foundation_date: Mapped[Optional[date]] = mapped_column("dataFundacao", Date, nullable=True)
    dissolution_date: Mapped[Optional[date]] = mapped_column("dataExtincao", Date, nullable=True)
    successor_party_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "partidoSucessorId",
        UUID(as_uuid=True),
        ForeignKey("w_partidos.id"),
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
    __tablename__ = "w_filiacoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("w_politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("w_partidos.id"),
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
    # a que já está em `core.filiacao` ganha o empate de início (ver a fusão do staging, que a migração 0039 removeu); o teste semeia sempre sem ela
    survivor: Mapped[bool] = mapped_column(
        "sobrevivente", Boolean, default=False, server_default="false", nullable=False
    )

    # Relationships
    politician: Mapped["Politician"] = relationship(back_populates="affiliations")
    party: Mapped["PoliticalParty"] = relationship(back_populates="affiliations")

    __table_args__ = (
        Index("idx_affiliation_politician_date", "politicoId", "dataFiliacao"),
        Index("idx_affiliation_politician", "politicoId"),
        Index("idx_affiliation_party", "partidoId"),
    )


class Mandate(StagingTimeStampedModel):
    __tablename__ = "w_mandatos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("w_politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("w_partidos.id"),
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
    __tablename__ = "w_gabinete"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        "mandatoId",
        UUID(as_uuid=True),
        ForeignKey("w_mandatos.id", ondelete="CASCADE"),
        nullable=False,
    )
    politician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "politicoId", UUID(as_uuid=True), ForeignKey("w_politicos.id"), nullable=True
    )
    occupant_name: Mapped[str] = mapped_column("nomeOcupante", String(255), nullable=False)
    ministry_name: Mapped[str] = mapped_column("ministerioNome", String(200), nullable=False)
    inauguration_date: Mapped[date] = mapped_column("dataPosse", Date, nullable=False)
    departure_date: Mapped[Optional[date]] = mapped_column("dataExoneracao", Date, nullable=True)
    is_economy_minister: Mapped[bool] = mapped_column("isMinistroEconomia", Boolean, default=False, nullable=False)

    mandate: Mapped["Mandate"] = relationship(back_populates="cabinet_members")


class Proposition(StagingTimeStampedModel):
    __tablename__ = "w_proposicoes"

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
        "autorPoliticoId", UUID(as_uuid=True), ForeignKey("w_politicos.id"), nullable=True
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
    __tablename__ = "w_sessoes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[Optional[str]] = mapped_column("idExterno", String(100), unique=True, nullable=True)
    proposition_id: Mapped[uuid.UUID] = mapped_column(
        "proposicaoId",
        UUID(as_uuid=True),
        ForeignKey("w_proposicoes.id", ondelete="CASCADE"),
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
    __tablename__ = "w_votos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voting_session_id: Mapped[uuid.UUID] = mapped_column(
        "sessaoVotacaoId",
        UUID(as_uuid=True),
        ForeignKey("w_sessoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("w_politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("w_partidos.id"),
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
        ForeignKey("w_politicos.id", ondelete="CASCADE"),
        nullable=False,
    )
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        "mandatoId",
        UUID(as_uuid=True),
        ForeignKey("w_mandatos.id", ondelete="CASCADE"),
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

    __table_args__ = (Index("idx_attendance_politician_date", "politicoId", "dataSessao"), {"schema": "stg"})


class PropositionAuthor(StagingBase):
    __tablename__ = "proposicoes_autores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposition_id: Mapped[uuid.UUID] = mapped_column(
        "proposicaoId",
        UUID(as_uuid=True),
        ForeignKey("w_proposicoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    politician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("w_politicos.id", ondelete="CASCADE"),
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
        {"schema": "stg"},
    )


class VotacaoProposicao(StagingBase):
    __tablename__ = "votacoes_proposicao"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposicao_id: Mapped[uuid.UUID] = mapped_column(
        "proposicao_id",
        UUID(as_uuid=True),
        ForeignKey("w_proposicoes.id", ondelete="CASCADE"),
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
        {"schema": "stg"},
    )


class VotoNominal(StagingBase):
    __tablename__ = "votos_nominais"

    votacao_id: Mapped[uuid.UUID] = mapped_column(
        "votacao_id",
        UUID(as_uuid=True),
        ForeignKey("stg.votacoes_proposicao.id", ondelete="CASCADE"),
        primary_key=True,
    )
    parlamentar_id: Mapped[uuid.UUID] = mapped_column(
        "parlamentar_id",
        UUID(as_uuid=True),
        ForeignKey("w_politicos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    voto: Mapped[str] = mapped_column("voto", String(20), nullable=False)  # 'SIM', 'NAO', 'ABSTENCAO', 'OBSTRUCAO'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    votacao: Mapped["VotacaoProposicao"] = relationship("VotacaoProposicao", back_populates="votos_nominais")
    parlamentar: Mapped["Politician"] = relationship("Politician")

    __table_args__ = (
        Index("idx_votos_nominais_voto", "voto"),
        Index("idx_votos_nominais_parlamentar", "parlamentar_id"),
        {"schema": "stg"},
    )


class OrientacaoPartidaria(StagingBase):
    __tablename__ = "orientacoes_partidarias"

    votacao_id: Mapped[uuid.UUID] = mapped_column(
        "votacao_id",
        UUID(as_uuid=True),
        ForeignKey("stg.votacoes_proposicao.id", ondelete="CASCADE"),
        primary_key=True,
    )
    partido_bancada: Mapped[str] = mapped_column("partido_bancada", String(50), primary_key=True)
    orientacao: Mapped[str] = mapped_column(
        "orientacao", String(20), nullable=False
    )  # 'SIM', 'NAO', 'LIBERADO', 'OBSTRUCAO'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    votacao: Mapped["VotacaoProposicao"] = relationship("VotacaoProposicao", back_populates="orientacoes_partidarias")

    __table_args__ = (Index("idx_orientacoes_partido", "partido_bancada"), {"schema": "stg"})
