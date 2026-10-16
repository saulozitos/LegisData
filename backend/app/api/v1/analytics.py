import math
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from app.core.data_files import FIRST_SERIES_YEAR, mandate_year_range
from app.core.database import get_db
from app.models import (
    AnnualSocialIndicator,
    CargoPoliticoEnum,
    FederalTransferByState,
    Mandate,
    PartyAffiliation,
    PoliticalParty,
    Politician,
    StatePresidentialElectionResult,
    StateSocialIndicator,
)
from app.schemas.analytics import (
    CongressCompositionResponse,
    FederalTransfersResponse,
    WageDisparityResponse,
)
from app.services.composicao_service import composicao_do_mandato
from app.services.eco_dados import macro_por_ano, seguranca_por_ano, sociais_por_ano
from app.services.iple_service import get_all_mandates_iple, get_mandate_iple
from app.services.mandato_economia_service import matriz_de_mandatos
from app.services.pnad_service import classes_sociais
from app.services.presidencia_service import presidente_por_referencia
from app.services.salario_service import disparidade_salarial
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

router = APIRouter()

ELECTION_YEARS = [1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022]


def _clean_val(v):
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 2)
    except (ValueError, TypeError):
        return None


def _num(d: Dict[str, Any], *keys: str) -> Optional[float]:
    """Primeiro valor numérico válido entre as chaves (0 é um valor válido; ausente/NaN é None)."""
    for key in keys:
        v = _clean_val(d.get(key))
        if v is not None:
            return v
    return None


def _delta(a: Optional[float], b: Optional[float], nd: int = 2) -> Optional[float]:
    return round(b - a, nd) if a is not None and b is not None else None


def _relative(a: Optional[float], b: Optional[float], nd: int = 2) -> Optional[float]:
    """Variação relativa (%) de a para b; indefinida quando a falta ou é zero."""
    if a is None or b is None or a == 0:
        return None
    return round(((b - a) / abs(a)) * 100, nd)


def _get_mandate_years(m: dict) -> List[int]:
    if not m.get("data_inicio"):
        return []
    start, end = mandate_year_range(m, last_data_year=date.today().year, min_year=FIRST_SERIES_YEAR)
    return list(range(start, end + 1))


def _mean(values: List[Optional[float]]) -> Optional[float]:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else None


def _calculate_mandate_prosperity_score(m: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula o Score Sintético de Prosperidade Presidencial (0 a 100).
    Baseado em pilares multicritério: Crescimento do PIB real, Inflação IPCA, Poder de Compra do Salário Mínimo,
    Fome/Insegurança Alimentar, Desemprego e Sustentabilidade Ambiental.

    Indicadores ausentes NÃO são substituídos por valores padrão: o pilar fica de fora e os pesos são
    renormalizados. Sem nenhum pilar disponível o score é None.
    """
    pib = _num(m, "pib_medio_anual_pct")
    ipca_total = _num(m, "ipca_pos_real_pct", "ipca_acumulado_pct")
    anos = len(m.get("valores_anuais") or [])
    if not anos and m.get("data_inicio"):
        anos = len(_get_mandate_years(m))
    ipca_medio = (ipca_total / anos) if (ipca_total is not None and anos) else None

    sm_ini = _num(m, "salario_minimo_inicial_usd")
    sm_fim = _num(m, "salario_minimo_final_usd")
    sm_var = ((sm_fim - sm_ini) / sm_ini) * 100.0 if (sm_ini and sm_fim is not None) else None
    fome = _num(m, "fome_media_pct")
    desemp = _num(m, "desemprego_medio_pct")
    desmat = _num(m, "desmatamento_medio_anual_km2")

    sc_pib = max(10.0, min(100.0, 50.0 + pib * 10.0)) if pib is not None else None
    sc_ipca = max(10.0, min(100.0, 100.0 - ipca_medio * 4.0)) if ipca_medio is not None else None
    sc_sm = max(15.0, min(100.0, 50.0 + sm_var * 0.4)) if sm_var is not None else None
    sc_fome = max(15.0, min(100.0, 100.0 - fome * 4.5)) if fome is not None else None
    sc_desemp = max(15.0, min(100.0, 100.0 - desemp * 5.0)) if desemp is not None else None
    sc_desmat = max(15.0, min(100.0, 100.0 - (desmat / 30000.0) * 60.0)) if desmat is not None else None

    sc_econ = _mean([sc_pib, sc_ipca])  # Dimensão Econômica (35%)
    sc_soc = _mean([sc_sm, sc_fome])  # Dimensão Social e Renda (35%)
    sc_est = _mean([sc_desemp, sc_desmat])  # Estabilidade e Sustentabilidade (30%)

    weighted = [(sc_econ, 0.35), (sc_soc, 0.35), (sc_est, 0.30)]
    available = [(s, w) for s, w in weighted if s is not None]
    score_geral = round(sum(s * w for s, w in available) / sum(w for _, w in available), 1) if available else None

    if score_geral is None:
        classif = None
    elif score_geral >= 80:
        classif = "Alta Prosperidade"
    elif score_geral >= 68:
        classif = "Crescimento Consistente"
    elif score_geral >= 55:
        classif = "Desempenho Moderado"
    else:
        classif = "Cenário Desafiador"

    destaque_pos = []
    if sc_pib is not None and sc_pib >= 70:
        destaque_pos.append(f"Crescimento vigoroso do PIB (+{pib:.1f}% a.a.)")
    if sc_ipca is not None and sc_ipca >= 75:
        destaque_pos.append("Controle inflacionário sólido")
    if sc_sm is not None and sc_sm >= 70:
        destaque_pos.append("Forte valorização do Salário Mínimo")
    if sc_fome is not None and sc_fome >= 75:
        destaque_pos.append("Redução acentuada da insegurança alimentar")
    if sc_desmat is not None and sc_desmat >= 75:
        destaque_pos.append("Redução das taxas de desmatamento")

    destaque_atencao = []
    if sc_ipca is not None and sc_ipca < 60:
        destaque_atencao.append(f"Pressão inflacionária acumulada ({ipca_total:.1f}%)")
    if sc_pib is not None and sc_pib < 50:
        destaque_atencao.append(f"Crescimento econômico modesto ({pib:.1f}% a.a.)")
    if sc_desemp is not None and sc_desemp < 55:
        destaque_atencao.append("Taxas de desemprego elevadas no ciclo")
    if sc_desmat is not None and sc_desmat < 50:
        destaque_atencao.append("Pico nas taxas de desmatamento da Amazônia")

    pilares = {
        "pib": sc_pib,
        "ipca": sc_ipca,
        "salario_minimo": sc_sm,
        "fome": sc_fome,
        "desemprego": sc_desemp,
        "desmatamento": sc_desmat,
    }
    return {
        "score_geral": score_geral,
        "subscore_economico": sc_econ,
        "subscore_social": sc_soc,
        "subscore_estabilidade": sc_est,
        "classificacao": classif,
        "destaque_positivo": destaque_pos[0] if destaque_pos else None,
        "destaque_atencao": destaque_atencao[0] if destaque_atencao else None,
        "pilares_ausentes": sorted(k for k, v in pilares.items() if v is None),
        "dados_incompletos": any(v is None for v in pilares.values()),
    }


@router.get("/mandates-performance", response_model=List[Dict[str, Any]])
def get_mandates_economic_performance(db: Session = Depends(get_db)):
    """
    Retorna a matriz de performance econômica cruzando cada mandato presidencial
    com inflação acumulada, crescimento real do PIB, variação cambial, evolução do salário mínimo,
    Score de Prosperidade e Índice de Poder Legislativo do Executivo (IPLE).
    """
    data = matriz_de_mandatos(db)
    if not data:
        raise HTTPException(status_code=404, detail="Matriz de mandatos não encontrada. Execute o ETL.")
    iple_por_mandato = {i["mandato_id"]: i for i in get_all_mandates_iple(db)}  # uma leitura para todos os mandatos
    return [
        {
            **m,
            "score_prosperidade": _calculate_mandate_prosperity_score(m),
            "iple": iple_por_mandato.get(m["id_mandato"]),
        }
        for m in data
    ]


def _repasse_como_dict(r: FederalTransferByState) -> Dict[str, Any]:
    """Repasse em dict. Total é obrigatório na tabela; per capita desconhecido continua None (nunca vira 0)."""
    return {
        "mandato_id_ref": r.mandate_id_ref,
        "uf": r.uf,
        "estado_nome": r.estado_nome,
        "regiao": r.regiao,
        "area_tematica": r.area_tematica,
        "valor_pago_brl": float(r.valor_pago_brl),
        "valor_per_capita_brl": float(r.valor_per_capita_brl) if r.valor_per_capita_brl is not None else None,
    }


def _sum_by(rows: List[Dict[str, Any]], key: str = "valor_pago_brl") -> float:
    return sum(float(r.get(key) or 0.0) for r in rows)


@router.get("/compare-mandates", response_model=Dict[str, Any])
def compare_mandates(
    mandate1: str = Query(..., description="ID do primeiro mandato a confrontar (ex: fhc-1995)"),
    mandate2: str = Query(..., description="ID do segundo mandato a confrontar (ex: lula-2003)"),
    db: Session = Depends(get_db),
):
    """
    Confronto direto e analítico de dois mandatos presidenciais com:
    - KPIs Macroeconômicos, Sociais (Extrema Pobreza, Analfabetismo, Insegurança Alimentar, Gini),
      Segurança Pública (Homicídios, Feminicídios) e Desmatamento Amazônia.
    - Deltas comparativos (Mandato B - Mandato A).
    - Trajetória temporal normalizada por 'Ano do Mandato' (Ano 1 a Ano N).
    - Distribuição de Verbas e Repasses Federais por Estados e Áreas Temáticas (Saúde, Educação, Infraestrutura, Segurança).
    Deltas sem os dois lados disponíveis são devolvidos como null.
    """
    mandates_list = matriz_de_mandatos(db)
    if not mandates_list:
        raise HTTPException(status_code=404, detail="Dados de mandatos não encontrados.")

    m1 = next((m for m in mandates_list if m.get("id_mandato") == mandate1), None)
    m2 = next((m for m in mandates_list if m.get("id_mandato") == mandate2), None)

    if not m1 or not m2:
        raise HTTPException(
            status_code=404,
            detail=f"Mandato(s) não encontrado(s): {mandate1 if not m1 else mandate2}",
        )

    # Carregar dados macroeconômicos anuais para trajetória
    macro_dict = macro_por_ano(db)
    sociais_map = sociais_por_ano(db)
    seg_map = seguranca_por_ano(db)
    repasses_list = [_repasse_como_dict(r) for r in db.query(FederalTransferByState).all()]

    # Anos cobertos por cada mandato
    years1 = _get_mandate_years(m1)
    years2 = _get_mandate_years(m2)
    max_years = max(len(years1), len(years2))

    # Extração de Métricas Sociais Consolidadas
    def _extract_social(years):
        rows = [sociais_map.get(y) for y in years if y in sociais_map]
        if not rows:
            return {}
        return {
            "extrema_pobreza_inicial_pct": _clean_val(rows[0].get("extrema_pobreza_pct")),
            "extrema_pobreza_final_pct": _clean_val(rows[-1].get("extrema_pobreza_pct")),
            "analfabetismo_inicial_pct": _clean_val(rows[0].get("analfabetismo")),
            "analfabetismo_final_pct": _clean_val(rows[-1].get("analfabetismo")),
            "inseguranca_alimentar_inicial_pct": _clean_val(rows[0].get("inseguranca_alimentar_pct")),
            "inseguranca_alimentar_final_pct": _clean_val(rows[-1].get("inseguranca_alimentar_pct")),
            "gini_inicial": _clean_val(rows[0].get("gini")),
            "gini_final": _clean_val(rows[-1].get("gini")),
        }

    s1 = _extract_social(years1)
    s2 = _extract_social(years2)

    # Trajetória normalizada (Ano 1 a Ano N)
    normalized_trajectory = []
    for i in range(max_years):
        y1 = years1[i] if i < len(years1) else None
        y2 = years2[i] if i < len(years2) else None

        row1 = macro_dict.get(y1, {}) if y1 else {}
        row2 = macro_dict.get(y2, {}) if y2 else {}
        soc1 = sociais_map.get(y1, {}) if y1 else {}
        soc2 = sociais_map.get(y2, {}) if y2 else {}
        sg1 = seg_map.get(y1, {}) if y1 else {}
        sg2 = seg_map.get(y2, {}) if y2 else {}

        normalized_trajectory.append(
            {
                "label": f"Ano {i + 1}",
                "year_index": i + 1,
                "m1_calendar_year": y1,
                "m1_pib": _clean_val(row1.get("pib_crescimento_real_pct")),
                "m1_ipca": _clean_val(row1.get("ipca_acumulado_ano_pct")),
                "m1_usd": _clean_val(row1.get("cambio_dolar_medio")),
                "m1_salario_minimo": _clean_val(row1.get("salario_minimo")),
                "m1_extrema_pobreza": _clean_val(soc1.get("extrema_pobreza_pct")),
                "m1_analfabetismo": _clean_val(soc1.get("analfabetismo")),
                "m1_inseguranca_alimentar": _clean_val(soc1.get("inseguranca_alimentar_pct")),
                "m1_gini": _clean_val(soc1.get("gini")),
                "m1_homicidios": _clean_val(sg1.get("taxa_homicidios")),
                "m1_feminicidios": _clean_val(sg1.get("taxa_feminicidios")),
                "m1_desmatamento": _clean_val(row1.get("taxa_desmatamento_amazonia")),
                "m2_calendar_year": y2,
                "m2_pib": _clean_val(row2.get("pib_crescimento_real_pct")),
                "m2_ipca": _clean_val(row2.get("ipca_acumulado_ano_pct")),
                "m2_usd": _clean_val(row2.get("cambio_dolar_medio")),
                "m2_salario_minimo": _clean_val(row2.get("salario_minimo")),
                "m2_extrema_pobreza": _clean_val(soc2.get("extrema_pobreza_pct")),
                "m2_analfabetismo": _clean_val(soc2.get("analfabetismo")),
                "m2_inseguranca_alimentar": _clean_val(soc2.get("inseguranca_alimentar_pct")),
                "m2_gini": _clean_val(soc2.get("gini")),
                "m2_homicidios": _clean_val(sg2.get("taxa_homicidios")),
                "m2_feminicidios": _clean_val(sg2.get("taxa_feminicidios")),
                "m2_desmatamento": _clean_val(row2.get("taxa_desmatamento_amazonia")),
            }
        )

    # Cálculo dos Deltas (M2 em relação a M1); valor ausente => delta null (zero legítimo é preservado)
    ipca1 = _num(m1, "ipca_pos_real_pct", "ipca_acumulado_pct")
    ipca2 = _num(m2, "ipca_pos_real_pct", "ipca_acumulado_pct")
    pib1, pib2 = _num(m1, "pib_medio_anual_pct"), _num(m2, "pib_medio_anual_pct")
    pib_acum1 = _num(m1, "pib_crescimento_acumulado_pct")
    pib_acum2 = _num(m2, "pib_crescimento_acumulado_pct")
    cambio1, cambio2 = _num(m1, "cambio_variacao_pct"), _num(m2, "cambio_variacao_pct")
    sm_brl1, sm_brl2 = _num(m1, "salario_minimo_final_brl"), _num(m2, "salario_minimo_final_brl")
    sm_usd1, sm_usd2 = _num(m1, "salario_minimo_final_usd"), _num(m2, "salario_minimo_final_usd")

    fome1 = s1.get("inseguranca_alimentar_final_pct")
    fome1 = fome1 if fome1 is not None else _num(m1, "fome_final_pct")
    fome2 = s2.get("inseguranca_alimentar_final_pct")
    fome2 = fome2 if fome2 is not None else _num(m2, "fome_final_pct")

    hom1, hom2 = _num(m1, "homicidios_medio"), _num(m2, "homicidios_medio")
    fem1, fem2 = _num(m1, "feminicidios_medio"), _num(m2, "feminicidios_medio")
    desm1, desm2 = _num(m1, "desmatamento_medio_anual_km2"), _num(m2, "desmatamento_medio_anual_km2")

    # Repasses Federais por Estado e Área
    m1_repasses = [r for r in repasses_list if r.get("mandato_id_ref") == mandate1]
    m2_repasses = [r for r in repasses_list if r.get("mandato_id_ref") == mandate2]

    areas_meta = [
        {"area": "Saúde", "sublabel": "SUS & FNS"},
        {"area": "Educação", "sublabel": "FUNDEB & FNDE"},
        {"area": "Infraestrutura", "sublabel": "Infraestrutura & Cidades"},
        {"area": "Segurança Pública", "sublabel": "Segurança Pública & Polícias"},
    ]

    by_area: Dict[str, Dict[str, Any]] = {}
    for a in areas_meta:
        nome_area = a["area"]
        v1 = _sum_by([r for r in m1_repasses if r.get("area_tematica") == nome_area])
        v2 = _sum_by([r for r in m2_repasses if r.get("area_tematica") == nome_area])
        by_area[nome_area] = {
            "area": nome_area,
            "sublabel": a["sublabel"],
            "m1_total": round(v1, 2),
            "m2_total": round(v2, 2),
            "diff_brl": round(v2 - v1, 2),
            "growth_pct": round(((v2 - v1) / v1) * 100, 2) if v1 > 0 else 0.0,
        }

    # Índices por UF (evita varrer a lista inteira para cada estado)
    by_uf_m1: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_uf_m2: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in m1_repasses:
        by_uf_m1[r["uf"]].append(r)
    for r in m2_repasses:
        by_uf_m2[r["uf"]].append(r)

    all_ufs = sorted({r["uf"] for r in repasses_list if r.get("uf")})
    by_uf = []
    for uf in all_ufs:
        u1 = by_uf_m1.get(uf, [])
        u2 = by_uf_m2.get(uf, [])
        estado_nome = u1[0]["estado_nome"] if u1 else (u2[0]["estado_nome"] if u2 else uf)
        regiao = u1[0]["regiao"] if u1 else (u2[0]["regiao"] if u2 else "")
        tot1 = _sum_by(u1)
        tot2 = _sum_by(u2)
        # per capita desconhecido (sem população estimada, ou UF sem repasse no mandato) fica None, nunca 0
        pc1 = u1[0].get("valor_per_capita_brl") if u1 else None
        pc2 = u2[0].get("valor_per_capita_brl") if u2 else None

        areas_breakdown = {}
        for a in areas_meta:
            nome_area = a["area"]
            av1 = _sum_by([r for r in u1 if r.get("area_tematica") == nome_area])
            av2 = _sum_by([r for r in u2 if r.get("area_tematica") == nome_area])
            areas_breakdown[nome_area] = {
                "m1": round(av1, 2),
                "m2": round(av2, 2),
                "diff": round(av2 - av1, 2),
                "growth_pct": round(((av2 - av1) / av1) * 100, 2) if av1 > 0 else 0.0,
            }

        by_uf.append(
            {
                "uf": uf,
                "estado_nome": estado_nome,
                "regiao": regiao,
                "m1_total": round(tot1, 2),
                "m2_total": round(tot2, 2),
                "diff_brl": round(tot2 - tot1, 2),
                "growth_pct": round(((tot2 - tot1) / tot1) * 100, 2) if tot1 > 0 else 0.0,
                "m1_per_capita": round(pc1, 2) if pc1 is not None else None,
                "m2_per_capita": round(pc2, 2) if pc2 is not None else None,
                "diff_per_capita": round(pc2 - pc1, 2) if pc1 is not None and pc2 is not None else None,
                "areas": areas_breakdown,
            }
        )

    tot_geral_1 = sum(item["m1_total"] for item in by_area.values())
    tot_geral_2 = sum(item["m2_total"] for item in by_area.values())

    score_m1 = _calculate_mandate_prosperity_score(m1)
    score_m2 = _calculate_mandate_prosperity_score(m2)

    com_pc1 = [u for u in by_uf if u["m1_per_capita"] is not None]
    com_pc2 = [u for u in by_uf if u["m2_per_capita"] is not None]
    top_uf_m1 = max(com_pc1, key=lambda x: x["m1_per_capita"]) if com_pc1 else None
    top_uf_m2 = max(com_pc2, key=lambda x: x["m2_per_capita"]) if com_pc2 else None
    termometro_repasses = {
        "m1_lider_per_capita": {
            "uf": top_uf_m1["uf"] if top_uf_m1 else None,
            "estado": top_uf_m1["estado_nome"] if top_uf_m1 else None,
            "valor_per_capita": top_uf_m1["m1_per_capita"] if top_uf_m1 else None,
        },
        "m2_lider_per_capita": {
            "uf": top_uf_m2["uf"] if top_uf_m2 else None,
            "estado": top_uf_m2["estado_nome"] if top_uf_m2 else None,
            "valor_per_capita": top_uf_m2["m2_per_capita"] if top_uf_m2 else None,
        },
        "diagnostico": "Estados com menor contingente populacional e áreas prioritárias (Norte/Centro-Oeste) absorvem maior volume de repasses federais per capita vinculados aos pisos constitucionais de Saúde e Educação.",
    }

    iple1 = get_mandate_iple(db, mandate1)
    iple2 = get_mandate_iple(db, mandate2)
    m1_enriched = {**m1, "sociais": s1, "score_prosperidade": score_m1, "iple": iple1}
    m2_enriched = {**m2, "sociais": s2, "score_prosperidade": score_m2, "iple": iple2}

    def _score_delta(key: str) -> Optional[float]:
        return _delta(score_m1[key], score_m2[key], 1)

    return {
        "mandate1": m1_enriched,
        "mandate2": m2_enriched,
        "deltas": {
            "ipca_acumulado_diff_pp": _delta(ipca1, ipca2),
            "ipca_acumulado_relative_pct": _relative(ipca1, ipca2),
            "pib_medio_diff_pp": _delta(pib1, pib2),
            "pib_medio_relative_pct": _relative(pib1, pib2),
            "pib_acumulado_diff_pp": _delta(pib_acum1, pib_acum2),
            "cambio_variacao_diff_pp": _delta(cambio1, cambio2),
            "salario_minimo_brl_diff": _delta(sm_brl1, sm_brl2),
            "salario_minimo_brl_relative_pct": _relative(sm_brl1, sm_brl2),
            "salario_minimo_usd_diff": _delta(sm_usd1, sm_usd2),
            "salario_minimo_usd_relative_pct": _relative(sm_usd1, sm_usd2),
            "extrema_pobreza_diff_pp": _delta(s1.get("extrema_pobreza_final_pct"), s2.get("extrema_pobreza_final_pct")),
            "analfabetismo_diff_pp": _delta(s1.get("analfabetismo_final_pct"), s2.get("analfabetismo_final_pct")),
            "inseguranca_alimentar_diff_pp": _delta(fome1, fome2),
            "gini_diff": _delta(s1.get("gini_final"), s2.get("gini_final"), 3),
            "homicidios_medio_diff": _delta(hom1, hom2),
            "feminicidios_medio_diff": _delta(fem1, fem2),
            "desmatamento_medio_diff": _delta(desm1, desm2),
        },
        "scores_prosperidade": {
            "mandate1": score_m1,
            "mandate2": score_m2,
            "delta_score_geral": _score_delta("score_geral"),
            "delta_economico": _score_delta("subscore_economico"),
            "delta_social": _score_delta("subscore_social"),
            "delta_estabilidade": _score_delta("subscore_estabilidade"),
        },
        "termometro_repasses_apoio": termometro_repasses,
        "iple": {
            "mandate1": iple1,
            "mandate2": iple2,
            "delta_iple_score": (
                round(
                    float(iple2["indicadores_base"]["iple_score"]) - float(iple1["indicadores_base"]["iple_score"]), 4
                )
                if (iple1 and iple2 and "indicadores_base" in iple1 and "indicadores_base" in iple2)
                else None
            ),
        },
        "normalized_trajectory": normalized_trajectory,
        "repasses_comparison": {
            "by_area": by_area,
            "by_uf": by_uf,
            "summary": {
                "m1_total_geral": round(tot_geral_1, 2),
                "m2_total_geral": round(tot_geral_2, 2),
                "diff_total_brl": round(tot_geral_2 - tot_geral_1, 2),
                "growth_total_pct": (
                    round(((tot_geral_2 - tot_geral_1) / tot_geral_1) * 100, 2) if tot_geral_1 > 0 else 0.0
                ),
            },
        },
    }


def _current_mandates_by_politician(db: Session) -> Dict[Any, Mandate]:
    """Mandato federal (deputado/senador) em curso de cada parlamentar em exercício."""
    today = date.today()
    mandates = (
        db.query(Mandate)
        .filter(
            Mandate.office.in_([CargoPoliticoEnum.DEPUTADO_FEDERAL, CargoPoliticoEnum.SENADOR]),
            or_(Mandate.end_date.is_(None), Mandate.end_date >= today),
        )
        .order_by(Mandate.start_date.asc())
        .all()
    )
    return {m.politician_id: m for m in mandates}  # ordem crescente: prevalece o mais recente


@router.get("/party-fidelity", response_model=Dict[str, Any])
def get_party_fidelity(db: Session = Depends(get_db)):
    """
    Retorna a análise consolidada de fidelidade e migração partidária no Congresso Nacional:
    - Balanço partidário: ganhos, perdas e saldo líquido de bancada por legenda dos parlamentares EM EXERCÍCIO.
    - Top nômades partidários: parlamentares em exercício que mais trocaram de partido em suas carreiras.
    - Resumo e métricas gerais de infidelidade partidária.
    """
    empty_response = {
        "dados_disponiveis": False,
        "party_balance": [],
        "top_nomads": [],
        "summary": {
            "total_parlamentares": 0,
            "total_nomades": 0,
            "taxa_migracao_pct": 0,
            "partido_maior_ganho": None,
            "saldo_maior_ganho": 0,
            "partido_maior_perda": None,
            "saldo_maior_perda": 0,
        },
    }

    current_mandates = _current_mandates_by_politician(db)
    if not current_mandates:
        return empty_response

    party_map = {p.id: {"sigla": p.acronym, "nome": p.full_name} for p in db.query(PoliticalParty).all()}

    affs = db.query(PartyAffiliation).filter(PartyAffiliation.politician_id.in_(list(current_mandates))).all()
    if not affs:
        return empty_response

    by_pol = defaultdict(list)
    for a in affs:
        by_pol[a.politician_id].append(a)

    # Dados dos políticos com mais de uma filiação em uma única consulta (sem N+1)
    multi_ids = [pid for pid, items in by_pol.items() if len(items) > 1]
    pol_map = {p.id: p for p in db.query(Politician).filter(Politician.id.in_(multi_ids)).all()} if multi_ids else {}

    gains: Dict[str, int] = defaultdict(int)
    losses: Dict[str, int] = defaultdict(int)
    current_seats: Dict[str, int] = defaultdict(int)
    initial_seats: Dict[str, int] = defaultdict(int)
    nomads = []

    for pid, p_affs in by_pol.items():
        sorted_affs = sorted(p_affs, key=lambda x: x.start_date)
        first_aff = sorted_affs[0]
        curr_aff = next((x for x in reversed(sorted_affs) if x.is_current), sorted_affs[-1])

        first_sigla = party_map.get(first_aff.party_id, {}).get("sigla", "OUTROS")
        curr_sigla = party_map.get(curr_aff.party_id, {}).get("sigla", "OUTROS")

        initial_seats[first_sigla] += 1
        current_seats[curr_sigla] += 1

        if len(sorted_affs) > 1 and first_sigla != curr_sigla:
            losses[first_sigla] += 1
            gains[curr_sigla] += 1

        pol = pol_map.get(pid)
        if len(sorted_affs) > 1 and pol:
            mandate = current_mandates[pid]
            history_list = []
            for x in sorted_affs:
                history_list.append(
                    {
                        "partido": party_map.get(x.party_id, {}).get("sigla", "S.PART."),
                        "data_filiacao": x.start_date.isoformat(),
                        "data_desfiliacao": (x.end_date.isoformat() if x.end_date else None),
                        "motivo": (x.disaffiliation_reason.value if x.disaffiliation_reason else None),
                        "is_atual": bool(x.is_current),
                    }
                )

            nomads.append(
                {
                    "id": str(pol.id),
                    "nome_eleitoral": pol.electoral_name,
                    "nome_civil": pol.civil_name,
                    "cargo": "SENADOR" if mandate.office == CargoPoliticoEnum.SENADOR else "DEPUTADO FEDERAL",
                    "uf": mandate.jurisdiction_state,
                    "foto_url": pol.photo_url,
                    "partido_atual": curr_sigla,
                    "total_trocas": len(sorted_affs) - 1,
                    "total_partidos": len(set(x["partido"] for x in history_list)),
                    "siglas_sequencia": [x["partido"] for x in history_list],
                    "historico": history_list,
                }
            )

    nomads.sort(key=lambda x: (x["total_trocas"], x["total_partidos"], x["nome_eleitoral"]), reverse=True)

    party_balance = []
    for p in sorted(set(current_seats) | set(initial_seats)):
        if p in ("S.PART.", "OUTROS"):
            continue
        g = gains[p]
        loss = losses[p]
        party_balance.append(
            {
                "partido": p,
                "bancada_atual": current_seats[p],
                "bancada_inicial": initial_seats[p],
                "ganhos": g,
                "perdas": loss,
                "saldo_liquido": g - loss,
            }
        )

    party_balance.sort(key=lambda x: (x["saldo_liquido"], x["partido"]), reverse=True)

    summary = {
        "total_parlamentares": len(by_pol),
        "total_nomades": len(nomads),
        "taxa_migracao_pct": (round((len(nomads) / len(by_pol)) * 100, 1) if by_pol else 0),
        "partido_maior_ganho": party_balance[0]["partido"] if party_balance else None,
        "saldo_maior_ganho": party_balance[0]["saldo_liquido"] if party_balance else 0,
        "partido_maior_perda": party_balance[-1]["partido"] if party_balance else None,
        "saldo_maior_perda": party_balance[-1]["saldo_liquido"] if party_balance else 0,
    }

    return {
        "dados_disponiveis": True,
        "party_balance": party_balance,
        "top_nomads": nomads[:35],
        "summary": summary,
    }


@router.get("/wage-disparity", response_model=WageDisparityResponse)
def get_wage_disparity(db: Session = Depends(get_db)):
    """
    Retorna a série evolutiva confrontando:
    1) Salário Mínimo (BRL)
    2) Subsídio dos Parlamentares (BRL), fixado por decreto legislativo
    3) Inflação Acumulada
    Mais o placar da votação do Salário Mínimo (MPV 1172/2023), calculado dos votos nominais.
    """
    return disparidade_salarial(db)


@router.get("/congress-composition", response_model=CongressCompositionResponse)
def get_congress_composition(
    mandate_id: str = Query("lula-2023", description="ID do mandato presidencial"), db: Session = Depends(get_db)
):
    """
    Retorna a composição do Congresso Nacional durante o mandato:
    - Presidentes da Câmara e do Senado (com nomes, partidos e fotos)
    - Tamanho das Bancadas dos partidos na Câmara (513) e Senado (81)
    - Alinhamento e Governabilidade do Presidente da República
    """
    return composicao_do_mandato(db, mandate_id)


def _cobertura_repasses(linhas: List[tuple]) -> Dict[str, Any]:
    """Resume o período realmente coberto pelos repasses (o portal só publica a partir de 2014-01)."""
    inicios = [i for i, _f, _m, _p in linhas if i]
    fins = [f for _i, f, _m, _p in linhas if f]
    meses = [m for _i, _f, m, _p in linhas if m]
    parciais = [p for _i, _f, _m, p in linhas if p is not None]
    if not inicios or not fins:
        return {
            "inicio": None,
            "fim": None,
            "meses": None,
            "parcial": None,
            "descricao": "Transferências da União por UF (período de cobertura não informado)",
        }
    inicio, fim = min(inicios), max(fins)
    parcial = any(parciais) if parciais else None
    aviso = " — cobertura parcial do mandato (o Portal da Transparência publica desde 2014-01)" if parcial else ""
    return {
        "inicio": inicio,
        "fim": fim,
        "meses": max(meses) if meses else None,
        "parcial": parcial,
        "descricao": f"Transferências da União por UF, {inicio} a {fim}{aviso}",
    }


@router.get("/federal-transfers", response_model=FederalTransfersResponse)
def get_federal_transfers(
    mandate_id: str = Query("lula-2023", description="ID do mandato presidencial"),
    area: Optional[str] = Query(
        None,
        max_length=50,
        description="Filtrar por área (Saúde, Educação, Infraestrutura, Segurança Pública)",
    ),
    db: Session = Depends(get_db),
):
    """
    Retorna a execução orçamentária e repasses federais por Estado (UF) no mandato:
    - Grandes áreas: Saúde, Educação, Infraestrutura e Segurança Pública
    - Totais gerais, agregados por região e valores per capita
    Mandato sem repasses carregados devolve a lista vazia.
    """
    if presidente_por_referencia(db, mandate_id) is None:
        raise HTTPException(status_code=404, detail=f"Mandato '{mandate_id}' não encontrado.")

    query = db.query(FederalTransferByState).filter(FederalTransferByState.mandate_id_ref == mandate_id)
    if area and area.strip():
        escaped = area.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(FederalTransferByState.area_tematica.ilike(f"%{escaped}%", escape="\\"))
    rows = query.order_by(FederalTransferByState.uf, FederalTransferByState.area_tematica).all()
    items: List[Dict[str, Any]] = [
        {
            "uf": r.uf,
            "estado_nome": r.estado_nome,
            "regiao": r.regiao,
            "area_tematica": r.area_tematica,
            "valor_pago_brl": float(r.valor_pago_brl),
            "populacao_estimada": r.populacao_estimada or 0,
            "valor_per_capita_brl": float(r.valor_per_capita_brl) if r.valor_per_capita_brl is not None else None,
        }
        for r in rows
    ]
    cobertura = _cobertura_repasses([(r.periodo_inicio, r.periodo_fim, r.meses_cobertos, r.parcial) for r in rows])

    total_brl = sum(i["valor_pago_brl"] for i in items)
    areas_sum: Dict[str, float] = {}
    regioes_sum: Dict[str, float] = {}
    for i in items:
        areas_sum[i["area_tematica"]] = round(areas_sum.get(i["area_tematica"], 0.0) + i["valor_pago_brl"], 2)
        regioes_sum[i["regiao"]] = round(regioes_sum.get(i["regiao"], 0.0) + i["valor_pago_brl"], 2)

    return {
        "mandato_id": mandate_id,
        "periodo": cobertura["descricao"],
        "periodo_inicio": cobertura["inicio"],
        "periodo_fim": cobertura["fim"],
        "meses_cobertos": cobertura["meses"],
        "cobertura_parcial": cobertura["parcial"],
        "total_repassado_brl": round(total_brl, 2),
        "areas_resumo": areas_sum,
        "regioes_resumo": regioes_sum,
        "por_uf": items,
    }


def _opt_float(value) -> Optional[float]:
    """Decimal/float -> float preservando zero (apenas None vira None)."""
    return float(value) if value is not None else None


@router.get("/social-indicators")
def get_social_indicators(db: Session = Depends(get_db)):
    """
    Retorna o histórico anual nacional de indicadores sociais oficiais (IBGE/SIDRA), apenas nos anos com dado:
    taxa de analfabetismo, extrema pobreza e pobreza (% e milhões), insegurança alimentar grave (% de domicílios),
    índice de Gini (`serie_gini` informa a pesquisa; há quebra metodológica em 2012) e desemprego.
    Lacunas de pesquisa vêm como null; nada é interpolado.
    """
    records = db.query(AnnualSocialIndicator).order_by(AnnualSocialIndicator.year.asc()).all()
    if records:
        return [
            {
                "ano": r.year,
                "analfabetismo_pct": _opt_float(r.illiteracy_rate_pct),
                "extrema_pobreza_pct": _opt_float(r.extreme_poverty_pct),
                "extrema_pobreza_milhoes": _opt_float(r.extreme_poverty_millions),
                "inseguranca_alimentar_pct": _opt_float(r.food_insecurity_pct),
                "inseguranca_alimentar_milhoes": _opt_float(r.food_insecurity_millions),
                "gini": _opt_float(r.gini_index),
                "serie_gini": r.gini_series,
                "pobreza_pct": _opt_float(r.poverty_pct),
                "inseguranca_alimentar_total_pct": _opt_float(r.food_insecurity_total_pct),
                "desemprego_pct": _opt_float(r.unemployment_pct),
                "fonte": r.data_source,
            }
            for r in records
        ]

    return []


@router.get("/social-classes")
def get_social_classes_distribution(
    ano: Optional[int] = Query(None, description="Ano da PNAD Contínua (padrão: o mais recente disponível)."),
    db: Session = Depends(get_db),
):
    """
    Retorna a divisão de classes sociais no Brasil por faixas de salários mínimos, calculada dos microdados da PNAD
    Contínua (`etl/run_etl.py --pnad`, carregados com `--load-economia`) para o ano pedido, com o salário mínimo do
    próprio ano. Sem os microdados do ano, a resposta é 404: não há estimativa de reserva.
    """
    return classes_sociais(db, ano)


@router.get("/social-elections")
def get_social_elections_correlation(
    ano: int = Query(
        2022,
        description="Ano eleitoral de referência (1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022)",
    ),
    db: Session = Depends(get_db),
):
    """
    Cruza os indicadores sociais por Estado (UF) com os resultados eleitorais presidenciais (TSE).
    Permite examinar a correlação entre extrema pobreza/analfabetismo e a preferência eleitoral.
    Indicadores sociais ausentes no ano da eleição ficam como null (sem usar dados de outro ano).
    """
    if ano not in ELECTION_YEARS:
        raise HTTPException(
            status_code=422,
            detail=f"Ano eleitoral inválido. Valores aceitos: {', '.join(str(y) for y in ELECTION_YEARS)}.",
        )
    selected_year = ano

    eleicoes_db = (
        db.query(StatePresidentialElectionResult)
        .filter(StatePresidentialElectionResult.election_year == selected_year)
        .order_by(StatePresidentialElectionResult.uf)
        .all()
    )

    sociais_db = db.query(StateSocialIndicator).filter(StateSocialIndicator.year == selected_year).all()
    sociais_map = {s.uf: s for s in sociais_db}

    merged = []
    for el in eleicoes_db:
        soc = sociais_map.get(el.uf)

        merged.append(
            {
                "uf": el.uf,
                "estado_nome": el.state_name,
                "regiao": el.region,
                "ano_eleicao": el.election_year,
                "vencedor_nome": el.winner_candidate_name,
                "vencedor_partido": el.winner_party_acronym,
                "vencedor_votos_pct": _opt_float(el.winner_votes_pct),
                "segundo_nome": el.runner_up_candidate_name,
                "segundo_partido": el.runner_up_party_acronym,
                "segundo_votos_pct": _opt_float(el.runner_up_votes_pct),
                "taxa_analfabetismo_pct": _opt_float(soc.illiteracy_rate_pct) if soc else None,
                "extrema_pobreza_pct": _opt_float(soc.extreme_poverty_pct) if soc else None,
                "inseguranca_alimentar_pct": _opt_float(soc.food_insecurity_pct) if soc else None,
                "indice_gini": _opt_float(soc.gini_index) if soc else None,
            }
        )

    # Ordenar por extrema pobreza decrescente (sem dado vai para o fim)
    merged.sort(key=lambda x: (x["extrema_pobreza_pct"] is not None, x["extrema_pobreza_pct"] or 0), reverse=True)

    # Análise regional agregada (médias somente sobre os estados que têm o indicador)
    regioes_agg: Dict[str, Dict[str, Any]] = {}
    for item in merged:
        reg = item["regiao"]
        agg = regioes_agg.setdefault(
            reg,
            {"total_ufs": 0, "pobreza": [], "analfabetismo": [], "vencedores": {}},
        )
        agg["total_ufs"] += 1
        if item["extrema_pobreza_pct"] is not None:
            agg["pobreza"].append(item["extrema_pobreza_pct"])
        if item["taxa_analfabetismo_pct"] is not None:
            agg["analfabetismo"].append(item["taxa_analfabetismo_pct"])
        venc = f"{item['vencedor_nome']} ({item['vencedor_partido']})"
        agg["vencedores"][venc] = agg["vencedores"].get(venc, 0) + 1

    regioes_summary = []
    for reg, d in regioes_agg.items():
        regioes_summary.append(
            {
                "regiao": reg,
                "total_estados": d["total_ufs"],
                "media_extrema_pobreza_pct": round(sum(d["pobreza"]) / len(d["pobreza"]), 2) if d["pobreza"] else None,
                "media_analfabetismo_pct": (
                    round(sum(d["analfabetismo"]) / len(d["analfabetismo"]), 2) if d["analfabetismo"] else None
                ),
                "vencedores_contagem": d["vencedores"],
            }
        )

    return {
        "ano_eleicao": selected_year,
        "total_estados": len(merged),
        "anos_disponiveis": ELECTION_YEARS,
        "regioes_resumo": regioes_summary,
        "estados": merged,
    }
