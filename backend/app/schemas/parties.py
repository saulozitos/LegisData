from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PartyPilares(BaseModel):
    fidelidade_partidaria_pct: Optional[float] = None  # None: sem votação nominal com orientação no período
    taxa_eficacia_pct: float
    total_relatorias: int
    volume_relatorias: float
    assinaturas_apoio_quorum: int = 0  # assinaturas de apoio a PEC (peso reduzido, fora da autoria efetiva)


class QuadranteEficiencia(BaseModel):
    codigo: str
    titulo: str
    descricao: str


class PartyIPPMRankingItem(BaseModel):
    posicao: int
    partido_id: str
    sigla: str
    nome_completo: str
    numero_eleitoral: Optional[int] = None
    espectro_politico: str
    bloco_politico: str
    cor_hex: str
    logo_url: Optional[str] = None
    total_cadeiras_ativas: int
    cadeiras_dia_equivalentes: float
    parlamentares_produtivos: int
    pontuacao_bruta_ialp: float
    ippm_score_medio: float
    projetos_apresentados: int
    projetos_aprovados: int
    pilares: PartyPilares
    quadrante_eficiencia: QuadranteEficiencia


class IPPMRankingPeriodo(BaseModel):
    ano: int
    data_inicio: str
    data_fim: str
    casa: str
    bloco: str
    espectro: str
    # Preenchido quando o período não pode ser calculado (ex.: sem histórico de cadeiras na fonte)
    aviso: Optional[str] = None


class HighlightParty(BaseModel):
    sigla: str
    ippm_score: Optional[float] = None
    taxa_eficacia: Optional[float] = None
    fidelidade_pct: Optional[float] = None
    cor_hex: str


class IPPMRankingResumo(BaseModel):
    total_partidos: int
    media_ippm_geral: float
    partido_mais_produtivo: Optional[HighlightParty] = None
    partido_mais_eficaz: Optional[HighlightParty] = None
    partido_mais_coeso: Optional[HighlightParty] = None


class IPPMRankingResponse(BaseModel):
    periodo: IPPMRankingPeriodo
    resumo_geral: IPPMRankingResumo
    ranking: List[PartyIPPMRankingItem]


class PartyMandateTimelineItem(BaseModel):
    id: str
    politico_id: str
    nome_eleitoral: str
    foto_url: Optional[str] = None
    casa: str
    situacao: str
    data_inicio: str
    data_fim: Optional[str] = None
    observacao: Optional[str] = None


class PartyMandateTimelineResponse(BaseModel):
    partido: str
    total_membros_registrados: int
    titulares_exercicio: List[PartyMandateTimelineItem]
    ministros_licenciados: List[PartyMandateTimelineItem]
    suplentes_ativos: List[PartyMandateTimelineItem]


class CronLogItem(BaseModel):
    id: str
    data_execucao: str
    status_execucao: str
    registros_atualizados: int
    tempo_processamento_segundos: int
    erro_mensagem: Optional[str] = None
    etapa: Optional[str] = None


class PartyEvolutionPoint(BaseModel):
    ano: int
    ippm: float
    pontuacao_bruta_ialp: float
    cadeiras_dia_equivalentes: float
    parlamentares: int
    projetos_apresentados: int
    projetos_aprovados: int
    taxa_eficacia_pct: float


class PartyEvolutionSeries(BaseModel):
    sigla: str
    nome_completo: str
    cor_hex: str
    serie: List[PartyEvolutionPoint]


class IPPMEvolutionPeriod(BaseModel):
    ano_inicio: int
    ano_fim: int
    casa: str


class IPPMEvolutionResponse(BaseModel):
    periodo: IPPMEvolutionPeriod
    anos: List[int]
    partidos: List[PartyEvolutionSeries]
