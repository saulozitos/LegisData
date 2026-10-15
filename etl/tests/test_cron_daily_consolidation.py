from unittest.mock import MagicMock, patch

from etl.pipelines.cron_daily_consolidation import execute_cron_pipeline


def test_execute_cron_pipeline():
    with (
        patch("etl.pipelines.cron_daily_consolidation.SessionLocal") as mock_session_cls,
        patch("etl.pipelines.cron_daily_consolidation.sync_mandate_history", return_value=10),
        patch("etl.pipelines.presenca_atualizacao.atualizar", return_value={"camara_portal": {}}),
        patch("etl.pipelines.votacoes_atualizacao.atualizar", return_value={"carga": {}}),
        patch(
            "etl.pipelines.cron_daily_consolidation.calculate_party_ippm_ranking", return_value={"ranking": [1, 2, 3]}
        ),
        patch(
            "etl.pipelines.cron_daily_consolidation.build_coauthorship_network",
            return_value={"nodes": [1], "edges": [1, 2]},
        ),
    ):

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.execute.return_value.scalar.return_value = 50

        result = execute_cron_pipeline()

        assert result["status"] == "SUCESSO"
        assert result["tempo_processamento_segundos"] >= 0
        assert result["registros_atualizados"] == 10 + 50 + 3 + 2
        assert result["erro_mensagem"] is None
        assert "data_execucao" in result
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.close.called


def test_cron_marks_failure_when_presence_update_fails_but_runs_other_stages():
    with (
        patch("etl.pipelines.cron_daily_consolidation.SessionLocal") as mock_session_cls,
        patch("etl.pipelines.cron_daily_consolidation.sync_mandate_history", return_value=10),
        patch("etl.pipelines.presenca_atualizacao.atualizar", side_effect=RuntimeError("portal fora do ar")),
        patch("etl.pipelines.votacoes_atualizacao.atualizar", return_value={"carga": {}}),
        patch("etl.pipelines.cron_daily_consolidation.calculate_party_ippm_ranking", return_value={"ranking": [1]}),
        patch(
            "etl.pipelines.cron_daily_consolidation.build_coauthorship_network",
            return_value={"nodes": [], "edges": []},
        ),
    ):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.execute.return_value.scalar.return_value = 5

        result = execute_cron_pipeline()

        assert result["status"] == "FALHA"
        assert "presença: portal fora do ar" in result["erro_mensagem"]
        assert result["registros_atualizados"] == 10 + 5 + 1  # as demais etapas rodaram
