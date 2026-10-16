"""Salário mínimo, subsídio parlamentar e inflação desde 1995, a partir das séries oficiais de `eco`."""

from typing import Any, Dict, List, Optional

from app.models.leg import Proposicao, Votacao
from app.services.economia_service import dominantes_por_ano
from app.services.periodos import nome_do_mandato
from app.services.placar import contagens_por_votacao, placar_para_tela, placares_das_votacoes, sessao_principal
from sqlalchemy import text
from sqlalchemy.orm import Session

_SERIES_SQL = text(
    """
    SELECT s.codigo, extract(year FROM o.referencia)::int AS ano, o.valor
    FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id
    WHERE s.codigo IN ('SALARIO_MINIMO', 'SUBSIDIO_PARLAMENTAR', 'IPCA_ACUM_ANO') AND o.uf IS NULL
    """
)

# Votação do reajuste do salário mínimo no Plenário da Câmara (Lei 14.663/2023), localizada pela proposição.
MPV_SALARIO = ("MPV", 1172, 2023)
CASA_CAMARA = "CAMARA_DOS_DEPUTADOS"


def _crescimento(final: float, inicial: float) -> float:
    return round((final / inicial - 1.0) * 100.0, 1)


def serie_historica(db: Session) -> List[Dict[str, Any]]:
    """Um ponto por ano em que há salário mínimo e subsídio com norma citada; o IPCA ausente fica `None`."""
    por_serie: Dict[str, Dict[int, float]] = {}
    for codigo, ano, valor in db.execute(_SERIES_SQL):
        por_serie.setdefault(codigo, {})[ano] = float(valor)
    minimo, subsidio, ipca = (por_serie.get(c, {}) for c in ("SALARIO_MINIMO", "SUBSIDIO_PARLAMENTAR", "IPCA_ACUM_ANO"))
    anos = sorted(a for a in minimo if a in subsidio and minimo[a] > 0)
    if not anos:
        return []
    dominantes = dominantes_por_ano(db)
    base_min, base_sub = minimo[anos[0]], subsidio[anos[0]]
    fator_ipca = 1.0
    pontos: List[Dict[str, Any]] = []
    for i, ano in enumerate(anos):
        if i > 0 and ano in ipca:
            fator_ipca *= 1.0 + ipca[ano] / 100.0
        dominante = dominantes.get(ano)
        pontos.append(
            {
                "ano": ano,
                "presidente_dominante": (
                    nome_do_mandato(dominante["nome_exibicao"], dominante["rotulo"]) if dominante else "—"
                ),
                "salario_minimo_brl": minimo[ano],
                "salario_parlamentar_brl": subsidio[ano],
                "multiplo_salarios_minimos": round(subsidio[ano] / minimo[ano], 1),
                "ipca_acumulado_ano_pct": round(ipca[ano], 2) if ano in ipca else None,
                "indice_salario_minimo_base100": round(minimo[ano] / base_min * 100.0, 1),
                "indice_salario_parlamentar_base100": round(subsidio[ano] / base_sub * 100.0, 1),
                "indice_ipca_base100": round(fator_ipca * 100.0, 1),
            }
        )
    return pontos


def estatisticas(pontos: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resumo calculado da própria série (primeiro e último ano, múltiplo médio, pico e crescimento acumulado)."""
    primeiro, atual = pontos[0], pontos[-1]
    pico = max(pontos, key=lambda p: p["multiplo_salarios_minimos"])
    multiplos = [p["multiplo_salarios_minimos"] for p in pontos]
    return {
        "ano_referencia_inicial": primeiro["ano"],
        "ano_referencia_atual": atual["ano"],
        "salario_minimo_inicial": primeiro["salario_minimo_brl"],
        "salario_minimo_atual": atual["salario_minimo_brl"],
        "salario_parlamentar_inicial": primeiro["salario_parlamentar_brl"],
        "salario_parlamentar_atual": atual["salario_parlamentar_brl"],
        "multiplo_medio_historico": round(sum(multiplos) / len(multiplos), 1),
        "pico_multiplo_ano": pico["ano"],
        "pico_multiplo_valor": pico["multiplo_salarios_minimos"],
        "multiplo_atual": atual["multiplo_salarios_minimos"],
        "crescimento_acumulado_salario_minimo_pct": _crescimento(
            atual["salario_minimo_brl"], primeiro["salario_minimo_brl"]
        ),
        "crescimento_acumulado_salario_parlamentar_pct": _crescimento(
            atual["salario_parlamentar_brl"], primeiro["salario_parlamentar_brl"]
        ),
    }


def votacao_salario_minimo(db: Session) -> Dict[str, Any]:
    """Placar da MPV 1172/2023 no Plenário da Câmara, calculado dos votos nominais; sem a votação, vem indisponível."""
    base: Dict[str, Any] = {
        "proposicao_titulo": "MPV 1172/2023 (Lei nº 14.663/2023)",
        "ementa": "Define o valor do salário mínimo em R$ 1.320,00 e estabelece a política de valorização "
        "permanente com ganho real anual.",
        "data_votacao": None,
        "casa": "Câmara dos Deputados (Plenário)",
        "placar": None,
        "votos_amostra": [],
        "dados_indisponiveis": True,
    }
    tipo, numero, ano = MPV_SALARIO
    proposicao = (
        db.query(Proposicao)
        .filter(Proposicao.tipo_codigo == tipo, Proposicao.numero == numero, Proposicao.ano == ano)
        .first()
    )
    if proposicao is None:
        return base
    votacoes = [
        v
        for v in db.query(Votacao).filter(Votacao.proposicao_id == proposicao.id).all()
        if v.casa is not None and v.casa.codigo == CASA_CAMARA
    ]
    contagens = contagens_por_votacao(db, Votacao.proposicao_id == proposicao.id)
    placares = placares_das_votacoes(votacoes, contagens)
    sessao = sessao_principal(votacoes, placares)
    if sessao is None or not placares[sessao.id]["total"]:
        return base
    base.update(
        {
            "data_votacao": sessao.data_hora.date().isoformat(),
            "placar": placar_para_tela(placares[sessao.id]),
            "dados_indisponiveis": False,
            "fonte": "API Dados Abertos da Câmara (votos nominais)",
        }
    )
    return base


def disparidade_salarial(db: Session) -> Optional[Dict[str, Any]]:
    pontos = serie_historica(db)
    if not pontos:
        return None
    return {
        "serie_historica": pontos,
        "votacao_salario_minimo": votacao_salario_minimo(db),
        "estatisticas_disparidade": estatisticas(pontos),
    }
