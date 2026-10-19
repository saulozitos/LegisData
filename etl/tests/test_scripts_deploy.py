"""Os scripts de deploy precisam ao menos ter sintaxe válida: um erro de shell só apareceria no servidor."""

import os
import random
import re
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


def test_deploy_se_atualiza_antes_de_tocar_no_banco():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    reexecucao = _posicao(texto, r"^\s*_LEGISDATA_DEPLOY_REEXEC=1 _LEGISDATA_DEPLOY_ALVO=\"\$ALVO\" exec ")
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
    assert re.search(r'_LEGISDATA_DEPLOY_ALVO="\$ALVO" exec ', texto)
    assert re.search(r'^git merge --ff-only -q "\$ALVO"', texto, re.MULTILINE)


def test_senha_do_banco_vai_por_arquivo_de_ambiente_e_nao_pela_linha_de_comando():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert not re.search(r"-e (ALEMBIC_)?DATABASE_URL=", texto)
    assert re.search(r"chmod 600 \"\$ENV_BANCO\"", texto) and '--env-file "$ENV_BANCO"' in texto


DEPLOY_SH = RAIZ / "scripts" / "deploy" / "deploy.sh"
FINANCAS_SH = RAIZ / "scripts" / "deploy" / "atualizar_financas.sh"
INSTALAR_SH = RAIZ / "scripts" / "deploy" / "instalar.sh"
SYSTEMD = RAIZ / "scripts" / "systemd"
SEM_BASH = pytest.mark.skipif(shutil.which("bash") is None, reason="bash indisponível")


def _texto(caminho):
    return caminho.read_text(encoding="utf-8")


def _bloco(texto, nome):
    """O trecho entre `# >>> nome` e `# <<< nome` de um script, para rodar só ele com bash de verdade."""
    achado = re.search(rf"# >>> {nome}\n(.*?)# <<< {nome}", texto, re.DOTALL)
    assert achado, f"bloco {nome} não encontrado"
    return achado.group(1)


def _bash(script, cwd=None, env=None):
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, cwd=cwd, env={**os.environ, **(env or {})}, check=False
    )


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


# ── Deploy: carga das séries e das finanças ──────────────────────────────────────────────────────────────────────────
def test_deploy_descarta_saidas_do_cron_antes_do_merge_e_carrega_tudo_pela_carga_unica():
    texto = _texto(DEPLOY_SH)
    assert _posicao(texto, r"^\s*git checkout -q -- etl/data/processed") < _posicao(texto, r"^git merge --ff-only ")
    carga = texto[_posicao(texto, r"^\s*um_comando python -c ") :]
    assert re.search(
        r"^from etl\.pipelines\.carga_economica import carregar_tudo, chaves_do_deploy", carga, re.MULTILINE
    )
    assert _posicao(texto, r"alembic upgrade head") < _posicao(texto, r"^\s*um_comando python -c ")
    assert _posicao(texto, r"^\s*um_comando python -c ") < _posicao(texto, r"^docker compose up ")


def test_deploy_repassa_a_liberacao_de_encolhimento_vazia_por_padrao_e_tolera_so_as_financas():
    texto = _texto(DEPLOY_SH)
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :].split("\n}\n")[0]
    # a variável é repassada DENTRO de `um_comando` (não solta no script) e vazia quando o operador não a define
    assert re.search(r"-e LEGISDATA_ACEITAR_ENCOLHIMENTO=\"\$\{LEGISDATA_ACEITAR_ENCOLHIMENTO:-\}\"", corpo)
    # só as finanças são toleradas (as duas chaves delas), com qualquer espaçamento ou aspas
    tuplas = re.findall(r"toleradas\s*=\s*\(([^)]*)\)", texto)
    assert len(tuplas) == 1
    assert {x.strip().strip("'\"") for x in tuplas[0].split(",") if x.strip()} == {"financas", "financas_estaticas"}


def test_deploy_so_tolera_falha_das_financas_quando_fin_ja_tem_dados():
    """No primeiro deploy `fin` nasce vazio: tolerar a falha subiria a API sem dados e com saída 0."""
    texto = _texto(DEPLOY_SH)
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :].split("\n}\n")[0]
    assert re.search(r"-e LEGISDATA_FIN_TEM_DADOS=\"\$\{LEGISDATA_FIN_TEM_DADOS:-\}\"", corpo)
    # as DUAS tabelas precisam ter dados (uma migração que esvazia só uma conta como "sem dados" e semeia tudo)
    consulta = _posicao(
        texto,
        r"^\s*LEGISDATA_FIN_TEM_DADOS=\"\$\(docker exec politica_postgres psql .*exists\(select 1 from fin\.emenda\) and exists\(select 1 from fin\.despesa_cota\)",
    )
    assert consulta < _posicao(texto, r"^\s*um_comando python -c ")
    carga = texto[_posicao(texto, r"^\s*um_comando python -c ") :]
    assert re.search(r"os\.environ\.get\('LEGISDATA_FIN_TEM_DADOS'\) == 't' else \(\)", carga)
    assert re.search(r"carregar_tudo\(engine, chaves=chaves, toleradas=toleradas\)", carga)
    assert "chaves_do_deploy(os.environ.get('LEGISDATA_FIN_MODO', 'completa'))" in carga


def test_modo_das_financas_chega_a_carga_pelo_um_comando():
    texto = _texto(DEPLOY_SH)
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :].split("\n}\n")[0]
    assert 'LEGISDATA_FIN_MODO="${LEGISDATA_FIN_MODO:-completa}"' in corpo  # sem decisão, o padrão é semear tudo
    assert (
        'read -r LEGISDATA_FIN_MODO LEGISDATA_FIN_REFRESCAR < <(decidir_financas "$ATUAL" "$ALVO" "$LEGISDATA_FIN_TEM_DADOS")'
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


def test_dry_run_do_deploy_nao_disputa_o_lock():
    """Com a atualização das finanças segurando o lock, o dry-run do instalador sairia 0 sem testar nada."""
    texto = _texto(DEPLOY_SH)
    assert re.search(r'if \[\[ -z "\$\{_LEGISDATA_DEPLOY_REEXEC:-\}" && \$DRY_RUN -eq 0 \]\]; then\n  exec 9>', texto)


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
        "etl/pipelines/financas_loader.py": "a",
        "etl/pipelines/financas_estaticas.py": "a",
        "etl/pipelines/loader_helpers.py": "a",
        "etl/pipelines/pessoa_resolver.py": "a",
        "etl/pipelines/carga_economica.py": "a",
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


def _decidir(repo, mudanca, tem_dados="t", atual="HEAD~1"):
    """Faz um commit com `mudanca` ({caminho: conteúdo}) e devolve o que `decidir_financas` responde para ele."""
    for caminho, conteudo in mudanca.items():
        (repo / caminho).parent.mkdir(parents=True, exist_ok=True)
        (repo / caminho).write_text(conteudo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "mudança")
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    anterior = _git(repo, "rev-parse", atual) if atual else ""
    resposta = _bash(f'{funcao}\ndecidir_financas "{anterior}" "$(git rev-parse HEAD)" "{tem_dados}"', cwd=repo)
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
        ({"etl/pipelines/financas_loader.py": "b"}, "estaticas 1"),  # código da carga: estáticas e atualização diária
        ({"etl/pipelines/loader_helpers.py": "b"}, "estaticas 1"),
        ({"etl/pipelines/pessoa_resolver.py": "b"}, "estaticas 1"),
        ({"etl/pipelines/carga_economica.py": "b"}, "estaticas 0"),  # só orquestra as estáticas
        ({"etl/pipelines/financas_estaticas.py": "b"}, "estaticas 0"),
        (
            {"etl/pipelines/sync_ceap_emendas.py": "b"},
            "nenhuma 1",
        ),  # só a extração: roda a atualização, nada de estáticas
        ({"etl/pipelines/financas_atualizacao.py": "b"}, "nenhuma 1"),
        ({"etl/extractors/emendas_extractor.py": "b"}, "nenhuma 1"),
        ({"etl/utils/http_client.py": "b"}, "estaticas 1"),  # utilitário compartilhado
        ({"etl/utils/names.py": "novo"}, "estaticas 1"),  # arquivo novo em etl/utils
        ({"backend/alembic/versions/0032.py": "novo"}, "estaticas 1"),  # migração de qualquer schema
    ],
)
def test_decisao_das_financas_por_arquivo_alterado_no_commit(repo_de_decisao, mudanca, esperado):
    assert _decidir(repo_de_decisao, mudanca) == esperado


@SEM_BASH
def test_fin_sem_dados_semeia_tudo_do_git_e_pede_a_atualizacao_qualquer_que_seja_o_commit(repo_de_decisao):
    assert _decidir(repo_de_decisao, {"docs/leia-me.md": "b"}, tem_dados="f") == "completa 1"
    assert _decidir(repo_de_decisao, {}, tem_dados="") == "completa 1"


@SEM_BASH
def test_commit_anterior_desconhecido_ou_ausente_recarrega_o_que_pode_e_pede_a_atualizacao(repo_de_decisao):
    assert _decidir(repo_de_decisao, {"docs/leia-me.md": "b"}, atual=None) == "estaticas 1"  # ATUAL vazio
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    inexistente = _bash(f'{funcao}\ndecidir_financas "{"0" * 40}" HEAD t', cwd=repo_de_decisao)
    assert inexistente.stdout.strip() == "estaticas 1" and inexistente.returncode == 0


@SEM_BASH
def test_toda_entrada_da_decisao_existe_no_repositorio():
    """Um arquivo renomeado deixaria `git diff -- caminho` sempre quieto e o deploy pularia a recarga para sempre."""
    funcao = _bloco(_texto(DEPLOY_SH), "decidir_financas")
    caminhos = re.findall(r"\b((?:etl|backend)/[\w./-]+)", funcao)
    assert len(caminhos) >= 15
    for caminho in caminhos:
        assert (RAIZ / caminho).exists(), caminho


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
        + 'cat "$ENV_BANCO"; stat -c %a "$ENV_BANCO"; echo "$ENV_BANCO"'
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
    linha_do_lock = r'^\s*exec 9>"\$ESTADO_DIR/deploy\.lock"'
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
        cp "${args[i+1]}" "$REGISTRO/envfile"; stat -c %a "${args[i+1]}" >"$REGISTRO/envfile_modo"; echo "${args[i+1]}" >"$REGISTRO/envfile_caminho"
      fi
    done
    exit "${FAKE_DOCKER_RUN_RC:-0}" ;;
esac
""",
        "flock": '#!/usr/bin/env bash\necho "$*" >>"$REGISTRO/flock.log"\nexit "${FAKE_FLOCK_RC:-0}"\n',
        "git": f'#!/usr/bin/env bash\nif [[ "$*" == *"rev-parse --short=7 HEAD"* ]]; then echo "${{FAKE_HEAD}}"; else exec {git_real} "$@"; fi\n',
    }
    for nome, conteudo in scripts.items():
        (falsos / nome).write_text(conteudo)
        (falsos / nome).chmod(0o755)
    (raiz / ".env").write_text("POSTGRES_USER=usuario\nPOSTGRES_DB=banco\nPOSTGRES_PASSWORD='p@ss:w/rd#1 %'\n")
    env = {
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
@pytest.mark.parametrize("nome, valor", [("a\nb", "a\nb"), ("cr", "a\rb")])
def test_script_das_financas_recusa_senha_com_quebra_de_linha(tmp_path, nome, valor):
    resposta, chamadas, registro, raiz = _ambiente_do_script_das_financas(tmp_path)
    (raiz / ".env").write_text(f'POSTGRES_PASSWORD="{valor}"\n')
    # rodar de novo com o .env trocado
    resposta = subprocess.run(
        ["bash", str(FINANCAS_SH)],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
            "REGISTRO": str(registro),
            "LEGISDATA_DIR": str(raiz),
            "DEPLOY_STATE_DIR": str(tmp_path / "estado"),
            "FAKE_IMAGEM": "x:abc1234",
            "FAKE_HEAD": "abc1234",
        },
    )
    assert resposta.returncode == 1 and "quebra de linha" in resposta.stdout


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


def test_deploy_dispara_a_atualizacao_so_quando_a_unit_existe_e_avisa_quando_nao_existe():
    texto = _texto(DEPLOY_SH)
    final = texto[_posicao(texto, r'^echo "\$TAG" >"\$ESTADO_DIR/ultima_tag"') :]
    assert "systemctl --user cat legisdata-financas.service" in final
    assert 'if [[ "${LEGISDATA_FIN_REFRESCAR:-0}" == "1" ]]' in final
    assert "systemctl --user start --no-block legisdata-financas.service" in final
    assert "AVISO: legisdata-financas.timer não está instalado" in final


# ── instalar.sh (bash de verdade, repositório git e comandos falsos) ─────────────────────────────────────────────────
def _instalacao(tmp_path, *, tag=None, env_rc="0", timer_rc="0", previo=None):
    repo, casa, falsos, registro = tmp_path / "repo", tmp_path / "home", tmp_path / "bin", tmp_path / "registro"
    for pasta in (repo / "scripts" / "deploy", repo / "scripts" / "systemd", casa, falsos, registro):
        pasta.mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "deploy" / "deploy.sh").write_text('#!/usr/bin/env bash\necho "deploy-falso $*"\n')
    shutil.copy(FINANCAS_SH, repo / "scripts" / "deploy" / "atualizar_financas.sh")
    shutil.copy(INSTALAR_SH, repo / "scripts" / "deploy" / "instalar.sh")
    for unit in SYSTEMD.glob("legisdata-*"):
        shutil.copy(unit, repo / "scripts" / "systemd" / unit.name)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "primeiro")
    sha = _git(repo, "rev-parse", "HEAD")
    comandos = {
        "docker": '#!/usr/bin/env bash\necho "docker $*" >>"$REGISTRO/chamadas.log"\n[[ "$1" == inspect ]] && echo "ghcr.io/x/legisdata-backend:${FAKE_TAG}"\nexit 0\n',
        "systemctl": '#!/usr/bin/env bash\necho "systemctl $*" >>"$REGISTRO/chamadas.log"\n'
        'case "$2" in show-environment) exit "${FAKE_ENV_RC}" ;; is-enabled|is-active) exit "${FAKE_TIMER_RC}" ;; esac\nexit 0\n',
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
        }
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


def test_instalador_checa_o_systemd_antes_de_gravar_qualquer_coisa():
    texto = _texto(INSTALAR_SH)
    assert _posicao(texto, r"systemctl --user show-environment") < _posicao(texto, r"^mkdir -p ")
    assert _posicao(texto, r"^mkdir -p ") < _posicao(texto, r"^docker rm -f politica_watchtower")
