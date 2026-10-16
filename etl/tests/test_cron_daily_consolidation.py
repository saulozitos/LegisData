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


def _executar_com_etapas(votacoes_efeito=None, presenca_efeito=None):
    """Roda o cron com as etapas externas simuladas; devolve (resultado, ordem das chamadas, sessão simulada)."""
    ordem = []

    def etapa(nome, retorno, efeito):
        def chamada(*args, **kwargs):
            ordem.append((nome, kwargs))
            if efeito:
                raise efeito
            return retorno

        return chamada

    with (
        patch("etl.pipelines.cron_daily_consolidation.SessionLocal") as mock_session_cls,
        patch("etl.pipelines.cron_daily_consolidation.sync_mandate_history", side_effect=etapa("ponte", 10, None)),
        patch("etl.pipelines.presenca_atualizacao.atualizar", side_effect=etapa("presenca", {}, presenca_efeito)),
        patch(
            "etl.pipelines.votacoes_atualizacao.atualizar",
            side_effect=etapa("votacoes", {"carga": {}}, votacoes_efeito),
        ),
        patch("etl.pipelines.cron_daily_consolidation.calculate_party_ippm_ranking", return_value={"ranking": [1]}),
        patch(
            "etl.pipelines.cron_daily_consolidation.build_coauthorship_network",
            return_value={"nodes": [], "edges": []},
        ),
    ):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.execute.return_value.scalar.return_value = 5
        resultado = execute_cron_pipeline()
    return resultado, ordem, mock_db


def test_votacoes_carregam_antes_da_ponte_sem_sincronizar_e_a_presenca_vem_depois():
    resultado, ordem, _ = _executar_com_etapas()

    assert [nome for nome, _ in ordem] == ["votacoes", "ponte", "presenca"]
    assert ordem[0][1] == {"sincronizar": False}  # a ponte roda uma única vez, na etapa seguinte
    assert resultado["status"] == "SUCESSO"


def test_falha_na_etapa_de_votacoes_marca_falha_mas_as_demais_rodam():
    resultado, ordem, mock_db = _executar_com_etapas(votacoes_efeito=RuntimeError("senado fora do ar"))

    assert resultado["status"] == "FALHA"
    assert "votações: senado fora do ar" in resultado["erro_mensagem"]
    assert [nome for nome, _ in ordem] == ["votacoes", "ponte", "presenca"]  # ponte e presença não foram puladas
    assert resultado["registros_atualizados"] == 10 + 5 + 1  # mandatos + autorias + partidos (+0 arestas)
    registrado = mock_db.add.call_args.args[0]
    assert registrado.status_execucao == "FALHA"
    assert "votações: senado fora do ar" in registrado.erro_mensagem


def test_falhas_de_votacoes_e_presenca_ficam_ambas_registradas():
    resultado, _, mock_db = _executar_com_etapas(votacoes_efeito=RuntimeError("a"), presenca_efeito=RuntimeError("b"))

    assert resultado["erro_mensagem"] == "votações: a; presença: b"
    assert mock_db.add.call_args.args[0].status_execucao == "FALHA"
