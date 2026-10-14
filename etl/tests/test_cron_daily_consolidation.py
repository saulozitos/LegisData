from unittest.mock import MagicMock, patch

from etl.pipelines.cron_daily_consolidation import execute_cron_pipeline


def test_execute_cron_pipeline():
    with (
        patch("etl.pipelines.cron_daily_consolidation.SessionLocal") as mock_session_cls,
        patch("etl.pipelines.cron_daily_consolidation.sync_mandate_history", return_value=10),
        patch("etl.pipelines.cron_daily_consolidation.sync_proposition_authors", return_value=50),
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

        result = execute_cron_pipeline()

        assert result["status"] == "SUCESSO"
        assert result["tempo_processamento_segundos"] >= 0
        assert result["registros_atualizados"] == 10 + 50 + 3 + 2
        assert result["erro_mensagem"] is None
        assert "data_execucao" in result
        assert mock_db.add.called
        assert mock_db.commit.called
        assert mock_db.close.called
