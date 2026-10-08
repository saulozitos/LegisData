import hmac
from typing import List, Optional

from app.core.config import settings
from app.services.cidadania_service import get_consultas_publicas
from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, Field

router = APIRouter()


class ConsultaPublicaItem(BaseModel):
    id_externo: str = Field(..., description="Identificador único da matéria no órgão de origem")
    casa: str = Field(..., description="Casa Legislativa (Senado ou Câmara)")
    sigla_projeto: str = Field(..., description="Identificação oficial do projeto (ex.: PL 2630/2020)")
    ementa: str = Field(..., description="Resumo explicativo do projeto de lei ou PEC")
    link_oficial_votacao: str = Field(..., description="URL oficial nos portais e-Cidadania ou e-Democracia")
    link_tramitacao_oficial: Optional[str] = Field(
        None, description="URL da ficha de tramitação legislativa oficial permanente"
    )
    em_votacao_aberta: bool = Field(
        True,
        description="Indica se a consulta/votação está aberta atualmente para participação popular",
    )
    votos_sim: Optional[int] = Field(None, description="Total de votos favoráveis registrados na consulta popular")
    votos_nao: Optional[int] = Field(None, description="Total de votos contrários registrados na consulta popular")
    total_votos: Optional[int] = Field(None, description="Soma de votos sim e não")
    percentual_sim: Optional[float] = Field(None, description="Percentual de aprovação popular (%)")
    percentual_nao: Optional[float] = Field(None, description="Percentual de rejeição popular (%)")
    tema: Optional[str] = Field(None, description="Área temática ou eixo do projeto")
    status: Optional[str] = Field(None, description="Situação atual da tramitação")
    autor: Optional[str] = Field(None, description="Parlamentar ou comissão proponente")
    data_apresentacao: Optional[str] = Field(None, description="Data de apresentação da proposta")
    destaque: Optional[bool] = Field(False, description="Indica se é um tema de altíssimo impacto nacional")
    fonte_dados: Optional[str] = Field(
        None, description="Origem do registro: 'tempo_real' (portal oficial) ou 'curadoria' (placar de referência)"
    )


@router.get(
    "/consultas",
    response_model=List[ConsultaPublicaItem],
    summary="Listar Consultas Públicas e Enquetes Populares em Andamento",
    description=(
        "Retorna proposições legislativas abertas para participação popular e votação direta "
        "nos portais oficiais do Senado Federal (e-Cidadania) e da Câmara dos Deputados (e-Democracia). "
        "Resultados cacheados em memória por 1 hora para resiliência e proteção das APIs governamentais."
    ),
)
def listar_consultas(
    casa: Optional[str] = Query(None, max_length=20, description="Filtrar por casa legislativa: 'Senado' ou 'Câmara'"),
    force_refresh: bool = Query(
        False,
        description="Forçar renovação do cache (somente com o header X-Admin-Token válido; ignorado para anônimos)",
    ),
    x_admin_token: Optional[str] = Header(None),
):
    # A renovação forçada dispara dezenas de chamadas a APIs governamentais: restrita a quem tem o token
    allow_refresh = bool(
        force_refresh
        and settings.ADMIN_REFRESH_TOKEN
        and x_admin_token
        and hmac.compare_digest(x_admin_token, settings.ADMIN_REFRESH_TOKEN)
    )
    consultas = get_consultas_publicas(force_refresh=allow_refresh)

    if casa:
        casa_filtro = casa.strip().lower()
        consultas = [c for c in consultas if (c.get("casa") or "").lower() == casa_filtro]

    return consultas
