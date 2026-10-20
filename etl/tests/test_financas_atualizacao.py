"""Atualização diária das finanças: extrai com cache, recarrega só o que foi gravado e relata a falha."""

import fcntl
from datetime import date

import pytest

import etl.pipelines.financas_atualizacao as atualizacao
from etl.pipelines import financas_loader


class Cenario:
    def __init__(self):
        self.run, self.carga = [], []
        self.resumo = {"ceap_gravado": True, "emendas_gravado": True}
        self.erro_da_carga = None


@pytest.fixture()
def simulado(monkeypatch, tmp_path):
    cenario = Cenario()

    def run(**kwargs):
        cenario.run.append(kwargs)
        return dict(cenario.resumo)

    def carregar(engine, processed_dir=None, chaves=None, ao_confirmar=None):
        cenario.carga.append((engine, tuple(chaves)))
        cenario.ao_confirmar = ao_confirmar
        if cenario.erro_da_carga:
            raise (
                cenario.erro_da_carga
                if isinstance(cenario.erro_da_carga, BaseException)
                else RuntimeError(cenario.erro_da_carga)
            )
        # o formato do `carregar` real: contagem de linhas por fonte (CEAP: despesas; emendas: emendas)
        return {
            c: ({"despesas": 1} if c == "ceap" else {"emendas": 1} if c == "emendas" else {"ok": 1}) for c in chaves
        }

    cenario.publicados = {"camara": {2025}, "senado": set()}
    monkeypatch.setattr(atualizacao.financas_loader, "anos_publicados_da_ceap", lambda engine: cenario.publicados)
    monkeypatch.setattr(atualizacao.sync_ceap_emendas, "run", run)
    monkeypatch.setattr(atualizacao.financas_loader, "carregar", carregar)
    monkeypatch.setattr(atualizacao, "LOCK", tmp_path / "lock" / ".financas.lock")
    # nenhum teste olha o diretório de estado real do deploy desta máquina
    cenario.lock_do_deploy = tmp_path / "estado" / "deploy.lock"
    monkeypatch.setattr(atualizacao, "lock_do_deploy", lambda: cenario.lock_do_deploy)
    cenario.ao_confirmar = None
    return cenario


HOJE = date(2026, 10, 19)


def test_extrai_com_o_cache_padrao_do_ano_inicial_ate_o_corrente_e_carrega_so_ceap_e_emendas(simulado):
    engine = object()
    resultado = atualizacao.atualizar(engine, hoje=HOJE)
    assert simulado.run == [
        {
            "ano_inicio": 2019,
            "ano_fim": 2026,
            "cache_dir": atualizacao.CACHE_DIR,
            "hoje": HOJE,
            "anos_publicados": {"camara": {2025}, "senado": set()},  # o que o fin já tem, não o arquivo do git
        }
    ]
    assert simulado.carga == [(engine, ("ceap", "emendas"))]  # remuneração, patrimônio... não mudam por dia
    assert resultado["carregadas"] == ["ceap", "emendas"] and resultado["carga"] == {
        "ceap": {"despesas": 1},
        "emendas": {"emendas": 1},
    }


def test_cache_padrao_fica_em_raw_fora_do_git_e_um_cache_dir_explicito_vale(simulado, tmp_path):
    assert atualizacao.CACHE_DIR.parts[-3:] == ("data", "raw", "ceap_por_ano")
    atualizacao.atualizar(object(), hoje=HOJE, cache_dir=tmp_path)
    assert simulado.run[0]["cache_dir"] == tmp_path


def test_o_ano_inicial_e_o_dos_arquivos_processados(simulado):
    atualizacao.atualizar(object(), hoje=HOJE)
    assert simulado.run[0]["ano_inicio"] == atualizacao.sync_ceap_emendas.ANO_INICIAL_ARQUIVO == 2019


def test_a_data_padrao_e_a_de_brasilia(simulado, monkeypatch):
    monkeypatch.setattr(atualizacao.sync_ceap_emendas, "hoje_no_brasil", lambda: date(2027, 3, 31))
    atualizacao.atualizar(object())
    assert simulado.run[0]["hoje"] == date(2027, 3, 31) and simulado.run[0]["ano_fim"] == 2027


@pytest.mark.parametrize(
    "falha, carregadas",
    [("ceap_gravado", ("emendas",)), ("emendas_gravado", ("ceap",))],
)
def test_fonte_que_nao_gravou_nao_e_recarregada_mas_a_outra_e_a_execucao_falha(simulado, falha, carregadas):
    """Recarregar a fonte que falhou leria o arquivo do git (mais antigo) e devolveria o `fin` ao passado."""
    simulado.resumo[falha] = False
    with pytest.raises(RuntimeError, match="fontes não gravadas") as erro:
        atualizacao.atualizar(object(), hoje=HOJE)
    assert [c for _, c in simulado.carga] == [carregadas]
    assert falha.split("_")[0] in str(erro.value)


def test_nenhuma_fonte_gravada_nao_toca_no_fin(simulado):
    simulado.resumo = {"ceap_gravado": False, "emendas_gravado": False}
    with pytest.raises(RuntimeError, match="ceap.*emendas"):
        atualizacao.atualizar(object(), hoje=HOJE)
    assert simulado.carga == []


def test_falha_da_carga_sobe_junto_com_a_das_fontes_nao_gravadas(simulado):
    simulado.resumo["emendas_gravado"] = False
    simulado.erro_da_carga = "ceap: tabela encolheria"
    with pytest.raises(RuntimeError) as erro:
        atualizacao.atualizar(object(), hoje=HOJE)
    assert "emendas" in str(erro.value) and "encolheria" in str(erro.value)


def test_falha_da_carga_sobe(simulado):
    simulado.erro_da_carga = "ceap: tabela encolheria"
    with pytest.raises(RuntimeError, match="encolheria"):
        atualizacao.atualizar(object(), hoje=HOJE)


def test_segunda_execucao_ao_mesmo_tempo_e_pulada_sem_extrair_nem_carregar(simulado):
    atualizacao.LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(atualizacao.LOCK, "w") as segurando:
        fcntl.flock(segurando, fcntl.LOCK_EX | fcntl.LOCK_NB)
        resultado = atualizacao.atualizar(object(), hoje=HOJE)
    assert "pulada" in resultado and simulado.run == [] and simulado.carga == []
    # e liberado o lock, a execução seguinte roda
    assert "pulada" not in atualizacao.atualizar(object(), hoje=HOJE)


def test_deploy_em_andamento_pula_a_atualizacao_sem_extrair_nem_carregar_e_solta_o_lock_proprio(simulado):
    """O `make daily` não pode extrair nem carregar enquanto o deploy descarta etl/data e semeia o fin."""
    simulado.lock_do_deploy.parent.mkdir(parents=True)
    with open(simulado.lock_do_deploy, "w") as deploy:
        fcntl.flock(deploy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        resultado = atualizacao.atualizar(object(), hoje=HOJE)
        assert resultado == {"pulada": "deploy em andamento"} and simulado.run == [] and simulado.carga == []
        with open(atualizacao.LOCK, "w") as proprio:  # o lock próprio não ficou preso
            fcntl.flock(proprio, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert "pulada" not in atualizacao.atualizar(object(), hoje=HOJE)  # e, solto o do deploy, a execução seguinte roda


def test_sem_diretorio_de_deploy_a_atualizacao_roda_e_nunca_cria_o_lock_do_deploy(simulado):
    assert not simulado.lock_do_deploy.exists()
    assert "pulada" not in atualizacao.atualizar(object(), hoje=HOJE)
    assert not simulado.lock_do_deploy.exists() and not simulado.lock_do_deploy.parent.exists()


def test_lock_do_deploy_que_e_link_simbolico_e_recusado_e_solta_o_lock_proprio(simulado, tmp_path):
    alvo = tmp_path / "outro"
    alvo.write_text("importante")
    simulado.lock_do_deploy.parent.mkdir(parents=True)
    simulado.lock_do_deploy.symlink_to(alvo)
    with pytest.raises(OSError):
        atualizacao.atualizar(object(), hoje=HOJE)
    assert alvo.read_text() == "importante" and simulado.run == []
    simulado.lock_do_deploy.unlink()
    assert "pulada" not in atualizacao.atualizar(object(), hoje=HOJE)


def test_o_lock_do_deploy_segue_a_convencao_do_deploy_sh(monkeypatch, tmp_path):
    monkeypatch.undo()  # a fixture `simulado` troca a função; aqui vale a de verdade
    monkeypatch.setenv("DEPLOY_STATE_DIR", str(tmp_path / "estado"))
    assert atualizacao.lock_do_deploy() == tmp_path / "estado" / "deploy.lock"
    monkeypatch.delenv("DEPLOY_STATE_DIR")
    assert atualizacao.lock_do_deploy().parts[-2:] == (".legisdata-deploy", "deploy.lock")


def test_o_lock_e_liberado_mesmo_quando_a_execucao_falha(simulado):
    simulado.resumo["ceap_gravado"] = False
    with pytest.raises(RuntimeError):
        atualizacao.atualizar(object(), hoje=HOJE)
    simulado.resumo["ceap_gravado"] = True
    assert "pulada" not in atualizacao.atualizar(object(), hoje=HOJE)


def test_main_devolve_1_quando_falha_0_quando_funciona_e_passa_o_engine_do_app(monkeypatch):
    from app.core.database import engine

    recebidos = []
    monkeypatch.setattr(atualizacao, "atualizar", lambda eng: recebidos.append(eng) or {"ok": True})
    configurados = []
    monkeypatch.setattr(atualizacao.logging, "basicConfig", lambda **kw: configurados.append(kw))
    assert atualizacao.main() == 0 and recebidos == [engine] and len(configurados) == 1

    def quebra(eng):
        raise RuntimeError("Portal fora do ar")

    monkeypatch.setattr(atualizacao, "atualizar", quebra)
    assert atualizacao.main() == 1


def test_main_trata_a_execucao_pulada_como_sucesso(monkeypatch):
    monkeypatch.setattr(atualizacao, "atualizar", lambda eng: {"pulada": "x"})
    monkeypatch.setattr(atualizacao.logging, "basicConfig", lambda **kw: None)
    assert atualizacao.main() == 0


def test_as_chaves_do_timer_existem_no_loader():
    nomes = {chave for chave, _ in financas_loader.CARGAS}
    assert set(financas_loader.CHAVES_DO_TIMER) <= nomes and set(financas_loader.CHAVES_ESTATICAS) <= nomes
    assert set(financas_loader.CHAVES_DO_TIMER) | set(financas_loader.CHAVES_ESTATICAS) == nomes  # nada fica sem dono
    assert not set(financas_loader.CHAVES_DO_TIMER) & set(financas_loader.CHAVES_ESTATICAS)


def test_o_parametro_lock_escolhe_o_arquivo_do_lock(simulado, tmp_path):
    outro = tmp_path / "outro" / ".lock"
    atualizacao.atualizar(object(), hoje=HOJE, lock=outro)
    assert outro.exists() and not atualizacao.LOCK.exists()


def test_lock_que_e_link_simbolico_e_recusado_em_vez_de_seguido(simulado, tmp_path):
    alvo = tmp_path / "alvo_de_outro_arquivo"
    alvo.write_text("importante")
    atualizacao.LOCK.parent.mkdir(parents=True, exist_ok=True)
    atualizacao.LOCK.symlink_to(alvo)
    with pytest.raises(OSError):
        atualizacao.atualizar(object(), hoje=HOJE)
    assert alvo.read_text() == "importante" and simulado.run == []


def test_o_lock_nao_trunca_o_arquivo_que_ja_existe(simulado):
    atualizacao.LOCK.parent.mkdir(parents=True, exist_ok=True)
    atualizacao.LOCK.write_text("pid 1")
    atualizacao.atualizar(object(), hoje=HOJE)
    assert atualizacao.LOCK.read_text() == "pid 1"


@pytest.mark.parametrize("resumo", [{}, {"ceap_gravado": True}, {"ceap_gravado": 1, "emendas_gravado": "sim"}])
def test_so_se_recarrega_a_fonte_que_o_resumo_afirma_ter_gravado(simulado, resumo):
    """Lista positiva: a ausência de resposta (ou um valor que não é `True`) nunca conta como gravação."""
    simulado.resumo = resumo
    with pytest.raises(RuntimeError, match="fontes não gravadas"):
        atualizacao.atualizar(object(), hoje=HOJE)
    esperado = [("ceap",)] if resumo.get("ceap_gravado") is True else []
    assert [chaves for _, chaves in simulado.carga] == esperado


def test_sem_resposta_do_banco_sobre_os_anos_carregados_a_extracao_segue_so_com_o_arquivo(
    simulado, monkeypatch, caplog
):
    from sqlalchemy.exc import OperationalError

    def quebra(engine):
        raise OperationalError("SELECT ...", {}, Exception("sem conexão"))

    monkeypatch.setattr(atualizacao.financas_loader, "anos_publicados_da_ceap", quebra)
    atualizacao.atualizar(object(), hoje=HOJE)
    assert simulado.run[0]["anos_publicados"] is None and "anos da CEAP já carregados" in caplog.text


def test_as_chaves_do_timer_sao_as_fontes_do_sync():
    assert financas_loader.CHAVES_DO_TIMER == atualizacao.sync_ceap_emendas.FONTES


def test_cada_carga_registra_na_propria_transacao_que_a_fonte_ficou_fresca(simulado):
    """O sinal para o deploy é o `ao_confirmar` da carga (dentro da transação), não um arquivo solto depois dela."""
    atualizacao.atualizar(object(), hoje=HOJE)
    assert simulado.ao_confirmar is financas_loader.registrar_carga_fresca


@pytest.mark.parametrize("erro", [ValueError("cargas desconhecidas"), "OperationalError"])
def test_erro_inesperado_da_carga_sobe_como_esta_e_o_main_devolve_1(simulado, monkeypatch, erro):
    from sqlalchemy.exc import OperationalError

    excecao = OperationalError("SELECT", {}, Exception("sem conexão")) if erro == "OperationalError" else erro
    simulado.erro_da_carga = excecao
    with pytest.raises(type(excecao)):
        atualizacao.atualizar(object(), hoje=HOJE)

    def atualiza_e_levanta(engine):
        raise excecao

    monkeypatch.setattr(atualizacao, "atualizar", atualiza_e_levanta)
    assert atualizacao.main() == 1  # a exceção inesperada vira código de saída 1, para o systemd registrar
