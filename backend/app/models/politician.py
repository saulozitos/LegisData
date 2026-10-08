import enum
import uuid
from datetime import date, datetime
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

from .base import Base, TimeStampedModel


class CargoPoliticoEnum(str, enum.Enum):
    PRESIDENTE = "PRESIDENTE"
    VICE_PRESIDENTE = "VICE_PRESIDENTE"
    MINISTRO_DE_ESTADO = "MINISTRO_DE_ESTADO"
    GOVERNADOR = "GOVERNADOR"
    VICE_GOVERNADOR = "VICE_GOVERNADOR"
    SENADOR = "SENADOR"
    DEPUTADO_FEDERAL = "DEPUTADO_FEDERAL"
    DEPUTADO_ESTADUAL = "DEPUTADO_ESTADUAL"


class TipoEsferaEnum(str, enum.Enum):
    FEDERAL = "FEDERAL"
    ESTADUAL = "ESTADUAL"
    MUNICIPAL = "MUNICIPAL"


class StatusMandatoEnum(str, enum.Enum):
    TITULAR_ATIVO = "TITULAR_ATIVO"
    CONCLUIDO = "CONCLUIDO"
    RENUNCIA = "RENUNCIA"
    IMPEACHMENT = "IMPEACHMENT"
    CASSADO = "CASSADO"
    LICENCIADO = "LICENCIADO"
    FALECIDO = "FALECIDO"
    SUPLENTE_EM_EXERCICIO = "SUPLENTE_EM_EXERCICIO"


class MotivoDesfiliacaoEnum(str, enum.Enum):
    MUDANCA_VOLUNTARIA = "MUDANCA_VOLUNTARIA"
    FUSAO_OU_INCORPORACAO = "FUSAO_OU_INCORPORACAO"
    EXPULSAO = "EXPULSAO"
    CRIACAO_DE_NOVA_LEGENDA = "CRIACAO_DE_NOVA_LEGENDA"
    EXTINCAO_DO_PARTIDO = "EXTINCAO_DO_PARTIDO"


class EspectroPoliticoEnum(str, enum.Enum):
    ESQUERDA = "ESQUERDA"
    CENTRO_ESQUERDA = "CENTRO_ESQUERDA"
    CENTRO = "CENTRO"
    CENTRO_DIREITA = "CENTRO_DIREITA"
    DIREITA = "DIREITA"


class Politician(TimeStampedModel):
    __tablename__ = "politicos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    civil_name: Mapped[str] = mapped_column("nomeCivil", String(255), nullable=False)
    electoral_name: Mapped[str] = mapped_column("nomeEleitoral", String(150), nullable=False, index=True)
    cpf: Mapped[Optional[str]] = mapped_column(String(14), unique=True, nullable=True)
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
    remunerations: Mapped[List["PoliticianRemuneration"]] = relationship(
        back_populates="politician", cascade="all, delete-orphan"
    )
    propositions: Mapped[List["Proposition"]] = relationship("Proposition", back_populates="author_politician")
    votes: Mapped[List["ParliamentaryVote"]] = relationship("ParliamentaryVote", back_populates="politician")
    attendances: Mapped[List["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="politician")
    asset_declarations: Mapped[List["PoliticianAssetDeclaration"]] = relationship(
        "PoliticianAssetDeclaration",
        back_populates="politician",
        cascade="all, delete-orphan",
    )
    despesas_cota: Mapped[List["DespesaCota"]] = relationship(
        "DespesaCota", back_populates="politician", cascade="all, delete-orphan"
    )
    emendas: Mapped[List["EmendaParlamentar"]] = relationship(
        "EmendaParlamentar", back_populates="politician", cascade="all, delete-orphan"
    )
    certidoes_judiciais: Mapped[List["CertidaoJudicial"]] = relationship(
        "CertidaoJudicial", back_populates="politician", cascade="all, delete-orphan"
    )
    doacoes_campanha: Mapped[List["DoacaoCampanha"]] = relationship(
        "DoacaoCampanha", back_populates="politician", cascade="all, delete-orphan"
    )
    processos_judiciais: Mapped[List["ProcessoJudicial"]] = relationship(
        "ProcessoJudicial", back_populates="politician", cascade="all, delete-orphan"
    )


class PoliticalParty(TimeStampedModel):
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
    predecessors: Mapped[List["PoliticalParty"]] = relationship(
        "PoliticalParty", backref="successor_party", remote_side=[id]
    )


class PartyAffiliation(Base):
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
    created_at: Mapped[datetime] = mapped_column(Date, default=datetime.utcnow)

    # Relationships
    politician: Mapped["Politician"] = relationship(back_populates="affiliations")
    party: Mapped["PoliticalParty"] = relationship(back_populates="affiliations")

    __table_args__ = (
        Index("idx_affiliation_politician_date", "politicoId", "dataFiliacao"),
        Index("idx_affiliation_politician", "politicoId"),
        Index("idx_affiliation_party", "partidoId"),
    )


class Mandate(TimeStampedModel):
    __tablename__ = "mandatos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    party_id: Mapped[uuid.UUID] = mapped_column(
        "partidoId",
        UUID(as_uuid=True),
        ForeignKey("partidos_politicos.id"),
        nullable=False,
        index=True,
    )
    office: Mapped[CargoPoliticoEnum] = mapped_column("cargo", Enum(CargoPoliticoEnum), nullable=False)
    sphere: Mapped[TipoEsferaEnum] = mapped_column(
        "esfera", Enum(TipoEsferaEnum), default=TipoEsferaEnum.FEDERAL, nullable=False
    )
    jurisdiction_state: Mapped[str] = mapped_column("ufJurisdicao", String(2), default="BR", nullable=False)
    election_year: Mapped[int] = mapped_column("anoEleicao", Integer, nullable=False, index=True)
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
    remunerations: Mapped[List["PoliticianRemuneration"]] = relationship(
        back_populates="mandate", cascade="all, delete-orphan"
    )
    attendances: Mapped[List["AttendanceRecord"]] = relationship("AttendanceRecord", back_populates="mandate")
    cabinet_members: Mapped[List["CabinetMember"]] = relationship(
        back_populates="mandate", cascade="all, delete-orphan"
    )
    economic_performance: Mapped[Optional["MandateEconomicPerformance"]] = relationship(
        "MandateEconomicPerformance", back_populates="mandate", uselist=False
    )

    __table_args__ = (
        Index("idx_mandate_office_year", "cargo", "anoEleicao"),
        Index("idx_mandate_dates", "dataInicio", "dataFim"),
        Index("idx_mandates_politico", "politicoId"),
        Index("idx_mandates_partido", "partidoId"),
        Index("idx_mandates_ano", "anoEleicao"),
    )


class CabinetMember(Base):
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


class PoliticianRemuneration(Base):
    __tablename__ = "remuneracoes_politicos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mandate_id: Mapped[uuid.UUID] = mapped_column(
        "mandatoId",
        UUID(as_uuid=True),
        ForeignKey("mandatos.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference_year: Mapped[int] = mapped_column("anoReferencia", Integer, nullable=False, index=True)
    reference_month: Mapped[int] = mapped_column("mesReferencia", Integer, nullable=False)
    gross_salary: Mapped[Decimal] = mapped_column("salarioBruto", Numeric(12, 2), nullable=False)
    net_salary: Mapped[Decimal] = mapped_column("salarioLiquido", Numeric(12, 2), nullable=False)
    parliamentary_quota_ceap: Mapped[Decimal] = mapped_column(
        "cotaParlamentarCeap", Numeric(12, 2), default=0.00, nullable=False
    )
    housing_allowance: Mapped[Decimal] = mapped_column("auxilioMoradia", Numeric(12, 2), default=0.00, nullable=False)
    other_benefits: Mapped[Decimal] = mapped_column("outrosBeneficios", Numeric(12, 2), default=0.00, nullable=False)
    data_source: Mapped[str] = mapped_column("fonteDados", String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(Date, default=datetime.utcnow)

    politician: Mapped["Politician"] = relationship(back_populates="remunerations")
    mandate: Mapped["Mandate"] = relationship(back_populates="remunerations")

    __table_args__ = (
        UniqueConstraint(
            "politicoId",
            "anoReferencia",
            "mesReferencia",
            name="uq_politician_year_month",
        ),
        Index("idx_remuneracoes_politico", "politicoId"),
        Index("idx_remuneracoes_ano", "anoReferencia"),
    )


class PoliticianAssetDeclaration(TimeStampedModel):
    __tablename__ = "declaracoes_patrimonio"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    election_year: Mapped[int] = mapped_column("anoEleicao", Integer, nullable=False, index=True)
    declared_value_brl: Mapped[Decimal] = mapped_column("valorDeclaradoBrl", Numeric(15, 2), nullable=False)
    asset_details: Mapped[Optional[str]] = mapped_column("detalhesBens", Text, nullable=True)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="asset_declarations")

    __table_args__ = (UniqueConstraint("politicoId", "anoEleicao", name="uq_politician_election_asset"),)


class DespesaCota(TimeStampedModel):
    __tablename__ = "despesas_cota_parlamentar"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column("ano", Integer, nullable=False, index=True)
    month: Mapped[Optional[int]] = mapped_column("mes", Integer, nullable=True)
    expense_type: Mapped[str] = mapped_column("tipoDespesa", String(255), nullable=False, index=True)
    net_value: Mapped[Decimal] = mapped_column("valorLiquido", Numeric(12, 2), nullable=False)
    supplier_name: Mapped[str] = mapped_column("nomeFornecedor", String(255), nullable=False)
    supplier_cnpj_cpf: Mapped[Optional[str]] = mapped_column("cnpjCpfFornecedor", String(30), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column("dataEmissao", Date, nullable=True)
    document_url: Mapped[Optional[str]] = mapped_column("documentoUrl", Text, nullable=True)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="despesas_cota")

    __table_args__ = (
        Index("idx_despesa_cota_politico", "politicoId"),
        Index("idx_despesa_cota_ano", "ano"),
        Index("idx_despesa_cota_tipo", "tipoDespesa"),
        Index("idx_despesa_politico_ano", "politicoId", "ano"),
    )


class EmendaParlamentar(TimeStampedModel):
    __tablename__ = "emendas_parlamentares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column("ano", Integer, nullable=False, index=True)
    amendment_code: Mapped[Optional[str]] = mapped_column("codigoEmenda", String(50), nullable=True)
    amendment_type: Mapped[str] = mapped_column("tipoEmenda", String(50), nullable=False)
    committed_value: Mapped[Decimal] = mapped_column("valorEmpenhado", Numeric(15, 2), nullable=False)
    paid_value: Mapped[Decimal] = mapped_column("valorPago", Numeric(15, 2), nullable=False)
    destination_locality: Mapped[str] = mapped_column("localidadeDestino", String(150), nullable=False)
    function_area: Mapped[Optional[str]] = mapped_column("funcao", String(100), nullable=True)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="emendas")

    __table_args__ = (
        Index("idx_emenda_politico", "politicoId"),
        Index("idx_emenda_ano", "ano"),
        Index("idx_emenda_tipo", "tipoEmenda"),
        Index("idx_emenda_politico_ano", "politicoId", "ano"),
    )


class CertidaoJudicial(TimeStampedModel):
    __tablename__ = "certidoes_judiciais"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    court_agency: Mapped[str] = mapped_column("orgao", String(100), nullable=False)
    certificate_type: Mapped[str] = mapped_column("tipoCertidao", String(50), nullable=False)
    status: Mapped[str] = mapped_column("statusFicha", String(50), nullable=False)
    details: Mapped[Optional[str]] = mapped_column("detalhes", Text, nullable=True)
    process_number: Mapped[Optional[str]] = mapped_column("numeroProcesso", String(100), nullable=True)
    issue_date: Mapped[Optional[str]] = mapped_column("dataEmissao", String(50), nullable=True)
    proof_url: Mapped[Optional[str]] = mapped_column("linkComprovacao", String(500), nullable=True)
    auth_code: Mapped[Optional[str]] = mapped_column("codigoAutenticidade", String(100), nullable=True)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="certidoes_judiciais")

    __table_args__ = (
        Index("idx_certidao_politico", "politicoId"),
        Index("idx_certidao_status", "statusFicha"),
    )


class DoacaoCampanha(TimeStampedModel):
    __tablename__ = "doacoes_campanha"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    election_year: Mapped[int] = mapped_column("anoEleicao", Integer, nullable=False, index=True)
    donor_name: Mapped[str] = mapped_column("nomeDoador", String(255), nullable=False)
    donor_cpf_cnpj: Mapped[Optional[str]] = mapped_column("cpfCnpjDoador", String(30), nullable=True)
    amount_donated: Mapped[Decimal] = mapped_column("valorDoado", Numeric(15, 2), nullable=False)
    donation_type: Mapped[Optional[str]] = mapped_column("tipoReceita", String(100), nullable=True)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="doacoes_campanha")

    __table_args__ = (
        Index("idx_doacao_politico", "politicoId"),
        Index("idx_doacao_ano", "anoEleicao"),
        Index("idx_doacao_politico_ano", "politicoId", "anoEleicao"),
    )


class ProcessoJudicial(TimeStampedModel):
    __tablename__ = "processos_judiciais"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    politician_id: Mapped[uuid.UUID] = mapped_column(
        "politicoId",
        UUID(as_uuid=True),
        ForeignKey("politicos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_number: Mapped[str] = mapped_column("numeroProcesso", String(100), nullable=False)
    court_agency: Mapped[str] = mapped_column("tribunal", String(100), nullable=False)
    process_date: Mapped[str] = mapped_column("dataProcesso", String(50), nullable=False)
    case_class: Mapped[str] = mapped_column("classeAssunto", String(255), nullable=False)
    description: Mapped[str] = mapped_column("descricao", Text, nullable=False)
    legal_status: Mapped[str] = mapped_column("situacaoJuridica", Text, nullable=False)
    proof_url: Mapped[str] = mapped_column("linkComprovacao", String(500), nullable=False)
    status_summary: Mapped[str] = mapped_column("statusResumo", String(50), nullable=False)
    is_declared_tse: Mapped[bool] = mapped_column("declaradoTse", Boolean, default=True, nullable=False)

    politician: Mapped["Politician"] = relationship("Politician", back_populates="processos_judiciais")

    __table_args__ = (
        Index("idx_processo_politico", "politicoId"),
        Index("idx_processo_numero", "numeroProcesso"),
    )
