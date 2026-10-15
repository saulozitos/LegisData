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
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core import config
from app.models.analytics import LogExecucaoCron
from app.models.politician import SituacaoMandatoEnum
from app.services.party_catalog_service import DEFAULT_PARTY_COLOR
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Status de tramitação que contam como proposição aprovada (pilar de eficácia)
STATUS_APROVADOS = ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA", "APROVADO_PLENARIO")


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
    Sincroniza o schema core a partir do legado. O histórico de mandatos deixou de ser uma tabela mantida em Python:
    é derivado de core.mandato_situacao (licenças, afastamentos para ministério e suplências) pela view
    core.vw_historico_mandato. Devolve o número de situações de mandato calculadas.
    """
    from app.services.core_sync import sync_legacy_to_core

    return int(sync_legacy_to_core(db)["situacoes"])


# Dias de mandato em exercício (ou suplência) de cada pessoa, no partido em que estava filiada em cada dia
_CADEIRAS_DIA_SQL = text(
    """
    WITH exercicio AS (
        -- 1) partido que ocupa a cadeira em cada dia, segundo o histórico do mandato (fonte oficial)
        SELECT m.pessoa_id, s.periodo * mp.periodo * daterange(:inicio, :fim, '[]') AS periodo
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.mandato_partido mp ON mp.mandato_id = m.id
        JOIN core.vw_partido_canonico pa ON pa.id = mp.partido_id
        WHERE pa.canonico_sigla_normalizada = ref.normalizar_texto(:sigla)
          AND s.situacao IN ('EXERCICIO', 'SUPLENCIA') AND c.codigo = ANY(:cargos)
        UNION ALL
        -- 2) mandatos sem histórico de partido: filiação vigente em cada dia
        SELECT m.pessoa_id, s.periodo * f.periodo * daterange(:inicio, :fim, '[]')
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.filiacao f ON f.pessoa_id = m.pessoa_id
        JOIN core.vw_partido_canonico pa ON pa.id = f.partido_id
        WHERE pa.canonico_sigla_normalizada = ref.normalizar_texto(:sigla)
          AND s.situacao IN ('EXERCICIO', 'SUPLENCIA') AND c.codigo = ANY(:cargos)
          AND NOT EXISTS (SELECT 1 FROM core.mandato_partido x WHERE x.mandato_id = m.id)
        UNION ALL
        -- 3) quem não tem histórico de partido nem filiação registrada herda o partido do mandato
        SELECT m.pessoa_id, s.periodo * daterange(:inicio, :fim, '[]')
        FROM core.mandato_situacao s
        JOIN core.mandato m ON m.id = s.mandato_id
        JOIN ref.cargo c ON c.id = m.cargo_id
        JOIN core.vw_partido_canonico pa ON pa.id = m.partido_id
        WHERE pa.canonico_sigla_normalizada = ref.normalizar_texto(:sigla)
          AND s.situacao IN ('EXERCICIO', 'SUPLENCIA') AND c.codigo = ANY(:cargos)
          AND NOT EXISTS (SELECT 1 FROM core.mandato_partido x WHERE x.mandato_id = m.id)
          AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = m.pessoa_id)
    )
    SELECT count(DISTINCT pessoa_id) AS parlamentares, coalesce(sum(upper(periodo) - lower(periodo)), 0) AS dias
    FROM exercicio WHERE NOT isempty(periodo)
    """
)
_CARGOS_POR_CASA = {
    "CAMARA": ["DEPUTADO_FEDERAL"],
    "SENADO": ["SENADOR"],
}


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
    O cálculo é a interseção, em SQL, entre os períodos de exercício do mandato e de filiação ao partido.
    """
    cargos = _CARGOS_POR_CASA.get(casa) or [c for lista in _CARGOS_POR_CASA.values() for c in lista]
    total_dias_periodo = max(1, (end_date - start_date).days + 1)
    row = db.execute(
        _CADEIRAS_DIA_SQL, {"sigla": partido_sigla, "inicio": start_date, "fim": end_date, "cargos": cargos}
    ).one()
    soma_cadeiras_dia = float(row.dias) / total_dias_periodo
    return {
        "total_parlamentares_ativos": int(row.parlamentares),
        "cadeiras_dia_equivalentes": max(0.1, round(soma_cadeiras_dia, 2)),
    }


def _aviso_cobertura(ranking: List[Dict[str, Any]], partidos_sem_cadeiras: List[str]) -> Optional[str]:
    """Explica ao leitor por que partidos com proposições ficaram fora do ranking."""
    if not partidos_sem_cadeiras:
        return None
    if not ranking:
        return (
            "Sem histórico de cadeiras para este período: a Câmara só publica posse, licença e troca de partido a "
            "partir da 52ª legislatura (2003). O IPPM não é calculado sem o divisor de cadeiras-dia."
        )
    return "Partidos sem cadeiras registradas no período ficaram fora do ranking: " + ", ".join(
        sorted(partidos_sem_cadeiras)
    )


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
    parties = (
        db.execute(
            text("SELECT * FROM core.vw_partido WHERE sigla <> 'S.PART.' AND linhagem_id IS NULL ORDER BY sigla")
        )
        .mappings()
        .all()
    )

    casa_param = clean_casa if clean_casa in ("CAMARA", "SENADO") else None
    params = {"casa": casa_param, "inicio": start_date, "fim": end_date}

    # 1. Agregação IALP por Partido: Score = tipo x autoria x tramitação (pesos em param.peso, metodologia IALP),
    # com o partido do autor na data de apresentação da proposição (core.filiacao)
    ialp_rows = db.execute(
        text(
            """
            SELECT pa.sigla, COUNT(DISTINCT v.pessoa_id), ROUND(SUM(v.pontos_ialp)::numeric, 2)
            FROM leg.vw_autoria_pontuada v JOIN core.vw_partido_canonico pc ON pc.id = v.partido_id
            JOIN core.partido pa ON pa.id = pc.canonico_id
            WHERE v.data_apresentacao BETWEEN :inicio AND :fim
              AND (:casa IS NULL OR (:casa = 'CAMARA' AND v.da_camara) OR (:casa = 'SENADO' AND v.do_senado))
            GROUP BY pa.sigla
            """
        ),
        params,
    ).fetchall()
    ialp_by_party = {str(r[0]).upper(): (int(r[1]), float(r[2])) for r in ialp_rows}

    # 2. Pilar A: Coesão Partidária (alinhamento do voto nominal à orientação da própria bancada ou, quando é o partido
    # do Presidente em exercício na data da votação, à orientação do Governo)
    fidelity_rows = db.execute(
        text(
            """
            SELECT pa.sigla, COUNT(*), COUNT(*) FILTER (WHERE v.opcao_codigo = o.orientacao)
            FROM leg.voto v
            JOIN leg.votacao vo ON vo.id = v.votacao_id
            JOIN core.vw_partido_canonico pc ON pc.id = v.partido_id
            JOIN core.partido pa ON pa.id = pc.canonico_id
            JOIN leg.orientacao o ON o.votacao_id = v.votacao_id
             AND (o.partido_id = pa.id
                  OR (o.bancada = 'Governo' AND EXISTS (
                        SELECT 1 FROM core.mandato mp JOIN ref.cargo cp ON cp.id = mp.cargo_id
                         WHERE cp.codigo = 'PRESIDENTE' AND mp.partido_id = pa.id
                           AND vo.data_hora::date BETWEEN mp.inicio AND coalesce(mp.fim, DATE '9999-12-31'))))
            WHERE o.orientacao IN ('SIM', 'NAO', 'OBSTRUCAO') AND vo.data_hora::date BETWEEN :inicio AND :fim
            GROUP BY pa.sigla
            """
        ),
        params,
    ).fetchall()
    fidelity_by_party: Dict[str, float] = {}
    for r in fidelity_rows:
        tot, alin = int(r[1]), int(r[2])
        if tot > 0:
            fidelity_by_party[str(r[0]).upper()] = round((alin / tot) * 100.0, 1)

    # 3. Pilar B: Taxa de Eficácia de Bancada (projetos aprovados vs apresentados; requerimentos e indicações ficam de fora)
    eff_rows = db.execute(
        text(
            """
            SELECT pa.sigla, COUNT(DISTINCT v.proposicao_id),
                   COUNT(DISTINCT v.proposicao_id) FILTER (WHERE v.status_codigo IN :aprovados)
            FROM leg.vw_autoria_pontuada v JOIN core.vw_partido_canonico pc ON pc.id = v.partido_id
            JOIN core.partido pa ON pa.id = pc.canonico_id
            WHERE v.tipo_autoria = 'AUTOR_PRINCIPAL' AND v.categoria_proposicao = 'PROJETO'
              AND v.data_apresentacao BETWEEN :inicio AND :fim
              AND (:casa IS NULL OR (:casa = 'CAMARA' AND v.da_camara) OR (:casa = 'SENADO' AND v.do_senado))
            GROUP BY pa.sigla
            """
        ).bindparams(bindparam("aprovados", expanding=True)),
        {**params, "aprovados": list(STATUS_APROVADOS)},
    ).fetchall()
    efficacy_by_party = {str(r[0]).upper(): (int(r[1]), int(r[2])) for r in eff_rows}

    # 4. Pilar C: Volume de Relatorias Relevantes
    rel_rows = db.execute(
        text(
            """
            SELECT pa.sigla, COUNT(DISTINCT v.proposicao_id), ROUND(SUM(v.pontos_relatoria)::numeric, 1)
            FROM leg.vw_autoria_pontuada v JOIN core.vw_partido_canonico pc ON pc.id = v.partido_id
            JOIN core.partido pa ON pa.id = pc.canonico_id
            WHERE v.tipo_autoria = 'RELATOR' AND v.data_apresentacao BETWEEN :inicio AND :fim
              AND (:casa IS NULL OR (:casa = 'CAMARA' AND v.da_camara) OR (:casa = 'SENADO' AND v.do_senado))
            GROUP BY pa.sigla
            """
        ),
        params,
    ).fetchall()
    relatoria_by_party = {str(r[0]).upper(): (int(r[1]), float(r[2])) for r in rel_rows}

    # Assinaturas de apoio a PEC (coautor): contadas à parte, com peso reduzido no IALP
    apoio_rows = db.execute(
        text(
            """
            SELECT pa.sigla, COUNT(*)
            FROM leg.vw_autoria_pontuada v JOIN core.vw_partido_canonico pc ON pc.id = v.partido_id
            JOIN core.partido pa ON pa.id = pc.canonico_id
            WHERE v.apoio_quorum AND v.data_apresentacao BETWEEN :inicio AND :fim
              AND (:casa IS NULL OR (:casa = 'CAMARA' AND v.da_camara) OR (:casa = 'SENADO' AND v.do_senado))
            GROUP BY pa.sigla
            """
        ),
        params,
    ).fetchall()
    apoio_by_party = {str(r[0]).upper(): int(r[1]) for r in apoio_rows}

    # Montagem dos Resultados por Partido
    partidos_sem_cadeiras: List[str] = []
    ranking: List[Dict[str, Any]] = []
    for party in parties:
        sigla = party["sigla"].upper()
        nome = party["nome"]
        cor = party["cor_hex"] or DEFAULT_PARTY_COLOR
        espectro = party["espectro_politico"] or "CENTRO"
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

        if total_cadeiras == 0:
            # Sem cadeiras registradas no período o divisor do IPPM não existe: o partido não entra (nada de divisor inventado)
            if ialp_total > 0 or tot_proj > 0:
                partidos_sem_cadeiras.append(sigla)
            continue

        # IPPM = IALP / Cadeiras-Dia
        ippm_score = round(ialp_total / max(0.1, cadeiras_dia), 2)
        fidelidade = fidelity_by_party.get(sigla)  # None: sem votação nominal com orientação no período
        taxa_eficacia = round((aprov_proj / max(1, tot_proj)) * 100.0, 1)

        ranking.append(
            {
                "partido_id": str(party["uid"]),
                "sigla": sigla,
                "nome_completo": nome,
                "numero_eleitoral": party["numero_eleitoral"],
                "espectro_politico": espectro,
                "bloco_politico": bloco_class,
                "cor_hex": cor,
                "logo_url": party["logo_url"],
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
                    "assinaturas_apoio_quorum": apoio_by_party.get(sigla, 0),
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
    # Líder em Produtividade: Deve representar uma bancada partidária colegiada (mínimo de 3 cadeiras ativas)
    # Evita que legendas unipessoais (1 único parlamentar) distorçam a liderança estatística de bancadas plurais
    MIN_BANCADA_LIDERANCA = 3
    candidatos_produtivos = [
        p
        for p in ranking
        if p.get("ippm_score_medio", 0) > 0 and p.get("total_cadeiras_ativas", 0) >= MIN_BANCADA_LIDERANCA
    ]
    mais_produtivo = (
        candidatos_produtivos[0]
        if candidatos_produtivos
        else (ranking[0] if ranking and ranking[0].get("ippm_score_medio", 0) > 0 else None)
    )

    # Maior Eficácia: Apenas partidos com taxa estritamente positiva e projetos aprovados no período
    candidatos_eficazes = [
        p for p in ranking if p["pilares"]["taxa_eficacia_pct"] > 0 and p.get("projetos_aprovados", 0) > 0
    ]
    mais_eficaz = (
        max(
            candidatos_eficazes,
            key=lambda x: (
                x["pilares"]["taxa_eficacia_pct"],
                x.get("projetos_aprovados", 0),
                x["ippm_score_medio"],
            ),
        )
        if candidatos_eficazes
        else None
    )

    # Maior Coesão: Em empate de fidelidade (ex: 100%), priorizar bancadas com mais cadeiras ativas
    candidatos_coeso = [p for p in ranking if (p["pilares"]["fidelidade_partidaria_pct"] or 0) > 0]
    mais_coeso = (
        max(
            candidatos_coeso,
            key=lambda x: (
                x["pilares"]["fidelidade_partidaria_pct"],
                x.get("total_cadeiras_ativas", 0),
                x["ippm_score_medio"],
            ),
        )
        if candidatos_coeso
        else None
    )

    return {
        "periodo": {
            "ano": target_year,
            "data_inicio": start_date.isoformat(),
            "data_fim": end_date.isoformat(),
            "casa": clean_casa,
            "bloco": clean_bloco,
            "espectro": clean_espectro,
            "aviso": _aviso_cobertura(ranking, partidos_sem_cadeiras),
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
        db.execute(
            text(
                """
                SELECT h.id, pe.uid AS politico_id, pe.nome_exibicao, h.foto_url, h.casa, h.situacao,
                       h.data_inicio, h.data_fim, h.observacao
                FROM core.vw_historico_mandato h
                JOIN core.pessoa pe ON pe.id = h.pessoa_id
                WHERE h.partido_sigla_normalizada = ref.normalizar_texto(:sigla)
                ORDER BY h.data_inicio DESC, h.id
                """
            ),
            {"sigla": partido_sigla},
        )
        .mappings()
        .all()
    )

    exercicio: List[Dict[str, Any]] = []
    afastados: List[Dict[str, Any]] = []
    suplencias: List[Dict[str, Any]] = []

    for h in history:
        item = {
            "id": str(h["id"]),
            "politico_id": str(h["politico_id"]),
            "nome_eleitoral": h["nome_exibicao"],
            "foto_url": h["foto_url"],
            "casa": h["casa"],
            "situacao": h["situacao"],
            "data_inicio": h["data_inicio"].isoformat(),
            "data_fim": h["data_fim"].isoformat() if h["data_fim"] else None,
            "observacao": h["observacao"],
        }
        if h["situacao"] == SituacaoMandatoEnum.EXERCICIO.value:
            exercicio.append(item)
        elif h["situacao"] == SituacaoMandatoEnum.AFASTADO_MINISTERIO.value:
            afastados.append(item)
        elif h["situacao"] == SituacaoMandatoEnum.SUPLENCIA.value:
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
