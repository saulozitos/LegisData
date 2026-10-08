from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class MandatePerformanceSchema(BaseModel):
    id_mandato: str
    presidente: str
    partido: str
    data_inicio: str
    data_fim: str
    status_mandato: str
    anos_cobertos: str
    ipca_acumulado_pct: float
    ipca_pos_real_pct: float
    pib_crescimento_acumulado_pct: float
    pib_medio_anual_pct: float
    cambio_inicial_usd_brl: Optional[float] = None
    cambio_final_usd_brl: Optional[float] = None
    cambio_variacao_pct: Optional[float] = None
    divida_liquida_inicial_pct_pib: Optional[float] = None
    divida_liquida_final_pct_pib: Optional[float] = None
    divida_liquida_delta_pct: Optional[float] = None
    salario_minimo_inicial_brl: Optional[float] = None
    salario_minimo_final_brl: Optional[float] = None
    salario_minimo_inicial_usd: Optional[float] = None
    salario_minimo_final_usd: Optional[float] = None
    ministros_fazenda_principais: List[str]
    marcos_economicos_principais: List[str]


class WagePoint(BaseModel):
    ano: int
    presidente_dominante: str
    salario_minimo_brl: float
    salario_parlamentar_brl: float
    multiplo_salarios_minimos: float
    ipca_acumulado_ano_pct: Optional[float] = None
    indice_salario_minimo_base100: float
    indice_salario_parlamentar_base100: float
    indice_ipca_base100: float


class MinimumWageVoteRecord(BaseModel):
    deputado_nome: str
    partido_sigla: str
    uf: str
    cargo: str
    voto: str # SIM, NAO, ABSTENCAO, OBSTRUCAO, AUSENTE
    foto_url: Optional[str] = None


class MinimumWageVotingSummary(BaseModel):
    proposicao_titulo: str
    ementa: str
    data_votacao: str
    casa: str
    placar: Dict[str, int]
    votos_amostra: List[MinimumWageVoteRecord]


class WageDisparityResponse(BaseModel):
    serie_historica: List[WagePoint]
    votacao_salario_minimo: MinimumWageVotingSummary
    estatisticas_disparidade: Dict[str, Any]


class LeaderProfile(BaseModel):
    nome: str
    partido: str
    uf: str
    periodo: str
    foto_url: Optional[str] = None


class PartySeat(BaseModel):
    partido: str
    cadeiras: int
    percentual: float
    alinhamento: str # "BASE_GOVERNO", "INDEPENDENTE_CENTRO", "OPOSICAO"
    cor_hex: str


class ChamberComposition(BaseModel):
    total_cadeiras: int
    presidentes: List[LeaderProfile]
    bancadas: List[PartySeat]
    governabilidade: Dict[str, Any]


class CongressCompositionResponse(BaseModel):
    mandato_id: str
    presidente_republica: str
    periodo: str
    camara: ChamberComposition
    senado: ChamberComposition


class StateTransferItem(BaseModel):
    uf: str
    estado_nome: str
    regiao: str
    area_tematica: str
    valor_pago_brl: float
    populacao_estimada: int
    valor_per_capita_brl: float


class FederalTransfersResponse(BaseModel):
    # Os valores vêm de repasses_federais_uf.json, gerado por modelo (OrcamentoExtractor).
    dados_estimados: bool = True
    mandato_id: str
    periodo: str
    total_repassado_brl: float
    areas_resumo: Dict[str, float]
    regioes_resumo: Dict[str, float]
    por_uf: List[StateTransferItem]
