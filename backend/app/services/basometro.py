"""
Basômetro: alinhamento de um parlamentar à orientação do GOVERNO nas votações nominais em plenário.

Mede apenas votações em que a fonte oficial registrou a orientação da bancada "Governo" como SIM ou NÃO
(orientações "Liberado"/ausentes não entram: não há linha de governo para seguir ou divergir). Sem baseline por
partido e sem valor padrão: com amostra insuficiente o indicador fica explicitamente indisponível.
"""

from typing import Any, Dict, Optional

from app.models.leg import Votacao, Voto
from sqlalchemy import func
from sqlalchemy.orm import Session

MIN_VOTACOES_AMOSTRA = 10

# Votos que contam como posição do parlamentar (AUSENTE e Art. 17 não são posição).
_VOTOS_COM_POSICAO = {"SIM", "NAO", "ABSTENCAO", "OBSTRUCAO"}

_METODOLOGIA = (
    "Percentual de votações nominais em plenário (Câmara e Senado) em que o voto coincidiu com a orientação da "
    "bancada do Governo (SIM ou NÃO). Abstenção e obstrução contam como divergência; ausência, Art. 17 e "
    "votações com orientação 'Liberado' ou sem orientação do governo ficam de fora. "
    f"Exige ao menos {MIN_VOTACOES_AMOSTRA} votações com orientação."
)


def classificar_governismo(taxa: float) -> str:
    if taxa >= 80.0:
        return "Governista Fiel"
    if taxa >= 60.0:
        return "Base Aliada Moderada"
    if taxa >= 40.0:
        return "Independente / Centro"
    if taxa >= 20.0:
        return "Oposição Moderada"
    return "Oposição Firme"


def calcular_basometro(
    db: Session,
    pessoa_id: Any,
    partido_sigla: Optional[str],
    votos_sim: int = 0,
    votos_nao: int = 0,
) -> Dict[str, Any]:
    linhas = (
        db.query(Votacao.orientacao_governo, Voto.opcao_codigo, func.count())
        .join(Votacao, Voto.votacao_id == Votacao.id)
        .filter(Voto.pessoa_id == pessoa_id, Votacao.orientacao_governo.in_(("SIM", "NAO")))
        .group_by(Votacao.orientacao_governo, Voto.opcao_codigo)
        .all()
    )
    if pessoa_id is None:
        linhas = []
    alinhados = divergentes = 0
    for orientacao, opcao, qtd in linhas:
        if opcao not in _VOTOS_COM_POSICAO:
            continue
        if opcao == orientacao:
            alinhados += qtd
        else:
            divergentes += qtd

    analisadas = alinhados + divergentes
    suficiente = analisadas >= MIN_VOTACOES_AMOSTRA
    taxa = round(alinhados / analisadas * 100, 1) if suficiente else None
    return {
        "taxa_governismo_pct": taxa,
        "total_votacoes_analisadas": analisadas,
        "votos_alinhados": alinhados if analisadas else None,
        "votos_divergentes": divergentes if analisadas else None,
        "votos_sim": votos_sim,
        "votos_nao": votos_nao,
        "classificacao": classificar_governismo(taxa) if taxa is not None else None,
        "dados_suficientes": suficiente,
        "amostra_minima": MIN_VOTACOES_AMOSTRA,
        "metodologia": _METODOLOGIA,
        "partido_sigla": partido_sigla,
    }
