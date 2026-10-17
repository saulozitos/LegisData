"""
API Oficial de Emendas Orçamentárias — LegisData.

Fornece consulta acessível, humanizada e estruturada das emendas parlamentares do Orçamento Federal:
- Classificação por tipo de autor: Individual (Político Específico), Bancada Estadual (Coletiva),
  Comissão Temática (Institucional) e Relator-Geral.
- Dicionário de termos que traduz a linguagem orçamentária técnica em termos do dia a dia do cidadão.
- Endpoints de resumo consolidado, busca por localidade (cidade/UF) e busca por autor.
"""

from typing import Any, Dict

from app.core.database import get_db
from app.services import emendas_service
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/resumo")
def get_emendas_resumo(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Panorama geral das emendas: valores reservados (empenhados) e entregues (pagos), por tipo de autor, área, ano e UF."""
    return emendas_service.resumo(db)


@router.get("/localidade/{localidade}")
def get_emendas_por_localidade(
    localidade: str,
    limit: int = Query(50, ge=1, le=200, description="Quantidade máxima de emendas na lista detalhada"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Emendas destinadas a uma cidade ou estado (ex.: 'MG', 'Belo Horizonte'), com a divisão por áreas."""
    return emendas_service.por_localidade(db, localidade, limit)


@router.get("/autor/{autor}")
def get_emendas_por_autor(
    autor: str,
    limit: int = Query(50, ge=1, le=200, description="Quantidade máxima de emendas na lista detalhada"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Emendas de um autor (parlamentar, comissão ou bancada): perfil institucional, totais e destinos."""
    return emendas_service.por_autor(db, autor, limit)
