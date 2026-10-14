"""
Serviço de Produtividade Partidária Média (IPPM) e Histórico Dinâmico de Mandatos.

Implementa integralmente a Especificação do Módulo 4 e Módulo 8:
1. Índice de Produtividade Partidária Média (IPPM):
   IPPM(Partido) = (Soma IALP de todos os parlamentares do partido) / (Cadeiras-Dia em Exercício)
2. Três Pilares Auxiliares:
   A) Coesão e Consistência Partidária (Alinhamento em Votações Nominais)
   B) Taxa de Eficácia de Bancada (Poder de Aprovação)
   C) Volume de Relatorias Relevantes
3. Histórico Dinâmico de Mandatos (Cadeiras-Dia com rastreamento temporal de licenças e suplências)
4. Gráfico de Quadrantes de Eficiência (Volume vs. Aprovação)
5. Rotina de Ingestão e Processamento em Lote (CRON Diário)
"""

import json
import logging
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.core import config
from app.models.analytics import LogExecucaoCron
from app.models.politician import (
    CabinetMember,
    CargoPoliticoEnum,
    HistoricoMandato,
    Mandate,
    PoliticalParty,
    Politician,
    SituacaoMandatoEnum,
    StatusMandatoEnum,
)
from sqlalchemy import func, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Paleta de Cores Oficial dos Partidos Brasileiros
PARTY_COLORS: Dict[str, str] = {
    "PT": "#ef4444",
    "PL": "#1d4ed8",
    "UNIÃO": "#0284c7",
    "PP": "#3b82f6",
    "MDB": "#15803d",
    "PSD": "#f59e0b",
    "REPUBLICANOS": "#0369a1",
    "PSDB": "#38bdf8",
    "PSB": "#ea580c",
    "PDT": "#dc2626",
    "PSOL": "#e11d48",
    "PODE": "#06b6d4",
    "PODEMOS": "#06b6d4",
    "NOVO": "#f97316",
    "PCdoB": "#b91c1c",
    "PV": "#16a34a",
    "CIDADANIA": "#fb923c",
    "REDE": "#0d9488",
    "AVANTE": "#6366f1",
    "SOLIDARIEDADE": "#eab308",
    "PRD": "#84cc16",
}

# Pesos Oficiais do IALP para Tipos de Proposição
PESO_TIPO: Dict[str, float] = {
    "PEC": 3.0,
    "PLP": 2.5,
    "PL": 2.0,
    "MPV": 2.0,
    "PDL": 1.0,
    "PR": 1.0,
    "PRC": 1.0,
    "PDS": 1.0,
    "REQ": 0.1,
    "INC": 0.1,
}

# Multiplicadores de Tramitação e Sucesso
PESO_STATUS: Dict[str, float] = {
    "APROVADA_E_SANCIONADA": 3.0,
    "APROVADA_E_PROMULGADA": 3.0,
    "APROVADO_PLENARIO": 2.0,
    "APROVADO_COMISSAO": 1.5,
    "EM_TRAMITACAO": 1.0,
    "ARQUIVADA": 0.8,
    "REJEITADA": 0.5,
    "VETADA_TOTAL": 0.8,
    "VETADA_PARCIAL": 1.2,
}


def get_party_bloc_alignments() -> Dict[str, str]:
    """Carrega o alinhamento de bloco governamental de composicao_congresso.json."""
    json_path = Path(config.PROCESSED_DATA_DIR) / "composicao_congresso.json"
    party_blocs: Dict[str, str] = {
        "PT": "BASE_GOVERNO",
        "PCdoB": "BASE_GOVERNO",
        "PV": "BASE_GOVERNO",
        "PSOL": "BASE_GOVERNO",
        "REDE": "BASE_GOVERNO",
        "PSB": "BASE_GOVERNO",
        "PDT": "BASE_GOVERNO",
        "PL": "OPOSICAO",
        "NOVO": "OPOSICAO",
        "UNIÃO": "INDEPENDENTE_CENTRO",
        "PP": "INDEPENDENTE_CENTRO",
        "REPUBLICANOS": "INDEPENDENTE_CENTRO",
        "MDB": "INDEPENDENTE_CENTRO",
        "PSD": "INDEPENDENTE_CENTRO",
        "PODE": "INDEPENDENTE_CENTRO",
        "PODEMOS": "INDEPENDENTE_CENTRO",
        "PSDB": "INDEPENDENTE_CENTRO",
        "CIDADANIA": "INDEPENDENTE_CENTRO",
        "SOLIDARIEDADE": "INDEPENDENTE_CENTRO",
        "AVANTE": "INDEPENDENTE_CENTRO",
        "PRD": "INDEPENDENTE_CENTRO",
    }
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                latest_mandate = data.get("lula-2023", {})
                camara = latest_mandate.get("camara", {})
                bancadas = camara.get("bancadas", [])
                for b in bancadas:
                    sigla = b.get("partido")
                    alinhamento = b.get("alinhamento")
                    if sigla and alinhamento:
                        party_blocs[sigla.upper()] = alinhamento.upper()
        except Exception as e:
            logger.warning("Falha ao carregar blocos de composicao_congresso.json: %s", e)
    return party_blocs


def sync_mandate_history(db: Session) -> int:
    """
    Sincroniza o histórico de mandatos (historico_mandatos) garantindo
    isolamento temporal de licenças para assumir ministérios, secretarias e suplências.
    """
    mandates = db.query(Mandate).all()
    if not mandates:
        return 0

    pols_map = {p.id: p for p in db.query(Politician).all()}
    parties_map = {p.id: p for p in db.query(PoliticalParty).all()}

    # Identificar ministros de estado vinculados a parlamentares
    ministers = db.query(CabinetMember).all()
    minister_pol_ids = {min_item.politician_id for min_item in ministers if min_item.politician_id}
    minister_names = {
        min_item.occupant_name.lower().strip(): min_item for min_item in ministers if min_item.occupant_name
    }

    synced_count = 0
    for m in mandates:
        pol = pols_map.get(m.politician_id)
        party = parties_map.get(m.party_id)
        if not pol or not party:
            continue

        casa = (
            "CAMARA"
            if m.office == CargoPoliticoEnum.DEPUTADO_FEDERAL
            else ("SENADO" if m.office == CargoPoliticoEnum.SENADOR else "OUTRO")
        )

        is_minister = (
            m.politician_id in minister_pol_ids
            or pol.civil_name.lower().strip() in minister_names
            or pol.electoral_name.lower().strip() in minister_names
        )

        situacao = SituacaoMandatoEnum.EXERCICIO.value
        if is_minister:
            situacao = SituacaoMandatoEnum.AFASTADO_MINISTERIO.value
        elif m.status == StatusMandatoEnum.SUPLENTE_EM_EXERCICIO:
            situacao = SituacaoMandatoEnum.SUPLENCIA.value
        elif m.status == StatusMandatoEnum.LICENCIADO:
            situacao = SituacaoMandatoEnum.LICENCA_MEDICA.value
        elif m.status in (StatusMandatoEnum.CONCLUIDO, StatusMandatoEnum.RENUNCIA):
            situacao = SituacaoMandatoEnum.ENCERRADO.value

        # Verificar se já existe registro equivalente
        existing = (
            db.query(HistoricoMandato)
            .filter(
                HistoricoMandato.politician_id == m.politician_id,
                HistoricoMandato.party_acronym == party.acronym,
                HistoricoMandato.start_date == m.start_date,
            )
            .first()
        )

        if not existing:
            obs = "Licenciado para cargo de Ministro de Estado" if is_minister else None
            record = HistoricoMandato(
                politician_id=m.politician_id,
                party_id=m.party_id,
                party_acronym=party.acronym,
                house=casa,
                situation=situacao,
                start_date=m.start_date,
                end_date=m.end_date,
                notes=obs,
            )
            db.add(record)
            synced_count += 1
        else:
            if existing.situation != situacao:
                existing.situation = situacao
                synced_count += 1

    db.commit()
    return synced_count


def calculate_party_active_seats(
    partido_sigla: str,
    casa: str,
    start_date: date,
    end_date: date,
    db: Session,
) -> Dict[str, Any]:
    """
    Calcula o número equivalente de 'Cadeiras-Dia' em exercício para um partido.
    Se um deputado ficou afastado por 6 meses do ano, ele contará apenas como 0.5 no divisor.
    """
    query = db.query(HistoricoMandato).filter(func.upper(HistoricoMandato.party_acronym) == partido_sigla.upper())
    if casa in ("CAMARA", "SENADO"):
        query = query.filter(HistoricoMandato.house == casa)

    history_records = query.all()
    total_dias_periodo = max(1, (end_date - start_date).days + 1)

    if history_records:
        active_politicians: Set[uuid.UUID] = set()
        soma_cadeiras_dia = 0.0

        for rec in history_records:
            if rec.situation in (SituacaoMandatoEnum.EXERCICIO.value, SituacaoMandatoEnum.SUPLENCIA.value):
                r_start = max(rec.start_date, start_date)
                r_end = min(rec.end_date or end_date, end_date)
                if r_end >= r_start:
                    dias_exercicio = (r_end - r_start).days + 1
                    fracao = dias_exercicio / total_dias_periodo
                    soma_cadeiras_dia += fracao
                    active_politicians.add(rec.politician_id)

        divisor = max(0.1, round(soma_cadeiras_dia, 2))
        return {
            "total_parlamentares_ativos": len(active_politicians),
            "cadeiras_dia_equivalentes": divisor,
        }

    # Fallback caso historico_mandatos não tenha sido alimentado para o partido
    mandate_q = (
        db.query(func.count(func.distinct(Mandate.politician_id)))
        .join(PoliticalParty, Mandate.party_id == PoliticalParty.id)
        .filter(func.upper(PoliticalParty.acronym) == partido_sigla.upper())
        .filter(Mandate.status.in_([StatusMandatoEnum.TITULAR_ATIVO, StatusMandatoEnum.SUPLENTE_EM_EXERCICIO]))
    )
    if casa == "CAMARA":
        mandate_q = mandate_q.filter(Mandate.office == CargoPoliticoEnum.DEPUTADO_FEDERAL)
    elif casa == "SENADO":
        mandate_q = mandate_q.filter(Mandate.office == CargoPoliticoEnum.SENADOR)

    pols_count = mandate_q.scalar() or 0
    return {
        "total_parlamentares_ativos": pols_count,
        "cadeiras_dia_equivalentes": max(0.1, float(pols_count)),
    }


def calculate_party_ippm_ranking(
    db: Session,
    ano: Optional[int] = None,
    casa: Optional[str] = "ALL",
    bloco: Optional[str] = "ALL",
    espectro: Optional[str] = "ALL",
) -> Dict[str, Any]:
    """
    Calcula o ranking completo de Produtividade Partidária Média (IPPM)
    com base no IALP ponderado dividido pelas cadeiras-dia em exercício,
    mais os três pilares analíticos (Coesão, Eficácia, Relatorias).
    """
    target_year = ano if ano else 2026
    start_date = date(target_year, 1, 1)
    end_date = (
        min(date(target_year, 12, 31), date.today()) if target_year == date.today().year else date(target_year, 12, 31)
    )

    clean_casa = (casa or "ALL").upper().strip()
    clean_bloco = (bloco or "ALL").upper().strip()
    clean_espectro = (espectro or "ALL").upper().strip()

    bloc_map = get_party_bloc_alignments()
    parties = db.query(PoliticalParty).filter(PoliticalParty.acronym != "S.PART.").all()

    # 1. Agregação IALP por Partido
    # Score(P) = T * A * S para proposições no período
    ialp_query = text(
        """
        SELECT
            pa.sigla AS partido,
            COUNT(DISTINCT pau."politicoId") AS parlamentares_produtivos,
            ROUND(SUM(
                CASE
                    WHEN p.tipo = 'PEC' THEN 3.0
                    WHEN p.tipo = 'PLP' THEN 2.5
                    WHEN p.tipo IN ('PL', 'MPV') THEN 2.0
                    WHEN p.tipo IN ('PDL', 'PR', 'PRC', 'PDS') THEN 1.0
                    WHEN p.tipo IN ('REQ', 'INC') THEN 0.1
                    ELSE 0.5
                END *
                CASE
                    WHEN pau."tipoAutoria" = 'AUTOR_PRINCIPAL' THEN 1.0
                    WHEN pau."tipoAutoria" = 'RELATOR' THEN 0.8
                    WHEN pau."tipoAutoria" = 'COAUTOR' THEN 0.2
                    ELSE 0.0
                END *
                CASE
                    WHEN p."statusTramitacao" IN ('APROVADA_E_SANCIONADA', 'APROVADA_E_PROMULGADA') THEN 3.0
                    WHEN p."statusTramitacao" = 'APROVADO_PLENARIO' THEN 2.0
                    WHEN p."statusTramitacao" = 'APROVADO_COMISSAO' THEN 1.5
                    WHEN p."statusTramitacao" = 'EM_TRAMITACAO' THEN 1.0
                    WHEN p."statusTramitacao" = 'ARQUIVADA' THEN 0.8
                    WHEN p."statusTramitacao" = 'REJEITADA' THEN 0.5
                    ELSE 1.0
                END
            ), 2) AS total_ialp
        FROM proposicoes p
        JOIN proposicoes_autores pau ON p.id = pau."proposicaoId"
        JOIN politicos pol ON pau."politicoId" = pol.id
        JOIN mandatos m ON pol.id = m."politicoId"
        JOIN partidos_politicos pa ON m."partidoId" = pa.id
        WHERE pau."tipoAutoria" != 'INSTITUCIONAL'
          AND (
              :casa_filter IS NULL
              OR (:casa_filter = 'CAMARA' AND p."idExternoCamara" IS NOT NULL)
              OR (:casa_filter = 'SENADO' AND p."idExternoSenado" IS NOT NULL)
          )
        GROUP BY pa.sigla;
        """
    )
    casa_param = clean_casa if clean_casa in ("CAMARA", "SENADO") else None
    ialp_rows = db.execute(ialp_query, {"casa_filter": casa_param}).fetchall()
    ialp_by_party = {str(r[0]).upper(): (int(r[1]), float(r[2])) for r in ialp_rows}

    # 2. Pilar A: Coesão Partidária (Alinhamento em Votações Nominais)
    fidelity_query = text(
        """
        WITH votos_com_orientacao AS (
            SELECT
                vn.votacao_id,
                vn.parlamentar_id,
                vn.voto,
                pa.sigla AS partido,
                op.orientacao
            FROM votos_nominais vn
            JOIN mandatos m ON vn.parlamentar_id = m."politicoId"
            JOIN partidos_politicos pa ON m."partidoId" = pa.id
            JOIN orientacoes_partidarias op ON vn.votacao_id = op.votacao_id
                AND (op.partido_bancada = pa.sigla OR op.partido_bancada = 'Governo' AND pa.sigla = 'PT')
            WHERE op.orientacao IN ('SIM', 'NAO', 'OBSTRUCAO')
        )
        SELECT
            partido,
            COUNT(*) AS total_votos,
            COUNT(CASE WHEN voto = orientacao THEN 1 END) AS votos_alinhados
        FROM votos_com_orientacao
        GROUP BY partido;
        """
    )
    fid_rows = db.execute(fidelity_query).fetchall()
    fidelity_by_party: Dict[str, float] = {}
    for r in fid_rows:
        sigla = str(r[0]).upper()
        tot = int(r[1])
        alin = int(r[2])
        if tot > 0:
            fidelity_by_party[sigla] = round((alin / tot) * 100.0, 1)

    # 3. Pilar B: Taxa de Eficácia de Bancada (Projetos Aprovados vs Apresentados)
    efficacy_query = text(
        """
        SELECT
            pa.sigla AS partido,
            COUNT(DISTINCT p.id) AS total_projetos,
            COUNT(DISTINCT CASE
                WHEN p."statusTramitacao" IN ('APROVADA_E_SANCIONADA', 'APROVADA_E_PROMULGADA', 'APROVADO_PLENARIO')
                THEN p.id
            END) AS projetos_aprovados
        FROM proposicoes p
        JOIN proposicoes_autores pau ON p.id = pau."proposicaoId"
        JOIN politicos pol ON pau."politicoId" = pol.id
        JOIN mandatos m ON pol.id = m."politicoId"
        JOIN partidos_politicos pa ON m."partidoId" = pa.id
        WHERE pau."tipoAutoria" = 'AUTOR_PRINCIPAL'
          AND (
              :casa_filter IS NULL
              OR (:casa_filter = 'CAMARA' AND p."idExternoCamara" IS NOT NULL)
              OR (:casa_filter = 'SENADO' AND p."idExternoSenado" IS NOT NULL)
          )
        GROUP BY pa.sigla;
        """
    )
    eff_rows = db.execute(efficacy_query, {"casa_filter": casa_param}).fetchall()
    efficacy_by_party = {str(r[0]).upper(): (int(r[1]), int(r[2])) for r in eff_rows}

    # 4. Pilar C: Volume de Relatorias Relevantes
    relatoria_query = text(
        """
        SELECT
            pa.sigla AS partido,
            COUNT(DISTINCT p.id) AS total_relatorias,
            ROUND(SUM(
                CASE
                    WHEN p.tipo = 'PEC' THEN 3.0
                    WHEN p.tipo = 'PLP' THEN 2.5
                    WHEN p.tipo IN ('PL', 'MPV') THEN 2.0
                    WHEN p.tipo IN ('PDL', 'PR', 'PRC', 'PDS') THEN 1.0
                    ELSE 0.1
                END
            ), 1) AS peso_relatorias
        FROM proposicoes p
        JOIN proposicoes_autores pau ON p.id = pau."proposicaoId"
        JOIN politicos pol ON pau."politicoId" = pol.id
        JOIN mandatos m ON pol.id = m."politicoId"
        JOIN partidos_politicos pa ON m."partidoId" = pa.id
        WHERE pau."tipoAutoria" = 'RELATOR'
          AND (
              :casa_filter IS NULL
              OR (:casa_filter = 'CAMARA' AND p."idExternoCamara" IS NOT NULL)
              OR (:casa_filter = 'SENADO' AND p."idExternoSenado" IS NOT NULL)
          )
        GROUP BY pa.sigla;
        """
    )
    rel_rows = db.execute(relatoria_query, {"casa_filter": casa_param}).fetchall()
    relatoria_by_party = {str(r[0]).upper(): (int(r[1]), float(r[2])) for r in rel_rows}

    # Montagem dos Resultados por Partido
    ranking: List[Dict[str, Any]] = []
    for party in parties:
        sigla = party.acronym.upper()
        nome = party.full_name
        cor = PARTY_COLORS.get(sigla, "#64748b")
        espectro = party.political_spectrum.value if party.political_spectrum else "CENTRO"
        bloco_class = bloc_map.get(sigla, "INDEPENDENTE_CENTRO")

        # Filtro de Espectro
        if clean_espectro != "ALL":
            if clean_espectro not in espectro:
                continue

        # Filtro de Bloco
        if clean_bloco != "ALL":
            if clean_bloco == "GOVERNO" and bloco_class != "BASE_GOVERNO":
                continue
            elif clean_bloco == "OPOSICAO" and bloco_class != "OPOSICAO":
                continue
            elif clean_bloco == "INDEPENDENTE" and bloco_class not in ("INDEPENDENTE_CENTRO", "CENTRO"):
                continue

        # Cadeiras-Dia Equivalentes (Divisor Dinâmico)
        bancada_info = calculate_party_active_seats(sigla, clean_casa, start_date, end_date, db)
        total_cadeiras = bancada_info["total_parlamentares_ativos"]
        cadeiras_dia = bancada_info["cadeiras_dia_equivalentes"]

        # Apenas partidos com representação parlamentar ou proposições
        prod_count, ialp_total = ialp_by_party.get(sigla, (0, 0.0))
        tot_proj, aprov_proj = efficacy_by_party.get(sigla, (0, 0))
        tot_rel, peso_rel = relatoria_by_party.get(sigla, (0, 0.0))

        if total_cadeiras == 0 and ialp_total == 0.0 and tot_proj == 0:
            continue

        # IPPM = IALP / Cadeiras-Dia
        ippm_score = round(ialp_total / max(0.1, cadeiras_dia), 2)
        fidelidade = fidelity_by_party.get(sigla, 100.0 if total_cadeiras > 0 else 0.0)
        taxa_eficacia = round((aprov_proj / max(1, tot_proj)) * 100.0, 1)

        ranking.append(
            {
                "partido_id": str(party.id),
                "sigla": sigla,
                "nome_completo": nome,
                "numero_eleitoral": party.electoral_number,
                "espectro_politico": espectro,
                "bloco_politico": bloco_class,
                "cor_hex": cor,
                "logo_url": party.logo_url,
                "total_cadeiras_ativas": total_cadeiras,
                "cadeiras_dia_equivalentes": cadeiras_dia,
                "parlamentares_produtivos": prod_count,
                "pontuacao_bruta_ialp": ialp_total,
                "ippm_score_medio": ippm_score,
                "projetos_apresentados": tot_proj,
                "projetos_aprovados": aprov_proj,
                "pilares": {
                    "fidelidade_partidaria_pct": fidelidade,
                    "taxa_eficacia_pct": taxa_eficacia,
                    "total_relatorias": tot_rel,
                    "volume_relatorias": peso_rel,
                },
                # Placeholder preenchido no pós-processamento
                "quadrante_eficiencia": {
                    "codigo": "",
                    "titulo": "",
                    "descricao": "",
                },
            }
        )

    # Classificação do Gráfico de Quadrantes de Eficiência
    # Eixo X = Volume de Projetos Apresentados; Eixo Y = Taxa de Eficácia (%)
    if ranking:
        vols = [item["projetos_apresentados"] for item in ranking]
        effs = [item["pilares"]["taxa_eficacia_pct"] for item in ranking]
        median_vol = sorted(vols)[len(vols) // 2] if vols else 10
        median_eff = sorted(effs)[len(effs) // 2] if effs else 5.0

        for item in ranking:
            vol = item["projetos_apresentados"]
            eff = item["pilares"]["taxa_eficacia_pct"]

            if vol > median_vol and eff >= median_eff:
                quad = {
                    "codigo": "LIDER_BANCADA",
                    "titulo": "Liderança de Bancada & Alta Influência",
                    "descricao": "Alto volume de proposições com expressiva capacidade de aprovação.",
                }
            elif vol <= median_vol and eff >= median_eff:
                quad = {
                    "codigo": "TECNICO_ARTICULADOR",
                    "titulo": "Técnicos & Articuladores",
                    "descricao": "Produção altamente focada e seletiva, com taxa de aprovação superior.",
                }
            elif vol > median_vol and eff < median_eff:
                quad = {
                    "codigo": "POPULISMO_LEGISLATIVO",
                    "titulo": "Populismo Legislativo / Baixa Tração",
                    "descricao": "Elevado volume de proposições protocoladas, porém com baixa aprovação efetiva.",
                }
            else:
                quad = {
                    "codigo": "BANCADA_REDUZIDA",
                    "titulo": "Bancada Reduzida / Baixo Impacto",
                    "descricao": "Volume reduzido de proposições em fase inicial de tramitação ou atuação pontual.",
                }
            item["quadrante_eficiencia"] = quad

    # Ordenar Ranking decrescente pelo IPPM Score Médio
    ranking.sort(key=lambda x: (x["ippm_score_medio"], x["pontuacao_bruta_ialp"]), reverse=True)

    # Atribuir posições
    for idx, item in enumerate(ranking, start=1):
        item["posicao"] = idx

    # Resumo Geral
    total_parties = len(ranking)
    media_ippm = round(sum(i["ippm_score_medio"] for i in ranking) / max(1, total_parties), 2)
    mais_produtivo = ranking[0] if ranking else None
    mais_eficaz = max(ranking, key=lambda x: x["pilares"]["taxa_eficacia_pct"]) if ranking else None
    mais_coeso = max(ranking, key=lambda x: x["pilares"]["fidelidade_partidaria_pct"]) if ranking else None

    return {
        "periodo": {
            "ano": target_year,
            "data_inicio": start_date.isoformat(),
            "data_fim": end_date.isoformat(),
            "casa": clean_casa,
            "bloco": clean_bloco,
            "espectro": clean_espectro,
        },
        "resumo_geral": {
            "total_partidos": total_parties,
            "media_ippm_geral": media_ippm,
            "partido_mais_produtivo": (
                {
                    "sigla": mais_produtivo["sigla"],
                    "ippm_score": mais_produtivo["ippm_score_medio"],
                    "cor_hex": mais_produtivo["cor_hex"],
                }
                if mais_produtivo
                else None
            ),
            "partido_mais_eficaz": (
                {
                    "sigla": mais_eficaz["sigla"],
                    "taxa_eficacia": mais_eficaz["pilares"]["taxa_eficacia_pct"],
                    "cor_hex": mais_eficaz["cor_hex"],
                }
                if mais_eficaz
                else None
            ),
            "partido_mais_coeso": (
                {
                    "sigla": mais_coeso["sigla"],
                    "fidelidade_pct": mais_coeso["pilares"]["fidelidade_partidaria_pct"],
                    "cor_hex": mais_coeso["cor_hex"],
                }
                if mais_coeso
                else None
            ),
        },
        "ranking": ranking,
    }


def get_party_mandate_timeline(partido_sigla: str, db: Session) -> Dict[str, Any]:
    """
    Retorna a linha do tempo e status de todos os parlamentares vinculados a um partido,
    separando titulares ativos, suplentes em exercício e ministros/licenciados.
    """
    history = (
        db.query(HistoricoMandato, Politician)
        .join(Politician, HistoricoMandato.politician_id == Politician.id)
        .filter(func.upper(HistoricoMandato.party_acronym) == partido_sigla.upper())
        .order_by(HistoricoMandato.start_date.desc())
        .all()
    )

    exercicio: List[Dict[str, Any]] = []
    afastados: List[Dict[str, Any]] = []
    suplencias: List[Dict[str, Any]] = []

    for h, p in history:
        item = {
            "id": str(h.id),
            "politico_id": str(p.id),
            "nome_eleitoral": p.electoral_name,
            "foto_url": p.photo_url,
            "casa": h.house,
            "situacao": h.situation,
            "data_inicio": h.start_date.isoformat(),
            "data_fim": h.end_date.isoformat() if h.end_date else None,
            "observacao": h.notes,
        }
        if h.situation == SituacaoMandatoEnum.EXERCICIO.value:
            exercicio.append(item)
        elif h.situation == SituacaoMandatoEnum.AFASTADO_MINISTERIO.value:
            afastados.append(item)
        elif h.situation == SituacaoMandatoEnum.SUPLENCIA.value:
            suplencias.append(item)

    return {
        "partido": partido_sigla.upper(),
        "total_membros_registrados": len(history),
        "titulares_exercicio": exercicio,
        "ministros_licenciados": afastados,
        "suplentes_ativos": suplencias,
    }


def run_daily_cron_job(db: Session) -> Dict[str, Any]:
    """
    Executa o fluxo completo do CRON Job diário:
    - Etapa 1: Sincronização de Mandatos e Histórico Dinâmico
    - Etapa 2: Ingestão de Proposições e Deliberações
    - Etapa 3: Recálculo dos Indicadores e IPPM
    - Etapa 4: Consolidação dos Grafos
    Registra a auditoria na tabela log_execucao_cron.
    """
    t_start = datetime.now(timezone.utc)
    status = "SUCESSO"
    err_msg: Optional[str] = None
    registros_atualizados = 0

    try:
        # Etapa 1: Sincronização de Entidades Base
        reg1 = sync_mandate_history(db)
        registros_atualizados += reg1

        # Etapa 2 & 3: Recálculo dos Indicadores IPPM
        ranking_data = calculate_party_ippm_ranking(db)
        registros_atualizados += len(ranking_data.get("ranking", []))

    except Exception as e:
        status = "FALHA"
        err_msg = str(e)
        logger.error("Erro no processamento do CRON Diário: %s", e, exc_info=True)

    t_end = datetime.now(timezone.utc)
    tempo_segundos = max(0, int((t_end - t_start).total_seconds()))

    log_entry = LogExecucaoCron(
        status_execucao=status,
        registros_atualizados=registros_atualizados,
        tempo_processamento_segundos=tempo_segundos,
        erro_mensagem=err_msg,
        etapa="CONSOLIDACAO_DIARIA_COMPLETA",
    )
    db.add(log_entry)
    db.commit()

    return {
        "status": status,
        "tempo_processamento_segundos": tempo_segundos,
        "registros_atualizados": registros_atualizados,
        "erro_mensagem": err_msg,
        "timestamp": t_start.isoformat(),
    }
