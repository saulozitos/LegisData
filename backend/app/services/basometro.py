"""
Basômetro: alinhamento de um parlamentar à orientação do GOVERNO nas votações nominais em plenário.

Mede apenas votações em que a fonte oficial registrou a orientação da bancada "Governo" como SIM ou NÃO
(orientações "Liberado"/ausentes não entram: não há linha de governo para seguir ou divergir). Sem baseline por
partido e sem valor padrão: com amostra insuficiente o indicador fica explicitamente indisponível.
"""

from typing import Any, Dict, Optional

from app.models.leg import Votacao, Voto
from sqlalchemy import func, text
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


# Por que o índice não aparece: cada motivo vira uma frase para o cidadão, sem número inventado.
AMOSTRA_INSUFICIENTE = "AMOSTRA_INSUFICIENTE"
SEM_ORIENTACAO = "SEM_ORIENTACAO"
MANDATO_ANTERIOR_A_BASE = "MANDATO_ANTERIOR_A_BASE"
SEM_VOTOS_NOMINAIS = "SEM_VOTOS_NOMINAIS"
SEM_MANDATO = "SEM_MANDATO"


def _cobertura(db: Session, pessoa_id: Any) -> Dict[str, Any]:
    """Votos registrados do parlamentar, ano em que a base de votações começa e fim do último mandato."""
    votos = db.execute(
        text(
            "SELECT count(*) FILTER (WHERE vt.opcao_codigo IN ('SIM', 'NAO', 'ABSTENCAO', 'OBSTRUCAO')), "
            "min(vo.data_hora), max(vo.data_hora) "
            "FROM leg.voto vt JOIN leg.votacao vo ON vo.id = vt.votacao_id WHERE vt.pessoa_id = :p"
        ),
        {"p": pessoa_id},
    ).one()
    base_desde = db.execute(text("SELECT min(data_hora) FROM leg.votacao")).scalar()
    mandato = db.execute(
        text(
            "SELECT count(*), max(coalesce(fim, current_date)) FROM core.mandato "
            "WHERE pessoa_id = :p AND condicao <> 'NOMEADO'"
        ),
        {"p": pessoa_id},
    ).one()
    return {
        "votos_registrados": int(votos[0] or 0),
        "primeiro_voto": votos[1],
        "ultimo_voto": votos[2],
        "base_desde": base_desde,
        "mandatos": int(mandato[0] or 0),
        "fim_ultimo_mandato": mandato[1],
    }


def explicar_indisponibilidade(analisadas: int, cob: Dict[str, Any]) -> Dict[str, str]:
    """Motivo e frase quando o índice não pode ser calculado. Só chamado com amostra insuficiente."""
    if analisadas > 0:
        return {
            "motivo": AMOSTRA_INSUFICIENTE,
            "explicacao": (
                f"Só {analisadas} voto(s) comparável(is) com a orientação do Governo; o índice exige "
                f"{MIN_VOTACOES_AMOSTRA} para não confundir poucos votos com um perfil."
            ),
        }
    if cob["votos_registrados"] > 0:
        return {
            "motivo": SEM_ORIENTACAO,
            "explicacao": (
                "Há votos registrados, mas nas votações em que votou o Governo não orientou SIM ou NÃO "
                "(orientação liberada ou não informada pela fonte oficial)."
            ),
        }
    base = cob["base_desde"]
    if not cob["mandatos"]:
        return {"motivo": SEM_MANDATO, "explicacao": "Nenhum mandato legislativo registrado para esta pessoa."}
    if base is not None and cob["fim_ultimo_mandato"] is not None and cob["fim_ultimo_mandato"] < base.date():
        return {
            "motivo": MANDATO_ANTERIOR_A_BASE,
            "explicacao": (
                f"O último mandato terminou em {cob['fim_ultimo_mandato'].year}; as votações nominais carregadas "
                f"começam em {base.year}."
            ),
        }
    return {
        "motivo": SEM_VOTOS_NOMINAIS,
        "explicacao": (
            "Há mandato no período coberto, mas nenhum voto nominal em plenário registrado (por exemplo, suplente em "
            "exercício curto ou matérias votadas de forma simbólica)."
        ),
    }


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
    cob = _cobertura(db, pessoa_id) if pessoa_id is not None else None
    motivo: Dict[str, Any] = {}
    if not suficiente and cob is not None:
        motivo = explicar_indisponibilidade(analisadas, cob)
    elif not suficiente:
        motivo = {"motivo": SEM_MANDATO, "explicacao": "Nenhum mandato legislativo registrado para esta pessoa."}
    return {
        "motivo_indisponivel": motivo.get("motivo"),
        "explicacao_indisponivel": motivo.get("explicacao"),
        "votos_registrados": cob["votos_registrados"] if cob else 0,
        "primeiro_voto": cob["primeiro_voto"].date().isoformat() if cob and cob["primeiro_voto"] else None,
        "ultimo_voto": cob["ultimo_voto"].date().isoformat() if cob and cob["ultimo_voto"] else None,
        "base_desde": cob["base_desde"].date().isoformat() if cob and cob["base_desde"] else None,
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
