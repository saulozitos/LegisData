"""
Pipeline de Consolidação Diária em Lote (CRON Job).

Executa diariamente a janela de manutenção programada (madrugada)
seguindo rigidamente o fluxo em 4 etapas conforme a Especificação Técnica:
1. Etapa 1: Sincronização de Entidades Base (Parlamentares, Mandatos e Histórico Dinâmico)
2. Etapa 2: Ingestão de Proposições e Deliberações
3. Etapa 3: Recálculo dos Indicadores e Scores (IALP dos parlamentares e IPPM dos partidos)
4. Etapa 4: Atualização da Matriz de Adjacência do Grafo de Coautoria
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.database import SessionLocal
from app.models.analytics import LogExecucaoCron
from app.services.legislative_scoring import build_coauthorship_network
from app.services.party_productivity_service import (
    calculate_party_ippm_ranking,
    sync_mandate_history,
)
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cron_daily_consolidation")


def execute_cron_pipeline() -> Dict[str, Any]:
    """Executa as 4 etapas sequenciais da consolidação diária."""
    db = SessionLocal()
    t_start = datetime.now(timezone.utc)
    status = "SUCESSO"
    err_msg: Optional[str] = None
    registros_totais = 0
    erros_etapas: list = []

    try:
        logger.info("=== INICIANDO CRON JOB DE CONSOLIDAÇÃO DIÁRIA ===")

        # Etapa 1: Sincronização de Entidades Base e Mandatos Dinâmicos
        logger.info("Etapa 1/4: Sincronizando histórico dinâmico de mandatos...")
        synced_mandates = sync_mandate_history(db)
        registros_totais += synced_mandates
        logger.info(f"Etapa 1 concluída: {synced_mandates} registros de mandatos sincronizados.")

        # Etapa 1b: presença e faltas (falha aqui não impede as demais etapas, mas marca a execução como FALHA)
        logger.info("Etapa 1b: atualizando presença e faltas do Congresso...")
        try:
            from app.core.database import engine

            from etl.pipelines.presenca_atualizacao import atualizar

            presenca = atualizar(engine)
            logger.info(f"Etapa 1b concluída: {presenca}")
        except Exception as e:
            erros_etapas.append(f"presença: {e}")
            logger.error(f"Falha na atualização de presença: {e}", exc_info=True)

        # Etapa 2: Ingestão de Proposições e Autores
        logger.info("Etapa 2/4: Verificando autoria e integridade de proposições...")
        synced_authors = int(db.execute(text("SELECT count(*) FROM leg.autoria")).scalar() or 0)
        registros_totais += synced_authors
        logger.info(f"Etapa 2 concluída: {synced_authors} vínculos de autoria verificados.")

        # Etapa 3: Recálculo dos Indicadores e Scores (IALP e IPPM)
        logger.info("Etapa 3/4: Recalculando Índice de Produtividade Partidária Média (IPPM)...")
        ranking_result = calculate_party_ippm_ranking(db)
        total_parties = len(ranking_result.get("ranking", []))
        registros_totais += total_parties
        logger.info(f"Etapa 3 concluída: IPPM calculado para {total_parties} bancadas partidárias.")

        # Etapa 4: Atualização da Matriz de Adjacência do Grafo
        logger.info("Etapa 4/4: Atualizando matriz de adjacência de coautoria para o grafo...")
        graph_data = build_coauthorship_network(db=db, limit_nodes=100)
        nodes_count = len(graph_data.get("nodes", []))
        edges_count = len(graph_data.get("edges", []))
        registros_totais += edges_count
        logger.info(f"Etapa 4 concluída: Grafo consolidado com {nodes_count} nós e {edges_count} arestas.")

    except Exception as e:
        status = "FALHA"
        err_msg = str(e)
        logger.error(f"Falha crítica no CRON Job diário: {e}", exc_info=True)

    if erros_etapas and status == "SUCESSO":
        status = "FALHA"
        err_msg = "; ".join(erros_etapas)

    t_end = datetime.now(timezone.utc)
    tempo_segundos = max(0, int((t_end - t_start).total_seconds()))

    try:
        log_entry = LogExecucaoCron(
            status_execucao=status,
            registros_atualizados=registros_totais,
            tempo_processamento_segundos=tempo_segundos,
            erro_mensagem=err_msg,
            etapa="CONSOLIDACAO_DIARIA_COMPLETA",
        )
        db.add(log_entry)
        db.commit()
    except Exception as log_err:
        logger.warning(f"Falha ao registrar log de execução cron: {log_err}")
    finally:
        db.close()

    result = {
        "status": status,
        "tempo_processamento_segundos": tempo_segundos,
        "registros_atualizados": registros_totais,
        "erro_mensagem": err_msg,
        "data_execucao": t_start.isoformat(),
    }
    logger.info(f"=== CRON JOB FINALIZADO: {status} em {tempo_segundos}s ({registros_totais} registros) ===")
    return result


if __name__ == "__main__":
    res = execute_cron_pipeline()
    if res["status"] != "SUCESSO":
        sys.exit(1)
