"""Os scripts de deploy precisam ao menos ter sintaxe válida: um erro de shell só apareceria no servidor."""

import os
import random
import re
import shlex
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.parse import quote

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPTS = sorted((RAIZ / "scripts" / "deploy").glob("*.sh"))


def test_ha_scripts_de_deploy():
    assert {s.name for s in SCRIPTS} >= {"deploy.sh", "instalar.sh"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda s: s.name)
def test_sintaxe_do_script_de_deploy(script):
    resultado = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, check=False)
    assert resultado.returncode == 0, resultado.stderr


def _posicao(texto, padrao):
    achado = re.search(padrao, texto, re.MULTILINE)
    assert achado, f"deploy.sh sem o trecho esperado: {padrao}"
    return achado.start()


def test_verificar_backup_restaura_num_banco_descartavel_e_nunca_toca_no_de_producao():
    texto = (RAIZ / "scripts" / "deploy" / "verificar_backup.sh").read_text(encoding="utf-8")
    assert "createdb" in texto and "pg_restore" in texto and '-d "$BANCO"' in texto
    assert "POSTGRES_DB" not in texto and "PG_DB" not in texto  # o nome do banco de produção nem é lido
    assert re.search(r"dropdb[^\n]*\"\$BANCO\"", texto)  # só o descartável é apagado
    assert re.search(r"trap limpar EXIT", texto)  # apaga o descartável mesmo se a conferência falhar
    # o descartável é cópia da produção: fecha a conexão a outros papéis logo após criá-lo, antes de restaurar
    assert _posicao(texto, r"REVOKE CONNECT ON DATABASE") > _posicao(texto, r"createdb ")
    assert _posicao(texto, r"REVOKE CONNECT ON DATABASE") < _posicao(texto, r"pg_restore ")


def _rodar_verificar_backup(tmp_path, dump, pessoas="3", revisao="0037"):
    """Roda o script com um `docker` falso que registra as chamadas e responde às duas consultas da conferência."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    chamadas = tmp_path / "chamadas.log"
    falso = bin_ / "docker"
    falso.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >>"$CHAMADAS"\n'
        'case "$*" in\n'
        '  *alembic_version*) echo "$REVISAO" ;;\n'
        '  *core.pessoa*) echo "$PESSOAS" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    falso.chmod(0o755)
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    (raiz / ".env").write_text("POSTGRES_USER=usuario_de_teste\n", encoding="utf-8")
    ambiente = {
        "PATH": f"{bin_}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "LEGISDATA_DIR": str(raiz),
        "BACKUP_DIR": str(tmp_path / "sem_backups"),
        "CHAMADAS": str(chamadas),
        "PESSOAS": pessoas,
        "REVISAO": revisao,
    }
    argumentos = ["bash", str(RAIZ / "scripts" / "deploy" / "verificar_backup.sh")] + ([str(dump)] if dump else [])
    resultado = subprocess.run(argumentos, capture_output=True, text=True, env=ambiente, check=False)
    return resultado, chamadas.read_text(encoding="utf-8") if chamadas.exists() else ""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
def test_verificar_backup_sem_dump_sai_com_erro_sem_criar_banco(tmp_path):
    resultado, chamadas = _rodar_verificar_backup(tmp_path, None)
    assert resultado.returncode == 1 and "nenhum backup encontrado" in resultado.stdout
    assert "createdb" not in chamadas


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
def test_verificar_backup_ok_restaura_e_apaga_o_banco_descartavel(tmp_path):
    dump = tmp_path / "legisdata_x.dump"
    dump.write_bytes(b"dump")
    resultado, chamadas = _rodar_verificar_backup(tmp_path, dump)
    assert resultado.returncode == 0 and "OK: revisão 0037, 3 pessoas" in resultado.stdout
    linhas = chamadas.splitlines()
    assert any("createdb" in linha for linha in linhas) and any("pg_restore" in linha for linha in linhas)
    assert "dropdb" in linhas[-1]  # o descartável sai do ar no fim


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")
@pytest.mark.parametrize("pessoas, revisao", [("0", "0037"), ("3", "")])
def test_verificar_backup_sem_pessoas_ou_sem_revisao_falha_e_ainda_apaga_o_banco(tmp_path, pessoas, revisao):
    dump = tmp_path / "legisdata_x.dump"
    dump.write_bytes(b"dump")
    resultado, chamadas = _rodar_verificar_backup(tmp_path, dump, pessoas=pessoas, revisao=revisao)
    assert resultado.returncode == 1 and "FALHOU" in resultado.stdout
    assert "dropdb" in chamadas.splitlines()[-1]


def test_deploy_se_atualiza_antes_de_tocar_no_banco():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    reexecucao = _posicao(texto, r"^\s*_LEGISDATA_DEPLOY_REEXEC=1 _LEGISDATA_DEPLOY_ALVO=\"\$ALVO\" .*exec ")
    assert reexecucao < _posicao(texto, r"docker exec politica_postgres pg_dump ")
    assert _posicao(texto, r"bash -n ") < reexecucao  # script novo com erro de sintaxe nunca é instalado


def test_deploy_so_da_nome_definitivo_ao_dump_depois_de_terminar_bem():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    gravacao = _posicao(texto, r'pg_dump .*>"\$DUMP\.parcial"')
    promocao = _posicao(texto, r'^\s*mv "\$DUMP\.parcial" "\$DUMP"')
    assert gravacao < promocao < _posicao(texto, r"^git merge --ff-only ")


def test_umask_restrito_nao_vaza_para_o_merge():
    """O umask 077 do dump vale só no subshell: no shell principal ele deixaria o git criar arquivos 600/700."""
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    fora_do_subshell = re.sub(r"\(umask 077 && [^)]*\)", "", texto)
    assert not re.search(r"^\s*umask\b", fora_do_subshell, re.MULTILINE), "umask solto no shell principal"
    assert re.search(r"\(umask 077 && docker exec politica_postgres pg_dump ", texto)


def test_deploy_usa_o_mesmo_alvo_na_reexecucao_e_no_merge():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert re.search(r'^ALVO="\$\{_LEGISDATA_DEPLOY_ALVO:-', texto, re.MULTILINE)
    assert re.search(r'_LEGISDATA_DEPLOY_ALVO="\$ALVO" .*exec ', texto)
    assert re.search(r'^git merge --ff-only -q "\$ALVO"', texto, re.MULTILINE)


def test_senha_do_banco_vai_por_arquivo_de_ambiente_e_nao_pela_linha_de_comando():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert not re.search(r"-e (ALEMBIC_)?DATABASE_URL=", texto)
    assert re.search(r"chmod 600 \"\$ENV_BANCO\"", texto) and '--env-file "$ENV_BANCO"' in texto


DEPLOY_SH = RAIZ / "scripts" / "deploy" / "deploy.sh"
FINANCAS_SH = RAIZ / "scripts" / "deploy" / "atualizar_financas.sh"
INSTALAR_SH = RAIZ / "scripts" / "deploy" / "instalar.sh"
SYSTEMD = RAIZ / "scripts" / "systemd"
SEM_FLOCK = pytest.mark.skipif(shutil.which("flock") is None, reason="flock (util-linux) indisponível")
SEM_BASH = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("git") is None, reason="bash ou git indisponível"
)


def _texto(caminho):
    return caminho.read_text(encoding="utf-8")


def _bloco(texto, nome):
    """O trecho entre `# >>> nome` e `# <<< nome` de um script, para rodar só ele com bash de verdade."""
    achado = re.search(rf"# >>> {nome}\n(.*?)# <<< {nome}", texto, re.DOTALL)
    assert achado, f"bloco {nome} não encontrado"
    return achado.group(1)


def _ambiente_limpo(**mudancas):
    """O ambiente do processo sem variáveis do git (o teste pode rodar dentro de um hook) e sem a configuração global."""
    # sem GIT_* (o teste pode rodar dentro de um hook) nem POSTGRES_* (outro teste da suíte pode exportá-las)
    ruido = ("GIT_", "POSTGRES_", "_LEGISDATA_", "LEGISDATA_", "DEPLOY_")
    base = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(ruido) and k not in ("INTERVALO_DA_CARGA", "DRY_RUN", "ESTADO_DIR")
    }
    return {**base, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", **mudancas}


def _bash(script, cwd=None, env=None):
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env=_ambiente_limpo(**(env or {})), check=False
    )


def _git(cwd, *args):
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=_ambiente_limpo(),
    ).stdout.strip()


# ── Deploy: carga das séries e das finanças ──────────────────────────────────────────────────────────────────────────
def test_deploy_descarta_saidas_do_cron_antes_do_merge_e_carrega_tudo_pela_carga_unica():
    texto = _texto(DEPLOY_SH)
    assert _posicao(texto, r"^\s*git checkout -q -- etl/data/processed") < _posicao(texto, r"^git merge --ff-only ")
    carga = texto[_posicao(texto, r"um_comando python -c ") :]
    assert re.search(
        r"^from etl\.pipelines\.carga_economica import TOLERADAS_NO_DEPLOY, carregar_tudo, falhas_toleradas, plano_do_modo",
        carga,
        re.MULTILINE,
    )
    assert _posicao(texto, r"alembic upgrade head") < _posicao(texto, r"um_comando python -c ")
    assert _posicao(texto, r"um_comando python -c ") < _posicao(texto, r"^docker compose up ")


def test_deploy_repassa_a_liberacao_de_encolhimento_vazia_por_padrao_e_tolera_so_as_financas():
    texto = _texto(DEPLOY_SH)
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :].split("\n}\n")[0]
    # a variável é repassada DENTRO de `um_comando` (não solta no script) e vazia quando o operador não a define
    assert re.search(r"-e LEGISDATA_ACEITAR_ENCOLHIMENTO=\"\$\{LEGISDATA_ACEITAR_ENCOLHIMENTO:-\}\"", corpo)
    # só as finanças são toleradas (as duas chaves delas), com qualquer espaçamento ou aspas
    assert re.search(r"toleradas\s*=\s*TOLERADAS_NO_DEPLOY if ", texto)  # a lista vive em carga_economica (um mapa só)
    from etl.pipelines.carga_economica import TOLERADAS_NO_DEPLOY

    assert TOLERADAS_NO_DEPLOY == ("financas",)


def test_deploy_so_tolera_falha_das_financas_quando_fin_ja_tem_dados():
    """No primeiro deploy `fin` nasce vazio: tolerar a falha subiria a API sem dados e com saída 0."""
    texto = _texto(DEPLOY_SH)
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :].split("\n}\n")[0]
    assert re.search(r"-e LEGISDATA_FIN_TEM_ALGUM_DADO=\"\$\{LEGISDATA_FIN_TEM_ALGUM_DADO:-\}\"", corpo)
    # o MODO vem de duas perguntas por fonte (a CEAP exige as 3 tabelas dela, as emendas a delas); a TOLERÂNCIA vale se
    # QUALQUER tabela tem dados (com a API servindo o que existe, abortar o deploy seria pior)
    from etl.pipelines.carga_economica import SQL_FIN_TEM_ALGUM_DADO, SQL_FIN_TEM_CEAP, SQL_FIN_TEM_EMENDAS

    for variavel, consulta in (
        ("TEM_CEAP", SQL_FIN_TEM_CEAP),
        ("TEM_EMENDAS", SQL_FIN_TEM_EMENDAS),
        ("LEGISDATA_FIN_TEM_ALGUM_DADO", SQL_FIN_TEM_ALGUM_DADO),
    ):
        pergunta = (
            f'{variavel}="$(docker exec politica_postgres psql -U "$PG_USER" -d "$PG_DB" -tAc "select {consulta}")"'
        )
        assert pergunta in texto, variavel
        assert _posicao(texto, re.escape(pergunta)) < _posicao(texto, r"um_comando python -c ")
    carga = texto[_posicao(texto, r"um_comando python -c ") :]
    assert re.search(r"os\.environ\.get\('LEGISDATA_FIN_TEM_ALGUM_DADO'\) == 't' else \(\)", carga)
    assert "carregar_tudo(engine, toleradas=toleradas, **plano)" in carga
    # sem decisão, não toca no fin
    assert (
        "plano_do_modo(os.environ.get('LEGISDATA_FIN_MODO', 'nenhuma'), ao_confirmar=registrar_carga_do_git)" in carga
    )


def _python_da_carga():
    """O programa que o deploy passa a `python -c` (entre aspas duplas no bash, sem expansões)."""
    texto = _texto(DEPLOY_SH)
    achado = re.search(r'um_comando python -c "\n(.*?)\n"\)"', texto, re.DOTALL)
    assert achado, "programa da carga não encontrado no deploy.sh"
    assert "$" not in achado.group(1) and "`" not in achado.group(1)  # o bash não pode expandir nada dentro dele
    return achado.group(1)


def test_o_programa_da_carga_compila_e_roda_com_o_gancho_do_git_e_o_modo_do_ambiente(monkeypatch, capsys):
    import sys
    import types

    from etl.pipelines import carga_economica, financas_loader

    codigo = _python_da_carga()
    compile(codigo, "deploy.sh:carga", "exec")
    motor = object()
    modulo_db = types.ModuleType("app.core.database")
    modulo_db.engine = motor
    monkeypatch.setitem(sys.modules, "app.core.database", modulo_db)
    recebido = {}

    def falso(engine, **kw):
        recebido.update(kw, engine=engine)
        return {"financas": {"erro": "x"}, "pnad": 1}

    monkeypatch.setattr(carga_economica, "carregar_tudo", falso)
    posprocessados = []
    monkeypatch.setattr("etl.utils.manutencao.posprocessar_carga", lambda engine: posprocessados.append(engine))
    monkeypatch.setenv("LEGISDATA_FIN_MODO", "sem_ceap")
    monkeypatch.setenv("LEGISDATA_FIN_TEM_ALGUM_DADO", "t")
    exec(compile(codigo, "deploy.sh:carga", "exec"), {})
    saida = capsys.readouterr().out
    assert recebido["engine"] is motor and recebido["toleradas"] == carga_economica.TOLERADAS_NO_DEPLOY
    assert recebido["chaves"] == carga_economica.chaves_do_modo("sem_ceap")
    opcoes = recebido["opcoes"]["financas"]
    assert opcoes["chaves"] == carga_economica.FINANCAS_POR_MODO["sem_ceap"]
    assert opcoes["ao_confirmar"] is financas_loader.registrar_carga_do_git
    assert "FALHA_TOLERADA financas" in saida
    # a carga religa os derivados (presidência atualiza core.mandato): o deploy os refaz, o primeiro leitor não paga
    assert posprocessados == [motor]

    monkeypatch.delenv("LEGISDATA_FIN_MODO")
    monkeypatch.delenv("LEGISDATA_FIN_TEM_ALGUM_DADO")
    exec(compile(codigo, "deploy.sh:carga", "exec"), {})
    assert recebido["toleradas"] == () and "financas" not in recebido["chaves"]  # sem decisão: modo "nenhuma"


def test_modo_das_financas_chega_a_carga_pelo_um_comando():
    texto = _texto(DEPLOY_SH)
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :].split("\n}\n")[0]
    assert 'LEGISDATA_FIN_MODO="${LEGISDATA_FIN_MODO:-nenhuma}"' in corpo  # sem decisão, o padrão não destrói nada
    assert (
        'read -r LEGISDATA_FIN_MODO LEGISDATA_FIN_REFRESCAR < <(decidir_financas "$ATUAL" "$ALVO" "$TEM_CEAP" "$TEM_EMENDAS" "$PENDENCIAS" "$CEAP_DO_TIMER" "$EMENDAS_DO_TIMER")'
        in texto
    )


def test_rollback_do_deploy_sobe_a_tag_anterior_com_o_compose_do_commit_anterior():
    texto = _texto(DEPLOY_SH)
    guardado = _posicao(texto, r'^COMMIT_ANTERIOR="\$\(git rev-parse HEAD\)"')
    assert guardado < _posicao(texto, r"^git merge --ff-only ")
    rollback = texto[_posicao(texto, r'if \[\[ "\$estado" != "healthy" \]\]') :]
    assert re.search(r'git show "\$COMMIT_ANTERIOR:docker-compose\.yml"', rollback)
    assert re.search(r'IMAGE_TAG="\$ANTERIOR" docker compose --project-directory "\$RAIZ" -f ', rollback)
    assert rollback.count("com o compose do commit anterior") == 1  # o comentário não pode se repetir


@SEM_BASH
@SEM_FLOCK
@pytest.mark.parametrize(
    "dry_run, reexec, esperado",
    [
        (0, "", "sai 0 com o lock ocupado"),
        (1, "", "segue"),  # o dry-run não disputa o lock: com a atualização rodando, sairia "ok" sem testar nada
        (0, "1", "segue"),  # numa reexecução o lock já foi tomado pelo processo anterior (descritor 9 herdado)
    ],
)
def test_trava_do_deploy_com_o_lock_ocupado(tmp_path, dry_run, reexec, esperado):
    import subprocess as sp

    estado = tmp_path / "estado"
    estado.mkdir()
    segurando = sp.Popen(
        ["bash", "-c", f'exec 9>"{estado}/deploy.lock"; flock -n 9 && echo preso && sleep 30'],
        stdout=sp.PIPE,
        text=True,
    )
    try:
        assert segurando.stdout.readline().strip() == "preso"
        script = (
            f'ESTADO_DIR="{estado}"\nDRY_RUN={dry_run}\nlog() {{ echo "LOG: $*"; }}\n'
            + _bloco(_texto(DEPLOY_SH), "trava_do_deploy")
            + "\necho SEGUIU"
        )
        resposta = _bash(script, env={"_LEGISDATA_DEPLOY_REEXEC": reexec} if reexec else {})
        if esperado == "segue":
            assert "SEGUIU" in resposta.stdout and "outra execução" not in resposta.stdout
        else:
            assert resposta.returncode == 0 and "outra execução em andamento" in resposta.stdout
            assert "SEGUIU" not in resposta.stdout
    finally:
        segurando.kill()
        segurando.wait()


@SEM_BASH
@pytest.mark.parametrize("estado, sai", [("", False), ("PADRAO", False), ("/outro/lugar", True)])
def test_o_instalador_recusa_um_deploy_state_dir_que_as_units_nao_usam(tmp_path, estado, sai):
    script = (
        f'HOME="{tmp_path}"\n'
        + _bloco(_texto(RAIZ / "scripts" / "deploy" / "instalar.sh"), "estado_fixo")
        + '\necho SEGUIU "$DEST"'
    )
    env = {"DEPLOY_STATE_DIR": estado.replace("PADRAO", f"{tmp_path}/.legisdata-deploy")} if estado else {}
    resposta = _bash(script, env=env)
    if sai:
        assert resposta.returncode == 1 and "SEGUIU" not in resposta.stdout and "não é suportado" in resposta.stdout
    else:
        assert resposta.returncode == 0 and f"SEGUIU {tmp_path}/.legisdata-deploy" in resposta.stdout


# ── decidir_financas: o que o deploy faz com CEAP e emendas (bash de verdade, repositório git de verdade) ───────────────
@pytest.fixture()
def repo_de_decisao(tmp_path):
    repo = tmp_path / "repo"
    arquivos = {
        "etl/data/processed/despesas_ceap_2019_2026.json": "[]",
        "etl/data/processed/emendas_parlamentares_2019_2026.json": "[]",
        "etl/data/processed/remuneracao_parlamentares.json": "{}",
        "etl/data/processed/declaracoes_patrimonio.json": "[]",
        "etl/data/processed/tse_doacoes_campanha.json": "[]",
        "etl/data/processed/certidoes_tse.json": "[]",
        "etl/data/processed/processos_judiciais.json": "[]",
        "etl/pipelines/financas_loader.py": "a",
        "etl/pipelines/loader_helpers.py": "a",
        "etl/pipelines/pessoa_resolver.py": "a",
        "etl/pipelines/carga_economica.py": "a",
        "etl/config.py": "a",
        "etl/pipelines/sync_ceap_emendas.py": "a",
        "etl/pipelines/financas_atualizacao.py": "a",
        "etl/extractors/emendas_extractor.py": "a",
        "etl/utils/http_client.py": "a",
        "backend/alembic/versions/0031.py": "a",
        "docs/leia-me.md": "a",
    }
    for caminho, conteudo in arquivos.items():
        (repo / caminho).parent.mkdir(parents=True, exist_ok=True)
        (repo / caminho).write_text(conteudo)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _decidir(
    repo,
    mudanca,
    tem_dados=None,
    atual="HEAD~1",
    pendencias="",
    ceap_timer="t",
    emendas_timer="t",
    tem_ceap="t",
    tem_emendas="t",
):
    """Faz um commit com `mudanca` ({caminho: conteúdo}) e devolve o que `decidir_financas` responde para ele."""
    if tem_dados is not None:  # atalho dos testes antigos: as duas fontes têm (ou não) dado
        tem_ceap = tem_emendas = tem_dados
    for caminho, conteudo in mudanca.items():
        (repo / caminho).parent.mkdir(parents=True, exist_ok=True)
        (repo / caminho).write_text(conteudo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "mudança")
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    anterior = _git(repo, "rev-parse", atual) if atual else ""
    resposta = _bash(
        f'{funcao}\ndecidir_financas "{anterior}" "$(git rev-parse HEAD)" "{tem_ceap}" "{tem_emendas}" "{pendencias}" "{ceap_timer}" "{emendas_timer}"',
        cwd=repo,
    )
    assert resposta.returncode == 0, resposta.stderr
    return resposta.stdout.strip()


@SEM_BASH
@pytest.mark.parametrize(
    "mudanca, esperado",
    [
        ({"docs/leia-me.md": "b"}, "nenhuma 0"),  # nada que a carga leia
        ({}, "nenhuma 0"),  # commit vazio
        # o arquivo de CEAP/emendas do git NUNCA dispara recarga quando o fin tem dados: o timer é a fonte
        ({"etl/data/processed/despesas_ceap_2019_2026.json": '[{"x":1}]'}, "nenhuma 0"),
        ({"etl/data/processed/emendas_parlamentares_2019_2026.json": '[{"x":1}]'}, "nenhuma 0"),
        ({"etl/data/processed/remuneracao_parlamentares.json": '{"x":1}'}, "estaticas 0"),
        ({"etl/data/processed/declaracoes_patrimonio.json": '[{"x":1}]'}, "estaticas 0"),
        ({"etl/data/processed/tse_doacoes_campanha.json": '[{"x":1}]'}, "estaticas 0"),
        ({"etl/data/processed/certidoes_tse.json": '[{"x":1}]'}, "estaticas 0"),
        ({"etl/data/processed/processos_judiciais.json": '[{"x":1}]'}, "estaticas 0"),
        # a curadoria é só a entrada do extrator (manual): mexer nela não recarrega o fin; o arquivo gerado é que vale
        ({"etl/data/processed/processos_curados.json": '[{"x":1}]'}, "nenhuma 0"),
        ({"etl/pipelines/financas_loader.py": "b"}, "estaticas 1"),  # código da carga: estáticas e atualização diária
        ({"etl/pipelines/loader_helpers.py": "b"}, "estaticas 1"),
        ({"etl/pipelines/pessoa_resolver.py": "b"}, "estaticas 1"),
        ({"etl/pipelines/carga_economica.py": "b"}, "estaticas 0"),  # só orquestra as estáticas
        (
            {"etl/pipelines/sync_ceap_emendas.py": "b"},
            "nenhuma 1",
        ),  # só a extração: roda a atualização, nada de estáticas
        ({"etl/pipelines/financas_atualizacao.py": "b"}, "nenhuma 1"),
        ({"etl/extractors/emendas_extractor.py": "b"}, "nenhuma 1"),
        ({"etl/config.py": "b"}, "estaticas 1"),  # tetos e diretórios que o extrator e a carga importam
        ({"etl/utils/http_client.py": "b"}, "estaticas 1"),  # utilitário compartilhado
        ({"etl/utils/names.py": "novo"}, "estaticas 1"),  # arquivo novo em etl/utils
        ({"backend/alembic/versions/0032.py": "novo"}, "estaticas 1"),  # migração de qualquer schema
    ],
)
def test_decisao_das_financas_por_arquivo_alterado_no_commit(repo_de_decisao, mudanca, esperado):
    assert _decidir(repo_de_decisao, mudanca) == esperado


@SEM_BASH
@pytest.mark.parametrize(
    "pendencias, esperado",
    [("carga", "estaticas 0"), ("refrescar", "nenhuma 1"), ("carga\nrefrescar", "estaticas 1"), ("", "nenhuma 0")],
)
def test_pendencias_de_um_deploy_anterior_valem_mesmo_sem_mudanca_no_commit(repo_de_decisao, pendencias, esperado):
    assert _decidir(repo_de_decisao, {"docs/leia-me.md": "b"}, pendencias=pendencias) == esperado


@SEM_BASH
@pytest.mark.parametrize(
    "mudanca, pendencias, tem_dados, esperado",
    [
        ({"etl/pipelines/financas_loader.py": "b"}, "carga", "t", "estaticas 1"),  # pendência + código mudou
        ({"docs/leia-me.md": "b"}, "carga", "f", "completa 1"),  # fin sem dados: a semeadura vale mais que a pendência
        ({"docs/leia-me.md": "b"}, "cargas\nrefrescando", "t", "nenhuma 0"),  # só linha inteira conta, não substring
        (
            {"scripts/deploy/atualizar_financas.sh": "novo"},
            "",
            "t",
            "nenhuma 1",
        ),  # o script do timer pede a atualização
        ({"scripts/systemd/legisdata-financas.timer": "novo"}, "", "t", "nenhuma 1"),
    ],
)
def test_pendencias_e_o_script_do_timer_na_decisao(repo_de_decisao, mudanca, pendencias, tem_dados, esperado):
    assert _decidir(repo_de_decisao, mudanca, tem_dados=tem_dados, pendencias=pendencias) == esperado


@SEM_BASH
@pytest.mark.parametrize(
    "ceap_timer, emendas_timer, esperado",
    [
        ("f", "f", "completa 1"),  # o timer nunca carregou nada: o git é o dado mais novo, semeia tudo
        ("f", "t", "sem_emendas 1"),  # só as emendas são dele: semeia a CEAP sem reescrever as emendas (uid)
        ("t", "f", "sem_ceap 1"),
        ("t", "t", "nenhuma 0"),
    ],
)
def test_semeadura_por_fonte_conforme_o_que_o_timer_ja_carregou(repo_de_decisao, ceap_timer, emendas_timer, esperado):
    mudanca = {"docs/leia-me.md": "b"}
    assert _decidir(repo_de_decisao, mudanca, ceap_timer=ceap_timer, emendas_timer=emendas_timer) == esperado


@SEM_BASH
def test_fin_sem_dados_vence_qualquer_marcador_e_sem_marcadores_com_dados_semeia_tudo(repo_de_decisao):
    assert (
        _decidir(repo_de_decisao, {"docs/leia-me.md": "b"}, tem_dados="f", ceap_timer="t", emendas_timer="t")
        == "completa 1"
    )
    assert (
        _decidir(repo_de_decisao, {"docs/leia-me.md": "c"}, tem_dados="t", ceap_timer="f", emendas_timer="f")
        == "completa 1"
    )


def test_a_consulta_das_fontes_do_timer_do_deploy_e_a_do_python():
    from etl.pipelines.semeadura_das_financas import SQL_FONTES_DO_TIMER

    assert f'-tAc "{SQL_FONTES_DO_TIMER}"' in _texto(DEPLOY_SH)


@SEM_BASH
@pytest.mark.parametrize(
    "resposta_do_banco, esperado",
    [("", "f f"), ("ceap", "t f"), ("emendas", "f t"), ("ceap emendas", "t t"), ("emendas_velhas ceapx", "f f")],
)
def test_o_deploy_deriva_as_fontes_do_timer_da_resposta_do_banco(tmp_path, resposta_do_banco, esperado):
    """A resposta do `psql` (nomes separados por espaço) vira as duas flags; só a palavra inteira conta."""
    falsos = tmp_path / "bin"
    falsos.mkdir()
    argumentos = tmp_path / "argumentos"
    (falsos / "docker").write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" >{shlex.quote(str(argumentos))}\necho '{resposta_do_banco}'\n"
    )
    (falsos / "docker").chmod(0o755)
    script = (
        "PG_USER=u PG_DB=d\n"
        + _bloco(_texto(DEPLOY_SH), "fontes_do_timer")
        + '\necho "$CEAP_DO_TIMER $EMENDAS_DO_TIMER"'
    )
    resposta = _bash(script, env={"PATH": f"{falsos}:{os.environ['PATH']}"})
    assert resposta.returncode == 0, resposta.stderr
    assert resposta.stdout.strip() == esperado
    from etl.pipelines.semeadura_das_financas import SQL_FONTES_DO_TIMER

    recebidos = argumentos.read_text(encoding="utf-8").splitlines()
    assert recebidos == ["exec", "politica_postgres", "psql", "-U", "u", "-d", "d", "-tAc", SQL_FONTES_DO_TIMER]


@SEM_BASH
@pytest.mark.parametrize("repeticao, refrescar, esperado", [(1, "1", "0"), (0, "1", "1"), (1, "0", "0"), (0, "0", "0")])
def test_repetir_a_carga_nao_repete_o_pedido_de_atualizacao(repeticao, refrescar, esperado):
    script = f"REPETICAO={repeticao}\nLEGISDATA_FIN_REFRESCAR={refrescar}\n{_bloco(_texto(DEPLOY_SH), 'pos_decisao')}\necho $LEGISDATA_FIN_REFRESCAR"
    assert _bash(script).stdout.strip() == esperado


def _decidir_em_lote(repo, combinacoes):
    """Roda `decidir_financas` para várias entradas num único bash (um commit só): devolve as saídas, uma por entrada."""
    (repo / "etl" / "pipelines" / "financas_loader.py").write_text("b")  # o commit mexe em código da carga
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "muda a carga")
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    linhas = "\n".join(
        f'decidir_financas "{atual}" HEAD "{ceap}" "{emendas}" "{pend}" "{ceap_t}" "{emendas_t}"'
        for atual, ceap, emendas, pend, ceap_t, emendas_t in combinacoes
    )
    resposta = _bash(f"{funcao}\n{linhas}", cwd=repo)
    assert resposta.returncode == 0, resposta.stderr
    saidas = resposta.stdout.strip().splitlines()
    assert len(saidas) == len(combinacoes), (len(saidas), len(combinacoes))  # nenhuma entrada some sem falhar
    return saidas


@SEM_BASH
def test_a_decisao_do_deploy_e_a_tabela_de_semeadura_do_python_nas_16_combinacoes(repo_de_decisao):
    """O bash e o Python (`modo_de_semeadura`) têm a mesma tabela: para toda combinação, o mesmo modo."""
    import itertools

    from etl.pipelines.carga_economica import modo_de_semeadura

    bools = (True, False)
    entradas = list(itertools.product(bools, repeat=4))
    saidas = _decidir_em_lote(
        repo_de_decisao,
        [
            ("HEAD~1", "t" if a else "f", "t" if b else "f", "", "t" if c else "f", "t" if d else "f")
            for a, b, c, d in entradas
        ],
    )
    assert len(saidas) == len(entradas) == 16  # uma saída sumida não pode passar calada pelo zip
    for (a, b, c, d), saida in zip(entradas, saidas):
        esperado = modo_de_semeadura(a, b, c, d) or "estaticas"  # nada a semear + código mudou => as estáticas
        assert saida.split()[0] == esperado, ((a, b, c, d), saida)


@SEM_BASH
def test_todo_modo_que_a_decisao_pode_emitir_existe_no_mapa_de_modos(repo_de_decisao):
    """Um modo digitado errado no bash só apareceria em produção: percorre entradas, commits anteriores e pendências."""
    from etl.pipelines.carga_economica import FINANCAS_POR_MODO

    atuais = ("HEAD~1", "", "0" * 40)
    pendencias = ("", "carga", "refrescar", "carga\nrefrescar")
    flags = ("t", "f")
    combinacoes = [
        (atual, ceap, emendas, pend, ct, et)
        for atual in atuais
        for pend in pendencias
        for ceap in flags
        for emendas in flags
        for ct in flags
        for et in flags
    ]
    emitidos = {saida.split()[0] for saida in _decidir_em_lote(repo_de_decisao, combinacoes)}
    assert emitidos <= set(FINANCAS_POR_MODO)  # nenhum modo fora do mapa
    assert emitidos == {"completa", "sem_emendas", "sem_ceap", "estaticas"}  # 'nenhuma' só sem mudança nem pendência


@SEM_BASH
def test_fin_sem_dados_semeia_tudo_do_git_e_pede_a_atualizacao_qualquer_que_seja_o_commit(repo_de_decisao):
    assert _decidir(repo_de_decisao, {"docs/leia-me.md": "b"}, tem_dados="f") == "completa 1"
    assert _decidir(repo_de_decisao, {}, tem_dados="") == "completa 1"


@SEM_BASH
def test_commit_anterior_desconhecido_ou_ausente_recarrega_o_que_pode_e_pede_a_atualizacao(repo_de_decisao):
    assert _decidir(repo_de_decisao, {"docs/leia-me.md": "b"}, atual=None) == "estaticas 1"  # ATUAL vazio
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    inexistente = _bash(f'{funcao}\ndecidir_financas "{"0" * 40}" HEAD t t', cwd=repo_de_decisao)
    assert inexistente.stdout.strip() == "estaticas 1" and inexistente.returncode == 0


@SEM_BASH
def test_toda_entrada_da_decisao_existe_no_repositorio():
    """Um arquivo renomeado deixaria `git diff -- caminho` sempre quieto e o deploy pularia a recarga para sempre."""
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    caminhos = re.findall(r"\b((?:etl|backend)/[\w./-]+)", funcao)
    assert len(caminhos) >= 15
    for caminho in caminhos:
        assert (RAIZ / caminho).exists(), caminho


def _modulos_importados(arquivo, vistos):
    """Os arquivos `etl/**` que `arquivo` importa, direta ou indiretamente (só importações estáticas, por AST)."""
    import ast

    if arquivo in vistos:
        return
    vistos.add(arquivo)
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        nomes = []
        if isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes = [no.module] + [f"{no.module}.{a.name}" for a in no.names]
        elif isinstance(no, ast.Import):
            nomes = [a.name for a in no.names]
        for nome in nomes:
            if nome.split(".")[0] != "etl":
                continue
            caminho = RAIZ.joinpath(*nome.split("."))
            if caminho.with_suffix(".py").is_file():
                _modulos_importados(caminho.with_suffix(".py"), vistos)


def test_tudo_que_o_extrator_e_a_carga_importam_esta_nas_listas_da_decisao():
    """Um módulo importado e fora das listas mudaria sem o deploy recarregar nem pedir a atualização (visto com etl/config.py)."""
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    listas = {}
    for nome in ("estaticas", "do_timer"):
        corpo = re.search(rf"local {nome}=\((.*?)\n  \)", funcao, re.DOTALL).group(1)
        listas[nome] = re.findall(r"((?:etl|backend)/[\w./-]+)", corpo)
    raizes = {
        "estaticas": ["etl/pipelines/financas_loader.py", "etl/pipelines/carga_economica.py"],
        "do_timer": ["etl/pipelines/sync_ceap_emendas.py", "etl/pipelines/financas_atualizacao.py"],
    }
    for nome, entradas in raizes.items():
        vistos = set()
        for entrada in entradas:
            _modulos_importados(RAIZ / entrada, vistos)
        for arquivo in vistos:
            relativo = arquivo.relative_to(RAIZ).as_posix()
            assert "from ." not in arquivo.read_text(
                encoding="utf-8"
            ), f"{relativo}: import relativo escaparia da varredura"
            if relativo.endswith("__init__.py"):
                continue
            coberto = any(relativo == item or relativo.startswith(item.rstrip("/") + "/") for item in listas[nome])
            assert coberto, f"{relativo} é importado por {entradas} e não está na lista '{nome}' de decidir_financas"


@SEM_BASH
def test_marcador_de_pendencias_marca_sem_duplicar_e_limpa_so_o_pedido(tmp_path):
    bloco = _bloco(_texto(DEPLOY_SH), "pendencias")
    script = (
        f'ESTADO_DIR="{tmp_path}"\n{bloco}\n'
        'pendente_marca carga; pendente_marca carga; pendente_marca refrescar; cat "$PENDENTE"; echo ---;'
        'pendente_limpa carga; cat "$PENDENTE"; echo ---; pendente_limpa refrescar; '
        'test ! -e "$PENDENTE" && echo sumiu; pendente_tem carga || echo sem-carga; pendente_limpa carga'
    )
    resposta = _bash(script)
    assert resposta.returncode == 0, resposta.stderr
    assert resposta.stdout.split() == ["carga", "refrescar", "---", "refrescar", "---", "sumiu", "sem-carga"]


# ── url_encode e o arquivo de ambiente do banco (bash de verdade) ────────────────────────────────────────────────────
@SEM_BASH
def test_url_encode_do_deploy_e_o_mesmo_de_urllib_para_qualquer_texto():
    funcao = _bloco(_texto(DEPLOY_SH), "url_encode")
    sorteio = random.Random(7)
    alfabeto = "abcXYZ019 @:/#%?&=+;,!*'()[]{}$\\\"<>|^`~._-çãé😀ñ\t"
    entradas = ["", "p@ss:w/rd#1", " espaço ", "100%", "ç", "😀"] + [
        "".join(sorteio.choice(alfabeto) for _ in range(sorteio.randint(1, 24))) for _ in range(300)
    ]
    resposta = subprocess.run(
        ["bash", "-c", f'{funcao}\nwhile IFS= read -r l; do url_encode "$l"; echo; done'],
        input="\n".join(entradas) + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert resposta.stdout.split("\n")[:-1] == [quote(e, safe="") for e in entradas]


@SEM_BASH
def test_o_arquivo_de_ambiente_do_deploy_codifica_a_senha_tem_modo_600_e_some_ao_sair(tmp_path):
    texto = _texto(DEPLOY_SH)
    script = (
        _bloco(texto, "url_encode")
        + 'log() { echo "$*" >&2; }\nPG_USER=usuario PG_DB=banco\n'
        + _bloco(texto, "env_banco")
        + 'cat "$ENV_BANCO"; stat -c %a "$ENV_BANCO" 2>/dev/null || stat -f %Lp "$ENV_BANCO"; echo "$ENV_BANCO"'
    )
    resposta = _bash(script, env={"POSTGRES_PASSWORD": "p@ss:w/rd#1 %"})
    linhas = resposta.stdout.split("\n")
    assert resposta.returncode == 0, resposta.stderr
    url = "postgresql+psycopg2://usuario:p%40ss%3Aw%2Frd%231%20%25@postgres:5432/banco"
    assert f"DATABASE_URL={url}" in linhas and f"ALEMBIC_DATABASE_URL={url}" in linhas
    assert "POSTGRES_PASSWORD=p@ss:w/rd#1 %" in linhas  # a senha crua só vai no arquivo, nunca na linha de comando
    assert linhas[-3] == "600" and not Path(linhas[-2]).exists()  # trap EXIT removeu o arquivo


@SEM_BASH
@pytest.mark.parametrize("senha", ["a\nb", "a\rb", "abc\n"])
def test_senha_com_quebra_de_linha_aborta_o_deploy_antes_de_gravar_o_arquivo_de_ambiente(senha):
    texto = _texto(DEPLOY_SH)
    script = (
        _bloco(texto, "url_encode")
        + 'log() { echo "$*" >&2; }\nPG_USER=u PG_DB=d\n'
        + _bloco(texto, "env_banco")
        + "echo seguiu"
    )
    resposta = _bash(script, env={"POSTGRES_PASSWORD": senha})
    assert resposta.returncode == 1 and "quebra de linha" in resposta.stderr and "seguiu" not in resposta.stdout


# ── Atualização diária das finanças (timer de usuário) ─────────────────────────────────────────────────────────────────
def test_atualizacao_diaria_usa_o_mesmo_lock_do_deploy_e_espera():
    financas, deploy = _texto(FINANCAS_SH), _texto(DEPLOY_SH)
    linha_do_lock = r'^\s*exec 9>"\$\{LEGISDATA_DEPLOY_LOCK:-\$ESTADO_DIR/deploy\.lock\}"'
    assert re.search(linha_do_lock, financas, re.MULTILINE) and re.search(linha_do_lock, deploy, re.MULTILINE)
    assert re.search(r"^flock -w \d+ 9 \|\|", financas, re.MULTILINE)  # espera o deploy terminar
    assert re.search(r"flock -n 9 \|\| \{ log \"outra execução em andamento\"; exit 0; \}", deploy)  # o deploy só pula
    assert re.search(r"financas_atualizacao 9>&-\s*$", financas, re.MULTILINE)  # o contêiner não herda o lock


def test_contineres_do_deploy_e_das_financas_tem_a_mesma_contencao():
    """Sem capacidades, sem privilégios novos, e o .env (outros segredos) escondido do contêiner que só precisa do banco."""
    for script in (DEPLOY_SH, FINANCAS_SH):
        texto = _texto(script)
        assert "--cap-drop ALL --security-opt no-new-privileges --pids-limit" in texto, script.name
        assert "-v /dev/null:/repo/.env:ro" in texto, script.name
        assert '-v "$RAIZ:/repo:ro"' in texto, script.name


def test_so_etl_data_e_gravavel_no_conteiner_das_financas():
    texto = _texto(FINANCAS_SH)
    montagens = re.findall(r'-v "([^"]+)"', texto)
    assert sorted(montagens) == sorted(["$RAIZ:/repo:ro", "$RAIZ/etl/data:/repo/etl/data"])
    assert '--user "$(id -u):$(id -g)"' in texto and re.search(r"--memory \d+g", texto)
    assert "python -m etl.pipelines.financas_atualizacao" in texto


def _ambiente_do_script_das_financas(tmp_path, **mudancas):
    """Roda atualizar_financas.sh com docker, flock e git falsos que registram o que receberam."""
    falsos = tmp_path / "bin"
    registro = tmp_path / "registro"
    raiz = tmp_path / "projeto"
    estado = tmp_path / "estado"
    for pasta in (falsos, registro, raiz / "etl" / "data"):
        pasta.mkdir(parents=True, exist_ok=True)
    git_real = shutil.which("git")
    scripts = {
        "docker": r"""#!/usr/bin/env bash
printf '%s\x1f' "$@" >>"$REGISTRO/docker.log"; printf '\n' >>"$REGISTRO/docker.log"
case "$1" in
  inspect) echo "${FAKE_IMAGEM}" ;;
  run)
    args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do
      if [[ "${args[i]}" == "--env-file" ]]; then
        cp "${args[i+1]}" "$REGISTRO/envfile"; { stat -c %a "${args[i+1]}" 2>/dev/null || stat -f %Lp "${args[i+1]}"; } >"$REGISTRO/envfile_modo"; echo "${args[i+1]}" >"$REGISTRO/envfile_caminho"
      fi
    done
    exit "${FAKE_DOCKER_RUN_RC:-0}" ;;
esac
""",
        "flock": '#!/usr/bin/env bash\necho "$*" >>"$REGISTRO/flock.log"\nexit "${FAKE_FLOCK_RC:-0}"\n',
        "git": f'#!/usr/bin/env bash\nif [[ "$*" == *"rev-parse HEAD"* ]]; then echo "${{FAKE_HEAD}}{"0" * (40 - 7)}"; else exec {git_real} "$@"; fi\n',
    }
    for nome, conteudo in scripts.items():
        (falsos / nome).write_text(conteudo)
        (falsos / nome).chmod(0o755)
    (raiz / ".env").write_text(
        mudancas.pop("env_texto", None)
        or "POSTGRES_USER=usuario\nPOSTGRES_DB=banco\nPOSTGRES_PASSWORD='p@ss:w/rd#1 %'\n"
    )
    if mudancas.pop("git_config", True):  # num worktree o .git é arquivo e não há .git/config a esconder
        (raiz / ".git").mkdir(exist_ok=True)
        (raiz / ".git" / "config").write_text("[core]\n")
    env = {
        **_ambiente_limpo(),
        "PATH": f"{falsos}:{os.environ['PATH']}",
        "REGISTRO": str(registro),
        "LEGISDATA_DIR": str(raiz),
        "DEPLOY_STATE_DIR": str(estado),
        "HOME": str(tmp_path / "home"),
        "FAKE_IMAGEM": "ghcr.io/saulozitos/legisdata-backend:abc1234",
        "FAKE_HEAD": "abc1234",
        **mudancas,
    }
    resposta = subprocess.run(["bash", str(FINANCAS_SH)], capture_output=True, text=True, env=env, check=False)
    chamadas = []
    log = registro / "docker.log"
    if log.exists():
        chamadas = [linha.split("\x1f")[:-1] for linha in log.read_text().splitlines()]
    return resposta, chamadas, registro, raiz


def _docker_run(chamadas):
    return [c for c in chamadas if c and c[0] == "run"]


@SEM_BASH
def test_script_das_financas_roda_o_contenier_endurecido_sem_a_senha_na_linha_de_comando(tmp_path):
    resposta, chamadas, registro, raiz = _ambiente_do_script_das_financas(tmp_path)
    assert resposta.returncode == 0, resposta.stderr
    (execucao,) = _docker_run(chamadas)
    argv = " ".join(execucao)
    assert "p@ss" not in argv and "w/rd" not in argv  # a senha nunca aparece no argv (visível em `ps`)
    for esperado in ("--cap-drop", "ALL", "no-new-privileges", "--user"):
        assert esperado in execucao, esperado
    assert f"{raiz}:/repo:ro" in execucao and f"{raiz}/etl/data:/repo/etl/data" in execucao
    assert "/dev/null:/repo/.env:ro" in execucao
    assert execucao[-3:] == ["python", "-m", "etl.pipelines.financas_atualizacao"]
    assert "ghcr.io/saulozitos/legisdata-backend:abc1234" in execucao  # a imagem que está no ar
    # o arquivo de ambiente existiu com modo 600, levou o banco em variáveis separadas e foi removido no fim
    assert (registro / "envfile_modo").read_text().strip() == "600"
    conteudo = (registro / "envfile").read_text()
    assert "POSTGRES_PASSWORD=p@ss:w/rd#1 %\n" in conteudo and "POSTGRES_SERVER=postgres" in conteudo
    assert "DATABASE_URL" not in conteudo  # a URL (com a senha codificada) é montada pelo Settings do backend
    assert not Path((registro / "envfile_caminho").read_text().strip()).exists()


@SEM_BASH
def test_script_das_financas_repassa_os_pares_de_argumentos_certos_ao_contenier(tmp_path):
    resposta, chamadas, _, raiz = _ambiente_do_script_das_financas(tmp_path, LEGISDATA_ACEITAR_ENCOLHIMENTO="1")
    assert resposta.returncode == 0, resposta.stderr
    (execucao,) = _docker_run(chamadas)
    pares = {(execucao[i], execucao[i + 1]) for i in range(len(execucao) - 1)}
    esperados = {
        ("--network", "legisdata_default"),
        ("-w", "/app"),
        ("-e", "ENVIRONMENT=production"),
        ("-e", "PYTHONPATH=/repo/backend:/repo"),
        (
            "-e",
            "LEGISDATA_ACEITAR_ENCOLHIMENTO=1",
        ),  # a liberação de uma redução legítima chega ao timer só pela linha de comando
        ("--pids-limit", "256"),
        ("-v", "/dev/null:/repo/.git/config:ro"),  # credenciais de remote do checkout não entram no contêiner
    }
    assert esperados <= pares, esperados - pares


@SEM_BASH
def test_sem_git_config_no_checkout_nao_ha_montagem_a_esconder(tmp_path):
    resposta, chamadas, _, _ = _ambiente_do_script_das_financas(tmp_path, git_config=False)
    (execucao,) = _docker_run(chamadas)
    assert resposta.returncode == 0 and not any("/repo/.git/config" in arg for arg in execucao)


@SEM_BASH
def test_script_das_financas_nao_repassa_a_liberacao_quando_ela_nao_foi_pedida(tmp_path):
    _, chamadas, _, _ = _ambiente_do_script_das_financas(tmp_path)
    (execucao,) = _docker_run(chamadas)
    assert "LEGISDATA_ACEITAR_ENCOLHIMENTO=" in execucao  # vazia: a proteção contra encolhimento continua ligada


@SEM_BASH
def test_script_das_financas_diz_que_a_tag_nao_e_um_commit_em_vez_de_acusar_divergencia(tmp_path):
    resposta, chamadas, _, _ = _ambiente_do_script_das_financas(
        tmp_path, FAKE_IMAGEM="ghcr.io/x/legisdata-backend:latest"
    )
    assert resposta.returncode == 1 and "não tem como tag o commit" in resposta.stdout
    assert "não é a do checkout" not in resposta.stdout and _docker_run(chamadas) == []


@SEM_BASH
def test_arquivo_de_ambiente_das_financas_vai_para_o_runtime_dir_quando_ele_existe(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    _, _, registro, _ = _ambiente_do_script_das_financas(tmp_path, XDG_RUNTIME_DIR=str(runtime))
    assert (registro / "envfile_caminho").read_text().strip().startswith(str(runtime) + "/")


@SEM_BASH
def test_script_das_financas_espera_o_lock_do_deploy_e_desiste_com_erro(tmp_path):
    resposta, chamadas, registro, _ = _ambiente_do_script_das_financas(tmp_path, FAKE_FLOCK_RC="1")
    assert resposta.returncode == 1 and "deploy em andamento" in resposta.stdout
    assert _docker_run(chamadas) == []
    assert "-w 1800 9" in (registro / "flock.log").read_text()


@SEM_BASH
def test_script_das_financas_recusa_rodar_com_imagem_diferente_do_checkout(tmp_path):
    """Depois de um rollback o checkout está no commit novo e a imagem no antigo: código e dependências divergem."""
    resposta, chamadas, _, _ = _ambiente_do_script_das_financas(tmp_path, FAKE_HEAD="def5678")
    assert resposta.returncode == 1 and "não é a do checkout" in resposta.stdout and "abc1234" in resposta.stdout
    assert _docker_run(chamadas) == []


@SEM_BASH
@pytest.mark.parametrize("valor", ["a\nb", "a\rb"])
def test_script_das_financas_recusa_senha_com_quebra_de_linha(tmp_path, valor):
    resposta, chamadas, _, _ = _ambiente_do_script_das_financas(tmp_path, env_texto=f'POSTGRES_PASSWORD="{valor}"\n')
    assert resposta.returncode == 1 and "quebra de linha" in resposta.stdout
    assert _docker_run(chamadas) == []  # nenhum contêiner subiu


@SEM_BASH
@pytest.mark.parametrize("env_texto", ["POSTGRES_USER=u\n", "POSTGRES_PASSWORD=\n"])
def test_script_das_financas_diz_que_a_senha_esta_ausente_em_vez_de_quebrar_com_variavel_nao_definida(
    tmp_path, env_texto
):
    resposta, chamadas, _, _ = _ambiente_do_script_das_financas(tmp_path, env_texto=env_texto)
    assert resposta.returncode == 1 and "POSTGRES_PASSWORD ausente" in resposta.stdout
    assert "unbound" not in resposta.stderr and _docker_run(chamadas) == []


@SEM_BASH
def test_o_script_das_financas_inspeciona_o_conteiner_da_api(tmp_path):
    _, chamadas, _, _ = _ambiente_do_script_das_financas(tmp_path)
    assert ["inspect", "--format", "{{.Config.Image}}", "politica_api"] in chamadas


@SEM_BASH
def test_restos_de_arquivo_de_ambiente_antigos_sao_removidos_e_os_recentes_ficam(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    velho, novo = runtime / "legisdata-env.antigo", runtime / "legisdata-env.recente"
    velho.write_text("x")
    novo.write_text("y")
    os.utime(velho, (1, 1))
    _ambiente_do_script_das_financas(tmp_path, XDG_RUNTIME_DIR=str(runtime))
    assert not velho.exists() and novo.exists()


@SEM_BASH
def test_falha_do_contenier_sobe_como_erro_e_o_arquivo_de_ambiente_e_removido(tmp_path):
    resposta, _, registro, _ = _ambiente_do_script_das_financas(tmp_path, FAKE_DOCKER_RUN_RC="3")
    assert resposta.returncode == 3 and "concluído" not in resposta.stdout
    assert not Path((registro / "envfile_caminho").read_text().strip()).exists()


def test_units_da_atualizacao_diaria_sao_de_usuario_e_nao_guardam_caminho_do_servidor():
    servico = _texto(SYSTEMD / "legisdata-financas.service")
    timer = _texto(SYSTEMD / "legisdata-financas.timer")
    assert "EnvironmentFile=%h/.legisdata-deploy/ambiente" in servico
    assert "ExecStart=%h/.legisdata-deploy/atualizar_financas.sh" in servico
    assert "Persistent=true" in timer and "WantedBy=timers.target" in timer
    for texto in (servico, timer, _texto(FINANCAS_SH)):
        assert not re.search(r"/home/|/opt/|umbrel|\b\d{1,3}(\.\d{1,3}){3}\b", texto)  # nada do servidor no repositório


def test_o_timer_das_financas_nao_roda_em_horario_redondo_e_espalha_a_hora():
    """A documentação da API do Senado pede para evitar rotinas em horários arredondados (HTTP 429 por pico)."""
    timer = _texto(SYSTEMD / "legisdata-financas.timer")
    hora = re.search(r"^OnCalendar=\*-\*-\* (\d\d):(\d\d):(\d\d)$", timer, re.MULTILINE)
    assert hora and hora.group(2) not in {"00", "15", "30", "45"} and hora.group(3) == "00"
    assert re.search(r"^RandomizedDelaySec=\d+min$", timer, re.MULTILINE)


def test_o_deploy_mantem_a_copia_do_script_das_financas_igual_a_do_commit_implantado():
    texto = _texto(DEPLOY_SH)
    instalacao = _posicao(texto, r'install -m 755 "\$RAIZ/scripts/deploy/atualizar_financas\.sh"')
    assert instalacao < _posicao(texto, r'^echo "\$TAG" >"\$ESTADO_DIR/ultima_tag"')  # só depois da saúde
    assert re.search(
        r'bash -n "\$RAIZ/scripts/deploy/atualizar_financas\.sh"', texto
    )  # script com erro nunca é instalado


def _fake_systemctl(tmp_path, existe=True, start_rc=0):
    """Um `systemctl` falso que registra o que recebeu; `cat` falha quando a unit não existe."""
    falsos = tmp_path / "falsos"
    falsos.mkdir(exist_ok=True)
    (falsos / "systemctl").write_text(
        '#!/usr/bin/env bash\necho "$*" >>"$REGISTRO/systemctl.log"\n'
        # só a unit das finanças, do usuário, existe (e só ela inicia): nome ou escopo errado no script não passa
        '[[ "$1" == --user ]] || exit 9\n'
        f'case "$2 $3" in "cat legisdata-financas.service") exit {0 if existe else 1} ;; '
        f'"start --no-block") [[ "$4" == legisdata-financas.service ]] && exit {start_rc} || exit 9 ;; esac\nexit 1\n'
    )
    (falsos / "systemctl").chmod(0o755)
    registro = tmp_path / "registro"
    registro.mkdir(exist_ok=True)
    return {"PATH": f"{falsos}:{os.environ['PATH']}", "REGISTRO": str(registro)}


def _disparo(tmp_path, *, existe, start_rc=0, refrescar="0", pendente=""):
    """Roda o bloco `disparo_financas` do deploy.sh com bash de verdade; devolve (saída, conteúdo de financas_pendente)."""
    estado = tmp_path / "estado"
    estado.mkdir(exist_ok=True)
    if pendente:
        (estado / "financas_pendente").write_text(pendente)
    texto = _texto(DEPLOY_SH)
    script = (
        f'ESTADO_DIR="{estado}"\nlog() {{ echo "LOG: $*"; }}\n{_bloco(texto, "pendencias")}\n'
        f'LEGISDATA_FIN_REFRESCAR={refrescar}\n{_bloco(texto, "disparo_financas")}'
    )
    resposta = _bash(script, env=_fake_systemctl(tmp_path, existe, start_rc))
    assert resposta.returncode == 0, resposta.stderr
    arquivo = estado / "financas_pendente"
    return resposta.stdout, (arquivo.read_text() if arquivo.exists() else None), tmp_path / "registro" / "systemctl.log"


@SEM_BASH
def test_disparo_com_a_unit_instalada_dispara_e_nao_deixa_pendencia(tmp_path):
    saida, pendente, log = _disparo(tmp_path, existe=True, refrescar="1")
    assert "atualização das finanças disparada" in saida and pendente is None
    assert "--user start --no-block legisdata-financas.service" in log.read_text()


@SEM_BASH
def test_disparo_sem_a_unit_registra_o_pedido_e_avisa(tmp_path):
    saida, pendente, _ = _disparo(tmp_path, existe=False, refrescar="1")
    assert "o pedido ficou registrado" in saida and pendente == "refrescar\n"


@SEM_BASH
def test_disparo_que_o_systemd_recusa_mantem_o_pedido(tmp_path):
    saida, pendente, _ = _disparo(tmp_path, existe=True, start_rc=1, refrescar="1")
    assert "não consegui disparar" in saida and pendente == "refrescar\n"


@SEM_BASH
def test_pedido_antigo_e_cumprido_mesmo_sem_pedido_novo_e_a_carga_pendente_fica(tmp_path):
    _, pendente, log = _disparo(tmp_path, existe=True, refrescar="0", pendente="carga\nrefrescar\n")
    assert pendente == "carga\n" and "start --no-block legisdata-financas.service" in log.read_text()


@SEM_BASH
def test_sem_pedido_e_sem_unit_so_avisa_que_o_timer_nao_esta_instalado(tmp_path):
    saida, pendente, _ = _disparo(tmp_path, existe=False, refrescar="0")
    assert "legisdata-financas.timer não está instalado" in saida and pendente is None


def _apos_carga(tmp_path, saida_da_carga, *, previa_pendente="", tentada=None):
    estado = tmp_path / "estado"
    estado.mkdir(exist_ok=True)
    if previa_pendente:
        (estado / "financas_pendente").write_text(previa_pendente)
    if tentada is not None:
        (estado / "financas_carga_tentada").write_text(str(tentada))
    texto = _texto(DEPLOY_SH)
    script = (
        f'ESTADO_DIR="{estado}"\nlog() {{ echo "LOG: $*"; }}\n{_bloco(texto, "pendencias")}\n'
        f"SAIDA_CARGA=$(cat <<'FIM'\n{saida_da_carga}\nFIM\n)\n{_bloco(texto, 'apos_carga')}"
    )
    resposta = _bash(script)
    assert resposta.returncode == 0, resposta.stderr
    pend = estado / "financas_pendente"
    carimbo = estado / "financas_carga_tentada"
    return pend.read_text() if pend.exists() else None, (carimbo.read_text().strip() if carimbo.exists() else None)


@SEM_BASH
def test_carga_tolerada_que_falhou_vira_pendencia_com_carimbo_de_tentativa(tmp_path):
    pendente, carimbo = _apos_carga(tmp_path, "financas {'erro': 'x'}\nFALHA_TOLERADA financas")
    import time

    assert (
        pendente == "carga\n" and carimbo.isdigit() and abs(int(carimbo) - time.time()) < 60
    )  # segundos desde a época


@SEM_BASH
def test_carga_que_passou_limpa_a_pendencia_de_carga_e_o_carimbo_sem_tocar_nas_outras(tmp_path):
    pendente, carimbo = _apos_carga(tmp_path, "series {'ok': 1}", previa_pendente="carga\nrefrescar\n", tentada=1)
    assert pendente == "refrescar\n" and carimbo is None


def test_o_python_do_deploy_e_o_bash_concordam_sobre_o_marcador_da_falha_tolerada():
    """O bash procura `FALHA_TOLERADA <chave>` e o Python o imprime para cada carga tolerada que devolveu erro."""
    from etl.pipelines.carga_economica import falhas_toleradas

    assert falhas_toleradas({"financas": {"erro": "x"}, "series": {"erro": "y"}}) == ["financas"]
    carga = _texto(DEPLOY_SH)
    assert "print('FALHA_TOLERADA', chave)" in carga and "grep -q '^FALHA_TOLERADA '" in carga


@SEM_BASH
@pytest.mark.parametrize(
    "pendencia, carimbo, pode",
    [
        ("", None, False),  # sem pendência de carga não há o que repetir
        ("carga\n", None, True),  # pendente e sem carimbo: repete
        ("carga\n", 10**12, False),  # tentada "no futuro" (agora < carimbo + intervalo): ainda espera
        ("carga\n", 1, True),  # tentada há muito tempo
        ("refrescar\n", None, False),  # outra pendência não repete a carga
    ],
)
def test_a_carga_pendente_so_repete_depois_do_intervalo(tmp_path, pendencia, carimbo, pode):
    estado = tmp_path / "estado"
    estado.mkdir()
    if pendencia:
        (estado / "financas_pendente").write_text(pendencia)
    if carimbo is not None:
        (estado / "financas_carga_tentada").write_text(str(carimbo))
    script = (
        f'ESTADO_DIR="{estado}"\n{_bloco(_texto(DEPLOY_SH), "pendencias")}\ncarga_pode_repetir && echo sim || echo nao'
    )
    resposta = _bash(script)
    assert resposta.stdout.strip() == ("sim" if pode else "nao"), resposta.stderr


def _mesmo_commit(
    tmp_path, *, atual="abc", alvo="abc", pendente="", tentada=None, dry_run=0, intervalo=3600, unit=True
):
    """Roda o bloco `mesmo_commit` do deploy.sh (com `exit` de verdade). Devolve (saída, pendências, carimbo)."""
    estado = tmp_path / "estado"
    estado.mkdir(exist_ok=True)
    if pendente:
        (estado / "financas_pendente").write_text(pendente)
    if tentada is not None:
        (estado / "financas_carga_tentada").write_text(str(tentada))
    texto = _texto(DEPLOY_SH)
    script = (
        f'ESTADO_DIR="{estado}"\nINTERVALO_DA_CARGA={intervalo}\nlog() {{ echo "LOG: $*"; }}\nDRY_RUN={dry_run}\n'
        f'ATUAL={atual}\nALVO={alvo}\n{_bloco(texto, "pendencias")}\n{_bloco(texto, "mesmo_commit")}\n'
        'echo "SEGUIU REPETICAO=$REPETICAO"'
    )
    resposta = _bash(script, env=_fake_systemctl(tmp_path, unit))
    assert resposta.returncode == 0, resposta.stderr
    pend = estado / "financas_pendente"
    carimbo = estado / "financas_carga_tentada"
    log = tmp_path / "registro" / "systemctl.log"
    return (
        resposta.stdout,
        pend.read_text() if pend.exists() else None,
        carimbo.read_text().strip() if carimbo.exists() else None,
        log.read_text() if log.exists() else "",
    )


@SEM_BASH
def test_mesmo_commit_sem_pendencia_sai_sem_fazer_nada(tmp_path):
    saida, pendente, carimbo, systemctl = _mesmo_commit(tmp_path)
    assert "SEGUIU" not in saida and pendente is None and carimbo is None and "start" not in systemctl


@SEM_BASH
def test_mesmo_commit_com_pedido_de_atualizacao_dispara_limpa_e_sai(tmp_path):
    saida, pendente, _, systemctl = _mesmo_commit(tmp_path, pendente="refrescar\n")
    assert "SEGUIU" not in saida and "pendente disparada" in saida and pendente is None
    assert "start --no-block legisdata-financas.service" in systemctl


@SEM_BASH
def test_mesmo_commit_com_carga_pendente_vencida_segue_carimba_a_tentativa_e_nao_mexe_no_pedido(tmp_path):
    import time

    saida, pendente, carimbo, _ = _mesmo_commit(tmp_path, pendente="carga\n", tentada=1)
    assert "SEGUIU REPETICAO=1" in saida and pendente == "carga\n"
    assert abs(int(carimbo) - time.time()) < 60  # um instante de agora, em segundos desde a época


@SEM_BASH
def test_mesmo_commit_com_carga_dentro_do_intervalo_sai(tmp_path):
    import time

    agora = int(time.time())
    saida, _, carimbo, _ = _mesmo_commit(tmp_path, pendente="carga\n", tentada=agora)
    assert "SEGUIU" not in saida and carimbo == str(agora)  # sai sem regravar o carimbo


@SEM_BASH
def test_commit_novo_segue_sem_repeticao_e_sem_carimbo(tmp_path):
    saida, pendente, carimbo, _ = _mesmo_commit(tmp_path, atual="abc", alvo="def", pendente="refrescar\n")
    assert "SEGUIU REPETICAO=0" in saida and pendente == "refrescar\n" and carimbo is None


@SEM_BASH
def test_dry_run_com_o_mesmo_commit_nao_dispara_nao_limpa_nem_carimba(tmp_path):
    saida, pendente, carimbo, systemctl = _mesmo_commit(tmp_path, pendente="carga\nrefrescar\n", tentada=1, dry_run=1)
    assert "SEGUIU REPETICAO=1" in saida  # segue até testar as imagens (o dry-run sai depois)
    assert pendente == "carga\nrefrescar\n" and carimbo == "1" and "start" not in systemctl


@SEM_BASH
@pytest.mark.parametrize("carimbo", ["lixo", "", "12 34", None, "1000"])
def test_carimbo_ilegivel_ou_antigo_repete(tmp_path, carimbo):
    saida, *_ = _mesmo_commit(tmp_path, pendente="carga\n", tentada=carimbo)
    assert "SEGUIU REPETICAO=1" in saida


@SEM_BASH
def test_o_carimbo_nunca_e_avaliado_como_expressao_aritmetica(tmp_path):
    armadilha = tmp_path / "executou"
    saida, *_ = _mesmo_commit(tmp_path, pendente="carga\n", tentada=f"a[$(touch {armadilha})]")
    assert "SEGUIU" in saida and not armadilha.exists()


@SEM_BASH
@pytest.mark.parametrize("agora, esperado", [(1100, "sim"), (1099, "nao")])  # carimbo 1000, intervalo 100
def test_fronteira_exata_do_intervalo(tmp_path, agora, esperado):
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "financas_pendente").write_text("carga\n")
    (estado / "financas_carga_tentada").write_text("1000")
    script = (
        f'ESTADO_DIR="{estado}"\nINTERVALO_DA_CARGA=100\n{_bloco(_texto(DEPLOY_SH), "pendencias")}\n'
        f"date() {{ echo {agora}; }}\ncarga_pode_repetir && echo sim || echo nao"
    )
    assert _bash(script).stdout.strip() == esperado


@SEM_BASH
def test_intervalo_invalido_no_ambiente_volta_ao_padrao(tmp_path):
    estado = tmp_path / "estado"
    estado.mkdir()
    resposta = _bash(
        f'ESTADO_DIR="{estado}"\nINTERVALO_DA_CARGA=1h\n{_bloco(_texto(DEPLOY_SH), "pendencias")}\necho $INTERVALO_DA_CARGA'
    )
    assert resposta.stdout.strip() == "3600"


# ── instalar.sh (bash de verdade, repositório git e comandos falsos) ─────────────────────────────────────────────────
def _instalacao(tmp_path, *, tag=None, env_rc="0", timer_rc="0", previo=None, dry_rc="0", inspect_rc="0", start_rc="0"):
    repo, casa, falsos, registro = tmp_path / "repo", tmp_path / "home", tmp_path / "bin", tmp_path / "registro"
    for pasta in (repo / "scripts" / "deploy", repo / "scripts" / "systemd", casa, falsos, registro):
        pasta.mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "deploy" / "deploy.sh").write_text(
        '#!/usr/bin/env bash\necho "deploy-falso $*"\nexit "${FAKE_DRY_RC:-0}"\n'
        # o instalador carrega as funções de pendência do próprio deploy.sh: o falso leva o bloco verdadeiro
        + "# >>> pendencias\n"
        + _bloco(_texto(DEPLOY_SH), "pendencias")
        + "# <<< pendencias\n"
    )
    shutil.copy(FINANCAS_SH, repo / "scripts" / "deploy" / "atualizar_financas.sh")
    shutil.copy(INSTALAR_SH, repo / "scripts" / "deploy" / "instalar.sh")
    for unit in SYSTEMD.glob("legisdata-*"):
        shutil.copy(unit, repo / "scripts" / "systemd" / unit.name)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "primeiro")
    sha = _git(repo, "rev-parse", "HEAD")
    comandos = {
        "docker": '#!/usr/bin/env bash\necho "docker $*" >>"$REGISTRO/chamadas.log"\nif [[ "$1" == inspect ]]; then [[ "${FAKE_INSPECT_RC:-0}" == 0 ]] || exit "$FAKE_INSPECT_RC"; echo "ghcr.io/x/legisdata-backend:${FAKE_TAG}"; fi\nexit 0\n',
        "systemctl": '#!/usr/bin/env bash\necho "systemctl $*" >>"$REGISTRO/chamadas.log"\n'
        'case "$2" in show-environment) exit "${FAKE_ENV_RC}" ;; is-enabled|is-active) exit "${FAKE_TIMER_RC}" ;; start) exit "${FAKE_START_RC:-0}" ;; esac\nexit 0\n',
        "loginctl": "#!/usr/bin/env bash\nexit 0\n",
    }
    for nome, conteudo in comandos.items():
        (falsos / nome).write_text(conteudo)
        (falsos / nome).chmod(0o755)
    if previo:
        (casa / ".legisdata-deploy").mkdir()
        for nome, conteudo in previo.items():
            (casa / ".legisdata-deploy" / nome).write_text(conteudo)

    def executar(tag_no_ar=None):
        env = {
            **os.environ,
            "PATH": f"{falsos}:{os.environ['PATH']}",
            "HOME": str(casa),
            "REGISTRO": str(registro),
            "FAKE_TAG": tag_no_ar or tag or sha[:7],
            "FAKE_ENV_RC": env_rc,
            "FAKE_TIMER_RC": timer_rc,
            "FAKE_DRY_RC": dry_rc,
            "FAKE_INSPECT_RC": inspect_rc,
            "FAKE_START_RC": start_rc,
        }
        for chave in [k for k in env if k.startswith("GIT_")]:
            del env[chave]
        env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(
            ["bash", "scripts/deploy/instalar.sh", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    return repo, casa, registro, sha, executar


@SEM_BASH
def test_primeira_instalacao_marca_o_commit_que_esta_no_ar_instala_tudo_e_liga_os_dois_timers(tmp_path):
    repo, casa, registro, sha, executar = _instalacao(tmp_path)
    resposta = executar()
    assert resposta.returncode == 0, resposta.stdout + resposta.stderr
    destino = casa / ".legisdata-deploy"
    assert (destino / "ultimo_sha").read_text().strip() == sha and (destino / "ultima_tag").read_text().strip() == sha[
        :7
    ]
    for script in ("deploy.sh", "atualizar_financas.sh"):
        assert (destino / script).stat().st_mode & stat.S_IXUSR
    unidades = {p.name for p in (casa / ".config" / "systemd" / "user").iterdir()}
    assert unidades == {
        "legisdata-deploy.service",
        "legisdata-deploy.timer",
        "legisdata-financas.service",
        "legisdata-financas.timer",
    }
    chamadas = (registro / "chamadas.log").read_text()
    assert "systemctl --user enable --now legisdata-deploy.timer" in chamadas
    assert "systemctl --user enable --now legisdata-financas.timer" in chamadas
    assert "dry-run ok" in resposta.stdout and "deploy-falso --dry-run" in resposta.stdout


@SEM_BASH
def test_reinstalar_nao_marca_como_implantado_um_commit_que_ainda_nao_subiu(tmp_path):
    repo, casa, registro, sha, executar = _instalacao(tmp_path)
    assert executar().returncode == 0
    (repo / "novo.txt").write_text("x")  # entrou outro commit na main e o CI ainda publica as imagens dele
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "segundo")
    resposta = executar()  # o que está no ar continua sendo o primeiro
    assert resposta.returncode == 0 and "estado existente mantido" in resposta.stdout
    assert (casa / ".legisdata-deploy" / "ultimo_sha").read_text().strip() == sha  # e não o HEAD novo


@SEM_BASH
def test_instalador_nao_altera_nada_se_o_systemd_do_usuario_nao_responde(tmp_path):
    repo, casa, registro, _, executar = _instalacao(tmp_path, env_rc="1")
    resposta = executar()
    assert resposta.returncode == 1 and "nada foi alterado" in resposta.stdout
    assert not (casa / ".legisdata-deploy").exists() and not (casa / ".config").exists()
    assert "docker" not in (registro / "chamadas.log").read_text()  # nem o Watchtower foi mexido


@SEM_BASH
def test_instalador_falha_alto_se_um_timer_nao_ficou_ativo(tmp_path):
    _, _, _, _, executar = _instalacao(tmp_path, timer_rc="1")
    resposta = executar()
    assert resposta.returncode == 1 and "ERRO: legisdata-deploy.timer não ficou ativo" in resposta.stdout


@SEM_BASH
def test_imagem_no_ar_que_nao_e_um_commit_nao_inventa_estado(tmp_path):
    _, casa, _, _, executar = _instalacao(tmp_path)
    resposta = executar(tag_no_ar="latest")
    assert resposta.returncode == 0 and "AVISO: a imagem no ar (latest) não é um commit" in resposta.stdout
    assert not (casa / ".legisdata-deploy" / "ultimo_sha").exists()  # sem estado, o primeiro deploy implanta a main


@SEM_BASH
def test_dry_run_que_falha_aborta_o_instalador_antes_de_mexer_no_watchtower_e_nos_timers(tmp_path):
    _, _, registro, _, executar = _instalacao(tmp_path, dry_rc="1")
    resposta = executar()
    assert resposta.returncode == 1 and "o dry-run do deploy falhou" in resposta.stdout
    chamadas = (registro / "chamadas.log").read_text()
    assert "docker rm" not in chamadas and "enable" not in chamadas and "dry-run ok" not in resposta.stdout


@SEM_BASH
def test_servidor_sem_a_api_no_ar_instala_sem_estado_em_vez_de_abortar_no_docker_inspect(tmp_path):
    _, casa, _, _, executar = _instalacao(tmp_path, inspect_rc="1")
    resposta = executar()
    assert resposta.returncode == 0, resposta.stdout + resposta.stderr
    assert not (casa / ".legisdata-deploy" / "ultimo_sha").exists()


@SEM_BASH
def test_instalador_dispara_a_atualizacao_pedida_por_um_deploy_anterior_e_limpa_o_pedido(tmp_path):
    _, casa, registro, _, executar = _instalacao(tmp_path, previo={"financas_pendente": "refrescar\n"})
    resposta = executar()
    assert resposta.returncode == 0, resposta.stdout + resposta.stderr
    chamadas = (registro / "chamadas.log").read_text().splitlines()
    ligar = chamadas.index("systemctl --user enable --now legisdata-financas.timer")
    disparo = chamadas.index("systemctl --user start --no-block legisdata-financas.service")
    assert ligar < disparo  # a unit existe e o timer está ligado antes do disparo
    assert not (casa / ".legisdata-deploy" / "financas_pendente").exists()


@SEM_BASH
def test_instalador_mantem_o_pedido_se_nao_conseguiu_disparar_e_preserva_outras_pendencias(tmp_path):
    _, casa, _, _, executar = _instalacao(tmp_path, previo={"financas_pendente": "carga\nrefrescar\n"}, start_rc="1")
    resposta = executar()
    assert resposta.returncode == 0 and "não consegui disparar" in resposta.stdout
    assert (casa / ".legisdata-deploy" / "financas_pendente").read_text() == "carga\nrefrescar\n"
    # com o disparo funcionando, só o "refrescar" sai
    _, casa2, _, _, executar2 = _instalacao(tmp_path / "b", previo={"financas_pendente": "carga\nrefrescar\n"})
    assert executar2().returncode == 0
    assert (casa2 / ".legisdata-deploy" / "financas_pendente").read_text() == "carga\n"


def test_instalador_checa_o_systemd_antes_de_gravar_qualquer_coisa():
    texto = _texto(INSTALAR_SH)
    assert _posicao(texto, r"systemctl --user show-environment") < _posicao(texto, r"^mkdir -p ")
    assert _posicao(texto, r"^mkdir -p ") < _posicao(texto, r"^docker rm -f politica_watchtower")


def test_contineres_do_deploy_usam_a_mesma_contencao_e_escondem_o_git_config():
    texto = _texto(DEPLOY_SH)
    assert texto.count('"${CONTENCAO[@]}"') == 2  # a migração e o um_comando, na mesma lista de flags
    assert "-v /dev/null:/repo/.git/config:ro" in texto
    assert re.search(r'chmod 600 "\$RAIZ/\.env"', texto)
    assert 'mktemp -p "$DIR_TEMP"' in texto and "XDG_RUNTIME_DIR" in texto


def test_as_consultas_de_dados_do_fin_do_deploy_sao_as_do_python():
    from etl.pipelines.carga_economica import SQL_FIN_TEM_ALGUM_DADO, SQL_FIN_TEM_CEAP, SQL_FIN_TEM_EMENDAS

    texto = _texto(DEPLOY_SH)
    for consulta in (SQL_FIN_TEM_CEAP, SQL_FIN_TEM_EMENDAS, SQL_FIN_TEM_ALGUM_DADO):
        assert f'-tAc "select {consulta}"' in texto


def test_o_preambulo_do_arquivo_de_ambiente_e_o_mesmo_nos_dois_scripts():
    """Os scripts são instalados como cópias avulsas (sem biblioteca comum): a parte compartilhada não pode divergir."""
    deploy = _bloco(_texto(DEPLOY_SH), "env_banco")
    financas = _bloco(_texto(FINANCAS_SH), "env_banco_financas")
    comum = [
        "POSTGRES_PASSWORD ausente no .env",
        "POSTGRES_PASSWORD com quebra de linha não cabe no arquivo de ambiente",
        'DIR_TEMP="${XDG_RUNTIME_DIR:-}"',
        'DIR_TEMP="${ESTADO_DIR:-${TMPDIR:-/tmp}}"',
        "find \"$DIR_TEMP\" -maxdepth 1 -name 'legisdata-env.*' -mmin +60 -delete",
        'ENV_BANCO="$(mktemp -p "$DIR_TEMP" legisdata-env.XXXXXX)"',
        "trap 'rm -f \"$ENV_BANCO\"' EXIT",
        'chmod 600 "$ENV_BANCO"',
    ]
    for trecho in comum:
        assert trecho in deploy and trecho in financas, trecho


@SEM_BASH
def test_na_reexecucao_o_bloco_herda_a_decisao_em_vez_de_ver_o_proprio_carimbo(tmp_path):
    """A 1ª passada decidiu repetir e carimbou; a cópia reexecutada herda `REPETICAO=1` e segue."""
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "financas_pendente").write_text("carga\n")
    import time

    (estado / "financas_carga_tentada").write_text(str(int(time.time())))  # carimbado agora, pela 1ª passada
    texto = _texto(DEPLOY_SH)
    script = (
        f'ESTADO_DIR="{estado}"\nlog() {{ echo "LOG: $*"; }}\nDRY_RUN=0\nATUAL=abc\nALVO=abc\n'
        f'{_bloco(texto, "pendencias")}\n{_bloco(texto, "mesmo_commit")}\necho "SEGUIU REPETICAO=$REPETICAO"'
    )
    reexecucao = _bash(script, env={"_LEGISDATA_DEPLOY_REEXEC": "1", "_LEGISDATA_DEPLOY_REPETICAO": "1"})
    assert "SEGUIU REPETICAO=1" in reexecucao.stdout
    primeira = _bash(script)  # sem as variáveis de reexecução: vê o carimbo de agora e sai
    assert primeira.returncode == 0 and primeira.stderr == "" and "SEGUIU" not in primeira.stdout  # saiu, sem erro
    assert 'REEXEC=1 _LEGISDATA_DEPLOY_ALVO="$ALVO" _LEGISDATA_DEPLOY_REPETICAO="$REPETICAO" exec' in texto


def test_instalador_avisa_quando_o_deploy_instalado_nao_traz_o_bloco_de_pendencias():
    texto = _texto(INSTALAR_SH)
    assert "declare -F pendente_tem" in texto and "não traz o bloco de pendências" in texto


@SEM_BASH
def test_sem_os_argumentos_dos_marcadores_a_decisao_cai_no_lado_seguro_e_nunca_semeia(repo_de_decisao):
    """Quem chamar `decidir_financas` sem os dois últimos argumentos (as flags do timer) recebe o comportamento que não reescreve fonte do timer."""
    (repo_de_decisao / "docs" / "leia-me.md").write_text("zzz")
    _git(repo_de_decisao, "add", "-A")
    _git(repo_de_decisao, "commit", "-q", "-m", "x")
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    for chamada in ('"HEAD~1" HEAD t t', '"HEAD~1" HEAD t t ""'):
        resposta = _bash(f"{funcao}\ndecidir_financas {chamada}", cwd=repo_de_decisao)
        assert resposta.stdout.strip() == "nenhuma 0", chamada


@SEM_BASH
def test_se_a_consulta_das_fontes_do_timer_falha_o_bloco_aborta_em_vez_de_semear_do_git(tmp_path):
    """Sem resposta do banco o deploy não pode cair em 'f f' (que semearia do git por cima do dado fresco)."""
    falsos = tmp_path / "bin"
    falsos.mkdir()
    (falsos / "docker").write_text("#!/usr/bin/env bash\nexit 1\n")
    (falsos / "docker").chmod(0o755)
    script = (
        "set -Eeuo pipefail\nPG_USER=u PG_DB=d\n"
        + _bloco(_texto(DEPLOY_SH), "fontes_do_timer")
        + '\necho "SEGUIU $CEAP_DO_TIMER"'
    )
    resposta = _bash(script, env={"PATH": f"{falsos}:{os.environ['PATH']}"})
    assert resposta.returncode != 0 and "SEGUIU" not in resposta.stdout


@SEM_BASH
@pytest.mark.parametrize("valor", ["x", "2", "", "a[$(touch {armadilha})]", "1; echo oi"])
def test_a_repeticao_herdada_do_ambiente_so_aceita_0_ou_1(tmp_path, valor):
    armadilha = tmp_path / "executou"
    estado = tmp_path / "estado"
    estado.mkdir()
    texto = _texto(DEPLOY_SH)
    script = (
        f'set -Eeuo pipefail\nESTADO_DIR="{estado}"\nlog() {{ :; }}\nDRY_RUN=0\nATUAL=abc\nALVO=def\n'
        f'{_bloco(texto, "pendencias")}\n{_bloco(texto, "mesmo_commit")}\necho "REPETICAO=$REPETICAO"'
    )
    resposta = _bash(
        script, env={"_LEGISDATA_DEPLOY_REPETICAO": valor.format(armadilha=armadilha), "_LEGISDATA_DEPLOY_REEXEC": "1"}
    )
    assert resposta.returncode == 0, resposta.stderr
    assert "REPETICAO=0" in resposta.stdout and not armadilha.exists()


@SEM_BASH
@pytest.mark.parametrize(
    "valor, valido",
    [
        ("a" * 40, True),
        ("abc", False),
        ("a" * 39, False),
        ("A" * 40, False),
        ("a" * 41, False),
        ("$(touch {armadilha})", False),
        ("a[$(touch {armadilha})]", False),
    ],
)
def test_o_alvo_herdado_do_ambiente_so_aceita_um_sha_de_40_hex(tmp_path, valor, valido):
    armadilha = tmp_path / "executou"
    script = 'log() { echo "LOG: $*"; }\n' + _bloco(_texto(DEPLOY_SH), "alvo") + '\necho "SEGUIU $ALVO"'
    resposta = _bash(script, env={"_LEGISDATA_DEPLOY_ALVO": valor.format(armadilha=armadilha)})
    assert not armadilha.exists()
    if valido:
        assert resposta.returncode == 0 and f"SEGUIU {valor}" in resposta.stdout
    else:
        assert resposta.returncode != 0 and "alvo inválido" in resposta.stdout and "SEGUIU" not in resposta.stdout


@SEM_BASH
@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("7", "7"),
        ("abc", "14"),
        ("0", "14"),
        ("-1", "14"),
        ("", "14"),
        ("1;echo oi", "14"),
        ("a[$(touch {armadilha})]", "14"),
    ],
)
def test_guardar_backups_so_aceita_inteiro_positivo_senao_usa_14(tmp_path, valor, esperado):
    """Um valor inválido de DEPLOY_KEEP_BACKUPS valia 1 na conta e `tail -n +1` apagaria todos os dumps."""
    armadilha = tmp_path / "executou"
    script = _bloco(_texto(DEPLOY_SH), "guardar_backups") + '\necho "$GUARDAR_BACKUPS $((GUARDAR_BACKUPS + 1))"'
    env = {"DEPLOY_KEEP_BACKUPS": valor.format(armadilha=armadilha)}
    resposta = _bash(script, env=env)
    assert resposta.returncode == 0, resposta.stderr
    assert resposta.stdout.split()[0] == esperado and not armadilha.exists()


def test_o_instalador_grava_o_diretorio_do_projeto_escapado_para_o_source(tmp_path):
    texto = _texto(RAIZ / "scripts" / "deploy" / "instalar.sh")
    assert 'printf \'LEGISDATA_DIR=%q\\n\' "$RAIZ" >"$DEST/ambiente"' in texto
    estranho = tmp_path / "pasta com espaço $(touch executou)"
    estranho.mkdir()
    ambiente = tmp_path / "ambiente"
    resposta = _bash(
        f"RAIZ={shlex.quote(str(estranho))}\nprintf 'LEGISDATA_DIR=%q\\n' \"$RAIZ\" >{shlex.quote(str(ambiente))}\n"
        f'. {shlex.quote(str(ambiente))}\nprintf %s "$LEGISDATA_DIR"',
        cwd=tmp_path,
    )
    assert resposta.stdout == str(estranho) and not (tmp_path / "executou").exists()


@SEM_BASH
@SEM_FLOCK
def test_trava_do_deploy_usa_o_lock_de_legisdata_deploy_lock_quando_a_variavel_existe(tmp_path):
    import subprocess as sp

    estado, compartilhado = tmp_path / "estado", tmp_path / "compartilhado"
    estado.mkdir()
    compartilhado.mkdir()
    lock = compartilhado / "deploy.lock"
    segurando = sp.Popen(
        ["bash", "-c", f'exec 9>"{lock}"; flock -n 9 && echo preso && sleep 30'], stdout=sp.PIPE, text=True
    )
    try:
        assert segurando.stdout.readline().strip() == "preso"
        script = (
            f'ESTADO_DIR="{estado}"\nDRY_RUN=0\nlog() {{ echo "LOG: $*"; }}\n'
            + _bloco(_texto(DEPLOY_SH), "trava_do_deploy")
            + "\necho SEGUIU"
        )
        ocupado = _bash(script, env={"LEGISDATA_DEPLOY_LOCK": str(lock)})
        assert (
            ocupado.returncode == 0
            and "outra execução em andamento" in ocupado.stdout
            and "SEGUIU" not in ocupado.stdout
        )
        livre = _bash(script)  # sem a variável o lock é o de $ESTADO_DIR, que ninguém segura
        assert "SEGUIU" in livre.stdout and (estado / "deploy.lock").exists()
    finally:
        segurando.kill()
        segurando.wait()


@SEM_BASH
@SEM_FLOCK
def test_a_reexecucao_herda_o_lock_pelo_descritor_9_e_ele_continua_preso(tmp_path):
    """O processo reexecutado não toma o lock de novo (REEXEC=1) e, por herdar o fd 9, ainda o segura: um terceiro não passa."""
    lock = tmp_path / "deploy.lock"
    bloco = _bloco(_texto(DEPLOY_SH), "trava_do_deploy")
    interno = f'ESTADO_DIR="{tmp_path}"\nDRY_RUN=0\nlog() {{ :; }}\n{bloco}\necho SEGUIU\nflock -n "{lock}" true && echo LIVRE || echo PRESO'
    externo = f'exec 9>"{lock}"\nflock -n 9\n_LEGISDATA_DEPLOY_REEXEC=1 bash -c {shlex.quote(interno)}'
    resposta = _bash(externo)
    assert resposta.stdout.split() == ["SEGUIU", "PRESO"], resposta.stderr


@SEM_BASH
def test_o_alvo_herdado_precisa_ser_ancestral_de_origin_main(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("1")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "um")
    na_main = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "branch", "-q", "lateral")
    _git(repo, "checkout", "-q", "lateral")
    (repo / "b").write_text("2")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "so na lateral")
    fora_da_main = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", na_main)
    bloco = _bloco(_texto(DEPLOY_SH), "alvo_na_main")

    def rodar(alvo):
        return _bash(f'log() {{ echo "LOG: $*"; }}\nALVO={alvo}\n{bloco}\necho SEGUIU', cwd=repo)

    assert "SEGUIU" in rodar(na_main).stdout
    recusado = rodar(fora_da_main)
    assert (
        recusado.returncode == 1
        and "não é ancestral de origin/main" in recusado.stdout
        and "SEGUIU" not in recusado.stdout
    )


@SEM_BASH
@pytest.mark.parametrize(
    "raiz, ok",
    [("/opt/projeto", True), ("/opt/com espaco", True), ("/opt/proj\neto", False), ("/opt/proj\teto", False)],
)
def test_o_instalador_recusa_caminho_do_projeto_com_caracteres_de_controle(raiz, ok):
    script = (
        f"RAIZ={shlex.quote(raiz)}\n"
        + _bloco(_texto(RAIZ / "scripts" / "deploy" / "instalar.sh"), "raiz_sem_controle")
        + "\necho SEGUIU"
    )
    resposta = _bash(script)
    assert ("SEGUIU" in resposta.stdout) is ok and (resposta.returncode == 0) is ok


def test_o_estado_do_deploy_e_endurecido_a_cada_execucao_nos_dois_scripts():
    """O diretório de estado guarda o lock e a senha do banco: 700 sempre (deploy.sh e atualizar_financas.sh)."""
    assert re.search(r'^chmod 700 "\$ESTADO_DIR"', _texto(DEPLOY_SH), re.MULTILINE)
    assert re.search(r'^chmod 700 "\$ESTADO_DIR"', _texto(FINANCAS_SH), re.MULTILINE)


@SEM_BASH
def test_o_script_das_financas_deixa_o_diretorio_de_estado_700(tmp_path):
    import stat

    (tmp_path / "estado").mkdir()
    (tmp_path / "estado").chmod(0o755)
    resposta, *_ = _ambiente_do_script_das_financas(tmp_path)
    assert resposta.returncode == 0, resposta.stderr
    assert stat.S_IMODE((tmp_path / "estado").stat().st_mode) == 0o700
