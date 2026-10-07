import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
import pandas as pd

from app.core.database import get_db
from app.schemas.analytics import (
    WageDisparityResponse,
    CongressCompositionResponse,
    FederalTransfersResponse
)
from app.models import (
    FederalTransferByState,
    AnnualSocialIndicator,
    StateSocialIndicator,
    StatePresidentialElectionResult
)

router = APIRouter()
DATA_DIR = Path(__file__).resolve().parents[4] / "etl" / "data" / "processed"


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


def _get_mandate_years(m: dict) -> List[int]:
    mid = m.get("id_mandato", "")
    if mid == "itamar-franco-1992":
        return [1993, 1994]
    if mid == "dilma-2015":
        return [2015, 2016]
    if mid == "temer-2016":
        return [2016, 2017, 2018]
    if mid == "lula-2023":
        return [2023, 2024, 2025, 2026]

    start_yr = int(m["data_inicio"][:4])
    end_yr = int(m["data_fim"][:4]) if m.get("data_fim") else start_yr + 4
    years = [y for y in range(start_yr, end_yr)]
    return years if years else [start_yr]


@router.get("/mandates-performance", response_model=List[Dict[str, Any]])
def get_mandates_economic_performance():
    """
    Retorna a matriz de performance econômica cruzando cada mandato presidencial
    com a inflação acumulada no período, crescimento real do PIB, variação cambial e evolução do salário mínimo.
    """
    file_path = DATA_DIR / "indicadores_por_mandato.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Matriz de mandatos não encontrada. Execute o ETL.")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/compare-mandates", response_model=Dict[str, Any])
def compare_mandates(
    mandate1: str = Query(..., description="ID do primeiro mandato a confrontar (ex: fhc-1995)"),
    mandate2: str = Query(..., description="ID do segundo mandato a confrontar (ex: lula-2003)")
):
    """
    Confronto direto e analítico de dois mandatos presidenciais com:
    - KPIs lado a lado
    - Diferença percentual / delta em pontos percentuais (IPCA acumulado, PIB médio e variação cambial)
    - Trajetória temporal normalizada por 'Ano do Mandato' (Ano 1, Ano 2, Ano 3, Ano 4)
    """
    file_path = DATA_DIR / "indicadores_por_mandato.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Dados de mandatos não encontrados.")

    with open(file_path, "r", encoding="utf-8") as f:
        mandates_list = json.load(f)

    m1 = next((m for m in mandates_list if m["id_mandato"] == mandate1), None)
    m2 = next((m for m in mandates_list if m["id_mandato"] == mandate2), None)

    if not m1 or not m2:
        raise HTTPException(status_code=404, detail=f"Mandato(s) não encontrado(s): {mandate1 if not m1 else mandate2}")

    # Carregar dados macroeconômicos anuais para trajetória
    macro_csv = DATA_DIR / "resumo_macroeconomico_anual.csv"
    macro_dict = {}
    if macro_csv.exists():
        df_macro = pd.read_csv(macro_csv)
        macro_dict = df_macro.set_index("ano").to_dict(orient="index")

    # Anos cobertos por cada mandato
    years1 = _get_mandate_years(m1)
    years2 = _get_mandate_years(m2)
    max_years = max(len(years1), len(years2))

    # Trajetória normalizada (Ano 1 a Ano N)
    normalized_trajectory = []
    for i in range(max_years):
        y1 = years1[i] if i < len(years1) else None
        y2 = years2[i] if i < len(years2) else None

        row1 = macro_dict.get(y1, {}) if y1 else {}
        row2 = macro_dict.get(y2, {}) if y2 else {}

        normalized_trajectory.append({
            "label": f"Ano {i + 1}",
            "year_index": i + 1,
            "m1_calendar_year": y1,
            "m1_pib": _clean_val(row1.get("pib_crescimento_real_pct")),
            "m1_ipca": _clean_val(row1.get("ipca_acumulado_ano_pct")),
            "m1_usd": _clean_val(row1.get("cambio_dolar_medio")),
            "m2_calendar_year": y2,
            "m2_pib": _clean_val(row2.get("pib_crescimento_real_pct")),
            "m2_ipca": _clean_val(row2.get("ipca_acumulado_ano_pct")),
            "m2_usd": _clean_val(row2.get("cambio_dolar_medio")),
        })

    # Cálculo dos Deltas (M2 em relação a M1)
    # 1. IPCA acumulado (usa IPCA pós-Real para Itamar se aplicável)
    ipca1 = float(m1.get("ipca_pos_real_pct") or m1.get("ipca_acumulado_pct") or 0)
    ipca2 = float(m2.get("ipca_pos_real_pct") or m2.get("ipca_acumulado_pct") or 0)
    ipca_delta_pp = round(ipca2 - ipca1, 2)
    ipca_delta_relative_pct = round(((ipca2 - ipca1) / ipca1) * 100, 2) if ipca1 != 0 else 0.0

    # 2. PIB Médio Anual
    pib1 = float(m1.get("pib_medio_anual_pct") or 0)
    pib2 = float(m2.get("pib_medio_anual_pct") or 0)
    pib_delta_pp = round(pib2 - pib1, 2)
    pib_delta_relative_pct = round(((pib2 - pib1) / abs(pib1)) * 100, 2) if pib1 != 0 else 0.0

    # 3. PIB Crescimento Acumulado
    pib_acum1 = float(m1.get("pib_crescimento_acumulado_pct") or 0)
    pib_acum2 = float(m2.get("pib_crescimento_acumulado_pct") or 0)
    pib_acum_delta_pp = round(pib_acum2 - pib_acum1, 2)

    # 4. Variação Cambial
    cambio1 = float(m1.get("cambio_variacao_pct") or 0)
    cambio2 = float(m2.get("cambio_variacao_pct") or 0)
    cambio_delta_pp = round(cambio2 - cambio1, 2)

    # 5. Salário Mínimo Final em BRL e USD
    sm_brl1 = float(m1.get("salario_minimo_final_brl") or 0)
    sm_brl2 = float(m2.get("salario_minimo_final_brl") or 0)
    sm_brl_delta = round(sm_brl2 - sm_brl1, 2)
    sm_brl_relative_pct = round(((sm_brl2 - sm_brl1) / sm_brl1) * 100, 2) if sm_brl1 > 0 else 0.0

    sm_usd1 = float(m1.get("salario_minimo_final_usd") or 0)
    sm_usd2 = float(m2.get("salario_minimo_final_usd") or 0)
    sm_usd_delta = round(sm_usd2 - sm_usd1, 2)
    sm_usd_relative_pct = round(((sm_usd2 - sm_usd1) / sm_usd1) * 100, 2) if sm_usd1 > 0 else 0.0

    return {
        "mandate1": m1,
        "mandate2": m2,
        "deltas": {
            "ipca_acumulado_diff_pp": ipca_delta_pp,
            "ipca_acumulado_relative_pct": ipca_delta_relative_pct,
            "pib_medio_diff_pp": pib_delta_pp,
            "pib_medio_relative_pct": pib_delta_relative_pct,
            "pib_acumulado_diff_pp": pib_acum_delta_pp,
            "cambio_variacao_diff_pp": cambio_delta_pp,
            "salario_minimo_brl_diff": sm_brl_delta,
            "salario_minimo_brl_relative_pct": sm_brl_relative_pct,
            "salario_minimo_usd_diff": sm_usd_delta,
            "salario_minimo_usd_relative_pct": sm_usd_relative_pct
        },
        "normalized_trajectory": normalized_trajectory
    }


@router.get("/party-fidelity", response_model=Dict[str, Any])
def get_party_fidelity(db: Session = Depends(get_db)):
    """
    Retorna a análise consolidada de fidelidade e migração partidária no Congresso Nacional:
    - Balanço partidário: ganhos, perdas e saldo líquido de bancada por legenda na atual legislatura.
    - Top nômades partidários: parlamentares que mais trocaram de partido em suas carreiras.
    - Resumo e métricas gerais de infidelidade partidária.
    """
    from collections import defaultdict
    from app.models import Politician, PoliticalParty, PartyAffiliation

    party_objs = db.query(PoliticalParty).all()
    party_map = {p.id: {"sigla": p.acronym, "nome": p.full_name} for p in party_objs}

    affs = db.query(PartyAffiliation).all()
    if not affs:
        # Fallback local se o banco não tiver sido carregado
        aff_file = DATA_DIR / "filiacoes_partidarias.json"
        if not aff_file.exists():
            return {"party_balance": [], "top_nomads": [], "summary": {}}
        with open(aff_file, "r", encoding="utf-8") as f:
            raw_affs = json.load(f)
        return {
            "party_balance": [],
            "top_nomads": [],
            "summary": {"total_parlamentares": len(raw_affs), "total_nomades": 0}
        }

    by_pol = defaultdict(list)
    for a in affs:
        by_pol[a.politician_id].append(a)

    gains = defaultdict(int)
    losses = defaultdict(int)
    current_seats = defaultdict(int)
    initial_seats = defaultdict(int)
    nomads = []

    for pid, p_affs in by_pol.items():
        sorted_affs = sorted(p_affs, key=lambda x: x.start_date)
        first_aff = sorted_affs[0]
        curr_aff = next((x for x in reversed(sorted_affs) if x.end_date is None or x.is_current), sorted_affs[-1])

        first_sigla = party_map.get(first_aff.party_id, {}).get("sigla", "OUTROS")
        curr_sigla = party_map.get(curr_aff.party_id, {}).get("sigla", "OUTROS")

        initial_seats[first_sigla] += 1
        current_seats[curr_sigla] += 1

        if len(sorted_affs) > 1 and first_sigla != curr_sigla:
            losses[first_sigla] += 1
            gains[curr_sigla] += 1

        if len(sorted_affs) > 1:
            pol = db.query(Politician).filter_by(id=pid).first()
            if pol:
                history_list = []
                for x in sorted_affs:
                    sigla_x = party_map.get(x.party_id, {}).get("sigla", "S.PART.")
                    history_list.append({
                        "partido": sigla_x,
                        "data_filiacao": x.start_date.isoformat(),
                        "data_desfiliacao": x.end_date.isoformat() if x.end_date else None,
                        "motivo": x.disaffiliation_reason.value if x.disaffiliation_reason else None,
                        "is_atual": bool(x.is_current or (x.end_date is None))
                    })

                nomads.append({
                    "id": str(pol.id),
                    "nome_eleitoral": pol.electoral_name,
                    "nome_civil": pol.civil_name,
                    "cargo": "SENADOR" if pol.senado_id else "DEPUTADO FEDERAL",
                    "uf": pol.birthplace_state or (sorted_affs[-1].state or "DF"),
                    "foto_url": pol.photo_url,
                    "partido_atual": curr_sigla,
                    "total_trocas": len(sorted_affs) - 1,
                    "total_partidos": len(set(x["partido"] for x in history_list)),
                    "siglas_sequencia": [x["partido"] for x in history_list],
                    "historico": history_list
                })

    nomads.sort(key=lambda x: (x["total_trocas"], x["total_partidos"]), reverse=True)

    party_balance = []
    all_parties = set(list(current_seats.keys()) + list(initial_seats.keys()))
    for p in all_parties:
        if p in ("S.PART.", "OUTROS"):
            continue
        c = current_seats[p]
        i = initial_seats[p]
        g = gains[p]
        l = losses[p]
        net = g - l
        party_balance.append({
            "partido": p,
            "bancada_atual": c,
            "bancada_inicial": i,
            "ganhos": g,
            "perdas": l,
            "saldo_liquido": net
        })

    party_balance.sort(key=lambda x: x["saldo_liquido"], reverse=True)

    summary = {
        "total_parlamentares": len(by_pol),
        "total_nomades": len(nomads),
        "taxa_migracao_pct": round((len(nomads) / len(by_pol)) * 100, 1) if by_pol else 0,
        "partido_maior_ganho": party_balance[0]["partido"] if party_balance else None,
        "saldo_maior_ganho": party_balance[0]["saldo_liquido"] if party_balance else 0,
        "partido_maior_perda": party_balance[-1]["partido"] if party_balance else None,
        "saldo_maior_perda": party_balance[-1]["saldo_liquido"] if party_balance else 0
    }

    return {
        "party_balance": party_balance,
        "top_nomads": nomads[:35],
        "summary": summary
    }


@router.get("/wage-disparity", response_model=WageDisparityResponse)
def get_wage_disparity():
    """
    Retorna a série evolutiva confrontando:
    1) Salário Mínimo (BRL)
    2) Salário Base dos Parlamentares (BRL)
    3) Inflação Acumulada
    Mais os detalhes e votos nominais da votação do Salário Mínimo (MPV 1172/2023).
    """
    file_path = DATA_DIR / "salario_vs_inflacao.json"
    if not file_path.exists():
        from etl.extractors.salario_inflacao_extractor import SalarioInflacaoExtractor
        extractor = SalarioInflacaoExtractor()
        return extractor.run()

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/congress-composition", response_model=CongressCompositionResponse)
def get_congress_composition(
    mandate_id: str = Query("lula-2023", description="ID do mandato presidencial")
):
    """
    Retorna a composição do Congresso Nacional durante o mandato:
    - Presidentes da Câmara e do Senado (com nomes, partidos e fotos)
    - Tamanho das Bancadas dos partidos na Câmara (513) e Senado (81)
    - Alinhamento e Governabilidade do Presidente da República
    """
    file_path = DATA_DIR / "composicao_congresso.json"
    if not file_path.exists():
        from etl.extractors.composicao_extractor import save_composicao_congresso, COMPOSICAO_CONGRESSO_HISTORICO
        save_composicao_congresso()
        composicoes = COMPOSICAO_CONGRESSO_HISTORICO
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            composicoes = json.load(f)

    if mandate_id in composicoes:
        return composicoes[mandate_id]

    default_id = "lula-2023" if "lula-2023" in composicoes else list(composicoes.keys())[0]
    return composicoes[default_id]


@router.get("/federal-transfers", response_model=FederalTransfersResponse)
def get_federal_transfers(
    mandate_id: str = Query("lula-2023", description="ID do mandato presidencial"),
    area: Optional[str] = Query(None, description="Filtrar por área (Saúde, Educação, Infraestrutura, Segurança Pública)"),
    db: Session = Depends(get_db)
):
    """
    Retorna a execução orçamentária e repasses federais por Estado (UF) no mandato:
    - Grandes áreas: Saúde, Educação, Infraestrutura e Segurança Pública
    - Totais gerais, agregados por região e valores per capita
    """
    query = db.query(FederalTransferByState).filter(FederalTransferByState.mandate_id_ref == mandate_id)
    if area:
        query = query.filter(FederalTransferByState.area_tematica.ilike(f"%{area}%"))

    records = query.all()

    if not records:
        file_path = DATA_DIR / "repasses_federais_uf.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                all_data = json.load(f)
                filtered = [r for r in all_data if r["mandato_id_ref"] == mandate_id]
                if area:
                    filtered = [r for r in filtered if area.lower() in r["area_tematica"].lower()]
                items = [
                    {
                        "uf": r["uf"],
                        "estado_nome": r["estado_nome"],
                        "regiao": r["regiao"],
                        "area_tematica": r["area_tematica"],
                        "valor_pago_brl": float(r["valor_pago_brl"]),
                        "populacao_estimada": int(r.get("populacao_estimada") or 0),
                        "valor_per_capita_brl": float(r.get("valor_per_capita_brl") or 0.0)
                    }
                    for r in filtered
                ]
        else:
            items = []
    else:
        items = [
            {
                "uf": r.uf,
                "estado_nome": r.estado_nome,
                "regiao": r.regiao,
                "area_tematica": r.area_tematica,
                "valor_pago_brl": float(r.valor_pago_brl),
                "populacao_estimada": r.populacao_estimada or 0,
                "valor_per_capita_brl": float(r.valor_per_capita_brl or 0.0)
            }
            for r in records
        ]

    total_brl = sum(i["valor_pago_brl"] for i in items)
    areas_sum = {}
    regioes_sum = {}
    for i in items:
        areas_sum[i["area_tematica"]] = round(areas_sum.get(i["area_tematica"], 0.0) + i["valor_pago_brl"], 2)
        regioes_sum[i["regiao"]] = round(regioes_sum.get(i["regiao"], 0.0) + i["valor_pago_brl"], 2)

    return {
        "mandato_id": mandate_id,
        "periodo": "Execução Orçamentária Federal",
        "total_repassado_brl": round(total_brl, 2),
        "areas_resumo": areas_sum,
        "regioes_resumo": regioes_sum,
        "por_uf": items
    }


@router.get("/social-indicators")
def get_social_indicators(db: Session = Depends(get_db)):
    """
    Retorna o histórico anual nacional de indicadores sociais (1993 a 2024):
    Taxa de analfabetismo, população em extrema pobreza (% e milhões),
    insegurança alimentar grave (% e milhões) e índice de Gini.
    """
    records = db.query(AnnualSocialIndicator).order_by(AnnualSocialIndicator.year.asc()).all()
    if records:
        return [
            {
                "ano": r.year,
                "analfabetismo_pct": float(r.illiteracy_rate_pct) if r.illiteracy_rate_pct else None,
                "extrema_pobreza_pct": float(r.extreme_poverty_pct) if r.extreme_poverty_pct else None,
                "extrema_pobreza_milhoes": float(r.extreme_poverty_millions) if r.extreme_poverty_millions else None,
                "inseguranca_alimentar_pct": float(r.food_insecurity_pct) if r.food_insecurity_pct else None,
                "inseguranca_alimentar_milhoes": float(r.food_insecurity_millions) if r.food_insecurity_millions else None,
                "gini": float(r.gini_index) if r.gini_index else None,
                "fonte": r.data_source
            }
            for r in records
        ]

    file_path = DATA_DIR / "indicadores_sociais_anuais.json"
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


@router.get("/social-classes")
def get_social_classes_distribution():
    """
    Retorna a divisão oficial de classes sociais no Brasil (Critério Brasil / FGV / IBGE):
    Faixas de salários mínimos, rendimento familiar mensal correspondente, percentual da população
    e contextualização educacional.
    """
    salario_minimo_ref = 1412.00  # Salário mínimo vigente de referência

    classes = [
        {
            "classe": "Classe A",
            "faixa_salarios_minimos": "Mais de 20 salários mínimos",
            "faixa_salarios_minimos_min": 20.0,
            "faixa_salarios_minimos_max": None,
            "renda_familiar_min_brl": round(20 * salario_minimo_ref, 2),
            "renda_familiar_max_brl": None,
            "faixa_renda_formatada": f"Acima de R$ {20 * salario_minimo_ref:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "percentual_populacao": 2.8,
            "descricao": "Alta renda e topo da pirâmide. Proprietários de empresas, altos executivos, juízes e servidores do topo do funcionalismo.",
            "cor": "#10b981",
            "destaque": "Topo 3%"
        },
        {
            "classe": "Classe B",
            "faixa_salarios_minimos": "De 10 a 20 salários mínimos",
            "faixa_salarios_minimos_min": 10.0,
            "faixa_salarios_minimos_max": 20.0,
            "renda_familiar_min_brl": round(10 * salario_minimo_ref, 2),
            "renda_familiar_max_brl": round(20 * salario_minimo_ref, 2),
            "faixa_renda_formatada": f"R$ {10 * salario_minimo_ref:,.2f} a R$ {20 * salario_minimo_ref:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "percentual_populacao": 13.2,
            "descricao": "Classe média alta. Profissionais liberais consolidados, média gerência, professores universitários e empresários médios.",
            "cor": "#3b82f6",
            "destaque": "Média Alta"
        },
        {
            "classe": "Classe C",
            "faixa_salarios_minimos": "De 4 a 10 salários mínimos",
            "faixa_salarios_minimos_min": 4.0,
            "faixa_salarios_minimos_max": 10.0,
            "renda_familiar_min_brl": round(4 * salario_minimo_ref, 2),
            "renda_familiar_max_brl": round(10 * salario_minimo_ref, 2),
            "faixa_renda_formatada": f"R$ {4 * salario_minimo_ref:,.2f} a R$ {10 * salario_minimo_ref:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "percentual_populacao": 31.0,
            "descricao": "Classe média tradicional / baixa. Pequenos comerciantes, técnicos especializados, professores do ensino básico e servidores médios.",
            "cor": "#f59e0b",
            "destaque": "Média Tradicional"
        },
        {
            "classe": "Classe D",
            "faixa_salarios_minimos": "De 2 a 4 salários mínimos",
            "faixa_salarios_minimos_min": 2.0,
            "faixa_salarios_minimos_max": 4.0,
            "renda_familiar_min_brl": round(2 * salario_minimo_ref, 2),
            "renda_familiar_max_brl": round(4 * salario_minimo_ref, 2),
            "faixa_renda_formatada": f"R$ {2 * salario_minimo_ref:,.2f} a R$ {4 * salario_minimo_ref:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "percentual_populacao": 29.5,
            "descricao": "Trabalhadores formais e autônomos de serviços essenciais, operários, comércio e transporte.",
            "cor": "#f97316",
            "destaque": "Maior Grupo Formal"
        },
        {
            "classe": "Classe E",
            "faixa_salarios_minimos": "Até 2 salários mínimos",
            "faixa_salarios_minimos_min": 0.0,
            "faixa_salarios_minimos_max": 2.0,
            "renda_familiar_min_brl": 0.0,
            "renda_familiar_max_brl": round(2 * salario_minimo_ref, 2),
            "faixa_renda_formatada": f"Até R$ {2 * salario_minimo_ref:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "percentual_populacao": 23.5,
            "descricao": "Base da pirâmide e vulnerabilidade extrema. Dependentes de programas sociais, diaristas, desempregados e informais.",
            "cor": "#ef4444",
            "destaque": "Vulnerabilidade"
        }
    ]

    return {
        "salario_minimo_referencia_brl": salario_minimo_ref,
        "ano_referencia": 2024,
        "fonte": "Critério Brasil / FGV Social / IBGE PNAD Contínua",
        "resumo_populacional": {
            "maioria_populacao_acumulada_d_e_pct": 53.0,
            "texto_educativo": "Mais de 53% das famílias brasileiras sobrevivem com renda total de até 4 salários mínimos (Classes D e E). Apenas 2,8% pertencem à Classe A (acima de 20 salários mínimos), o que frequentemente distorce a percepção sobre o que é a 'classe média' no país."
        },
        "classes": classes
    }


@router.get("/social-elections")
def get_social_elections_correlation(
    ano: Optional[int] = Query(2022, description="Ano eleitoral de referência (1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022)"),
    db: Session = Depends(get_db)
):
    """
    Cruza os indicadores sociais por Estado (UF) com os resultados eleitorais presidenciais (TSE).
    Permite examinar a correlação entre extrema pobreza/analfabetismo e a preferência eleitoral.
    """
    valid_years = [1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022]
    selected_year = ano if ano in valid_years else 2022

    eleicoes_db = (
        db.query(StatePresidentialElectionResult)
        .filter(StatePresidentialElectionResult.election_year == selected_year)
        .all()
    )

    sociais_db = (
        db.query(StateSocialIndicator)
        .filter(StateSocialIndicator.year == selected_year)
        .all()
    )
    if not sociais_db:
        sociais_db = (
            db.query(StateSocialIndicator)
            .filter(StateSocialIndicator.year == 2022)
            .all()
        )

    sociais_map = {s.uf: s for s in sociais_db}

    merged = []
    for el in eleicoes_db:
        uf = el.uf
        soc = sociais_map.get(uf)

        merged.append({
            "uf": uf,
            "estado_nome": el.state_name,
            "regiao": el.region,
            "ano_eleicao": el.election_year,
            "vencedor_nome": el.winner_candidate_name,
            "vencedor_partido": el.winner_party_acronym,
            "vencedor_votos_pct": float(el.winner_votes_pct),
            "segundo_nome": el.runner_up_candidate_name,
            "segundo_partido": el.runner_up_party_acronym,
            "segundo_votos_pct": float(el.runner_up_votes_pct),
            "taxa_analfabetismo_pct": float(soc.illiteracy_rate_pct) if soc and soc.illiteracy_rate_pct else None,
            "extrema_pobreza_pct": float(soc.extreme_poverty_pct) if soc and soc.extreme_poverty_pct else None,
            "inseguranca_alimentar_pct": float(soc.food_insecurity_pct) if soc and soc.food_insecurity_pct else None,
            "indice_gini": float(soc.gini_index) if soc and soc.gini_index else None
        })

    # Ordenar por extrema pobreza decrescente
    merged.sort(key=lambda x: (x["extrema_pobreza_pct"] or 0), reverse=True)

    # Análise regional agregada
    regioes_agg = {}
    for item in merged:
        reg = item["regiao"]
        if reg not in regioes_agg:
            regioes_agg[reg] = {
                "regiao": reg,
                "total_ufs": 0,
                "soma_pobreza": 0.0,
                "soma_analfabetismo": 0.0,
                "vencedores": {}
            }
        regioes_agg[reg]["total_ufs"] += 1
        regioes_agg[reg]["soma_pobreza"] += (item["extrema_pobreza_pct"] or 0.0)
        regioes_agg[reg]["soma_analfabetismo"] += (item["taxa_analfabetismo_pct"] or 0.0)
        venc = f"{item['vencedor_nome']} ({item['vencedor_partido']})"
        regioes_agg[reg]["vencedores"][venc] = regioes_agg[reg]["vencedores"].get(venc, 0) + 1

    regioes_summary = []
    for reg, d in regioes_agg.items():
        n = d["total_ufs"] or 1
        regioes_summary.append({
            "regiao": reg,
            "total_estados": n,
            "media_extrema_pobreza_pct": round(d["soma_pobreza"] / n, 2),
            "media_analfabetismo_pct": round(d["soma_analfabetismo"] / n, 2),
            "vencedores_contagem": d["vencedores"]
        })

    return {
        "ano_eleicao": selected_year,
        "total_estados": len(merged),
        "anos_disponiveis": valid_years,
        "regioes_resumo": regioes_summary,
        "estados": merged
    }




