"""Consolidação diária: ordem das etapas, isolamento de falhas e registro do resultado."""

from unittest.mock import MagicMock, patch

from etl.pipelines.cron_daily_consolidation import execute_cron_pipeline

ETAPAS_EXTERNAS = ("votacoes", "ponte", "presenca", "economia", "financas", "ranking", "grafo")


def _executar(efeitos=None, retornos=None, autorias=5):
    """
    Roda o cron com todas as etapas simuladas num só lugar. `efeitos` mapeia etapa -> exceção a levantar e `retornos`
    etapa -> retorno. Devolve (resultado, ordem, sessão simulada); a ordem inclui o IPPM e o grafo, para provar que a
    etapa 1d (finanças) vem antes das etapas 2 a 4.
    """
    efeitos, retornos, ordem = efeitos or {}, retornos or {}, []
    padrao = {
        "votacoes": {"carga": {}},
        "ponte": 10,
        "presenca": {},
        "economia": {"series": 28},
        "financas": {"carga": {}},
        "ranking": {"ranking": [1]},
        "grafo": {"nodes": [], "edges": []},
    }
    alvos = {
        "votacoes": "etl.pipelines.votacoes_atualizacao.atualizar",
        "ponte": "etl.pipelines.cron_daily_consolidation.sync_mandate_history",
        "presenca": "etl.pipelines.presenca_atualizacao.atualizar",
        "economia": "etl.pipelines.economia_atualizacao.atualizar",
        "financas": "etl.pipelines.financas_atualizacao.atualizar",
        "ranking": "etl.pipelines.cron_daily_consolidation.calculate_party_ippm_ranking",
        "grafo": "etl.pipelines.cron_daily_consolidation.build_coauthorship_network",
    }

    def etapa(nome):
        def chamada(*args, **kwargs):
            ordem.append((nome, kwargs))
            if nome in efeitos:
                raise efeitos[nome]
            return retornos.get(nome, padrao[nome])

        return chamada

    patches = [patch(alvo, side_effect=etapa(nome)) for nome, alvo in alvos.items()]
    patches.append(patch("etl.pipelines.cron_daily_consolidation.SessionLocal"))
    simulados = [p.start() for p in patches]
    try:
        mock_db = MagicMock()
        simulados[-1].return_value = mock_db
        mock_db.execute.return_value.scalar.return_value = autorias
        resultado = execute_cron_pipeline()
    finally:
        for p in patches:
            p.stop()
    return resultado, ordem, mock_db


def test_execute_cron_pipeline():
    resultado, ordem, mock_db = _executar(
        retornos={"ranking": {"ranking": [1, 2, 3]}, "grafo": {"nodes": [1], "edges": [1, 2]}}, autorias=50
    )
    assert resultado["status"] == "SUCESSO" and resultado["erro_mensagem"] is None
    assert resultado["tempo_processamento_segundos"] >= 0 and "data_execucao" in resultado
    # mandatos sincronizados + vínculos de autoria + partidos no ranking + arestas do grafo
    assert resultado["registros_atualizados"] == 10 + 50 + 3 + 2
    assert {nome for nome, _ in ordem} == set(ETAPAS_EXTERNAS)  # a 1c (séries) e a 1d (CEAP e emendas) rodaram
    assert mock_db.add.called and mock_db.commit.called and mock_db.close.called


def test_votacoes_carregam_antes_da_ponte_sem_sincronizar_e_as_financas_vem_antes_das_etapas_2_a_4():
    resultado, ordem, _ = _executar()

    # a ponte roda uma única vez (as votações não sincronizam), a presença vem depois dela e as finanças (1d) antes do IPPM
    assert [nome for nome, _ in ordem] == ["votacoes", "ponte", "presenca", "economia", "financas", "ranking", "grafo"]
    assert ordem[0][1] == {"sincronizar": False}
    assert resultado["status"] == "SUCESSO"


def test_falha_na_presenca_marca_falha_mas_roda_as_demais_etapas():
    resultado, ordem, _ = _executar(efeitos={"presenca": RuntimeError("portal fora do ar")})

    assert resultado["status"] == "FALHA"
    assert "presença: portal fora do ar" in resultado["erro_mensagem"]
    assert [nome for nome, _ in ordem] == ["votacoes", "ponte", "presenca", "economia", "financas", "ranking", "grafo"]
    assert resultado["registros_atualizados"] == 10 + 5 + 1  # as demais etapas rodaram


def test_falha_na_etapa_de_votacoes_marca_falha_mas_as_demais_rodam():
    resultado, ordem, mock_db = _executar(efeitos={"votacoes": RuntimeError("senado fora do ar")})

    assert resultado["status"] == "FALHA"
    assert "votações: senado fora do ar" in resultado["erro_mensagem"]
    assert [nome for nome, _ in ordem] == ["votacoes", "ponte", "presenca", "economia", "financas", "ranking", "grafo"]
    assert resultado["registros_atualizados"] == 10 + 5 + 1  # mandatos + autorias + partidos (+0 arestas)
    registrado = mock_db.add.call_args.args[0]
    assert registrado.status_execucao == "FALHA"
    assert "votações: senado fora do ar" in registrado.erro_mensagem


def test_falhas_de_votacoes_e_presenca_ficam_ambas_registradas():
    resultado, _, mock_db = _executar(efeitos={"votacoes": RuntimeError("a"), "presenca": RuntimeError("b")})

    assert resultado["erro_mensagem"] == "votações: a; presença: b"
    assert mock_db.add.call_args.args[0].status_execucao == "FALHA"


def test_falha_na_economia_marca_falha_mas_as_etapas_seguintes_rodam():
    resultado, ordem, _ = _executar(efeitos={"economia": RuntimeError("BCB fora do ar")}, autorias=0)

    assert resultado["status"] == "FALHA" and resultado["erro_mensagem"] == "economia: BCB fora do ar"
    assert resultado["registros_atualizados"] == 10 + 0 + 1 + 0  # mandatos + autorias + partidos + arestas
    assert [nome for nome, _ in ordem][-3:] == ["financas", "ranking", "grafo"]  # as seguintes à economia rodaram


def test_falha_na_atualizacao_de_financas_marca_falha_mas_as_demais_etapas_rodam():
    resultado, ordem, mock_db = _executar(efeitos={"financas": RuntimeError("Portal fora do ar")})

    assert resultado["status"] == "FALHA"
    assert resultado["erro_mensagem"] == "finanças: Portal fora do ar"
    assert [nome for nome, _ in ordem][-2:] == ["ranking", "grafo"]  # o IPPM e o grafo não foram pulados
    assert resultado["registros_atualizados"] == 10 + 5 + 1
    assert mock_db.add.call_args.args[0].status_execucao == "FALHA"


def test_atualizacao_de_financas_pulada_por_outra_execucao_nao_marca_falha():
    resultado, _, mock_db = _executar(retornos={"financas": {"pulada": "outra atualização das finanças em andamento"}})

    assert resultado["status"] == "SUCESSO" and resultado["erro_mensagem"] is None
    assert mock_db.add.call_args.args[0].status_execucao == "SUCESSO"
