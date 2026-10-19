"""Os scripts de deploy precisam ao menos ter sintaxe válida: um erro de shell só apareceria no servidor."""

import re
import shutil
import subprocess
from pathlib import Path

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


def test_deploy_descarta_saidas_do_cron_antes_do_merge_e_carrega_tudo_pela_carga_unica():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert _posicao(texto, r"^\s*git checkout -q -- etl/data/processed") < _posicao(texto, r"^git merge --ff-only ")
    carga = texto[_posicao(texto, r"^\s*um_comando python -c ") :]
    assert re.search(r"^from etl\.pipelines\.carga_economica import CARGAS, carregar_tudo", carga, re.MULTILINE)
    assert _posicao(texto, r"alembic upgrade head") < _posicao(texto, r"^\s*um_comando python -c ")
    assert _posicao(texto, r"^\s*um_comando python -c ") < _posicao(texto, r"^docker compose up ")


def test_deploy_repassa_a_liberacao_de_encolhimento_vazia_por_padrao_e_tolera_so_as_financas():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    inicio = _posicao(texto, r"^um_comando\(\) \{")
    corpo = texto[inicio : inicio + texto[inicio:].index("\n}\n")]
    # a variável é repassada DENTRO de `um_comando` (não solta no script) e vazia quando o operador não a define
    assert re.search(r"-e LEGISDATA_ACEITAR_ENCOLHIMENTO=\"\$\{LEGISDATA_ACEITAR_ENCOLHIMENTO:-\}\"", corpo)
    # só as finanças são toleradas, com qualquer espaçamento ou aspas: a tupla inteira tem de ser ("financas",)
    tuplas = re.findall(r"toleradas\s*=\s*\(([^)]*)\)", texto)
    assert len(tuplas) == 1
    assert [x.strip().strip("'\"") for x in tuplas[0].split(",") if x.strip()] == ["financas"]


def test_deploy_so_tolera_falha_das_financas_quando_fin_ja_tem_dados():
    """No primeiro deploy `fin` nasce vazio: tolerar a falha subiria a API sem dados e com saída 0."""
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    inicio = _posicao(texto, r"^um_comando\(\) \{")
    corpo = texto[inicio : inicio + texto[inicio:].index("\n}\n")]
    assert re.search(r"-e LEGISDATA_FIN_TEM_DADOS=\"\$\{LEGISDATA_FIN_TEM_DADOS:-\}\"", corpo)
    consulta = _posicao(
        texto, r"^\s*LEGISDATA_FIN_TEM_DADOS=\"\$\(docker exec politica_postgres psql .*exists\(select 1 from fin\."
    )
    assert consulta < _posicao(texto, r"^\s*um_comando python -c ")
    carga = texto[_posicao(texto, r"^\s*um_comando python -c ") :]
    assert re.search(r"os\.environ\.get\('LEGISDATA_FIN_TEM_DADOS'\) == 't' else \(\)", carga)
    assert re.search(r"carregar_tudo\(engine, chaves=chaves, toleradas=toleradas\)", carga)


def test_rollback_do_deploy_sobe_a_tag_anterior_com_o_compose_do_commit_anterior():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    guardado = _posicao(texto, r'^COMMIT_ANTERIOR="\$\(git rev-parse HEAD\)"')
    assert guardado < _posicao(texto, r"^git merge --ff-only ")
    rollback = texto[_posicao(texto, r'if \[\[ "\$estado" != "healthy" \]\]') :]
    assert re.search(r'git show "\$COMMIT_ANTERIOR:docker-compose\.yml"', rollback)
    assert re.search(r'IMAGE_TAG="\$ANTERIOR" docker compose --project-directory "\$RAIZ" -f ', rollback)


# ── Atualização diária das finanças (timer de usuário) ─────────────────────────────────────────────────────────────────
FINANCAS_SH = RAIZ / "scripts" / "deploy" / "atualizar_financas.sh"
SYSTEMD = RAIZ / "scripts" / "systemd"


def test_atualizacao_diaria_espera_o_lock_do_deploy_e_nao_deixa_o_lock_no_conteiner():
    texto = FINANCAS_SH.read_text(encoding="utf-8")
    # o mesmo arquivo de lock do deploy, no descritor 9, esperando em vez de pular (o deploy é quem pula e tenta de novo)
    assert re.search(r'^exec 9>"\$ESTADO_DIR/deploy\.lock"', texto, re.MULTILINE)
    assert re.search(r"^flock -w \d+ 9 \|\|", texto, re.MULTILINE)
    assert re.search(r"financas_atualizacao 9>&-\s*$", texto, re.MULTILINE)  # o contêiner não herda o lock


def test_atualizacao_diaria_monta_o_checkout_so_leitura_e_apenas_etl_data_gravavel():
    texto = FINANCAS_SH.read_text(encoding="utf-8")
    assert '-v "$RAIZ:/repo:ro"' in texto and '-v "$RAIZ/etl/data:/repo/etl/data"' in texto
    assert '--user "$(id -u):$(id -g)"' in texto  # os arquivos gravados ficam do dono do checkout
    assert "python -m etl.pipelines.financas_atualizacao" in texto
    assert re.search(r"--memory \d+g", texto)  # a extração não pode derrubar o servidor


def test_atualizacao_diaria_passa_a_senha_do_banco_por_arquivo_de_ambiente():
    texto = FINANCAS_SH.read_text(encoding="utf-8")
    assert not re.search(r"-e (ALEMBIC_)?DATABASE_URL=", texto) and "POSTGRES_PASSWORD" in texto
    assert re.search(r'chmod 600 "\$ENV_BANCO"', texto) and '--env-file "$ENV_BANCO"' in texto
    assert re.search(r"trap 'rm -f \"\$ENV_BANCO\"' EXIT", texto)


def test_units_da_atualizacao_diaria_sao_de_usuario_e_nao_guardam_caminho_do_servidor():
    servico = (SYSTEMD / "legisdata-financas.service").read_text(encoding="utf-8")
    timer = (SYSTEMD / "legisdata-financas.timer").read_text(encoding="utf-8")
    assert "EnvironmentFile=%h/.legisdata-deploy/ambiente" in servico
    assert "ExecStart=%h/.legisdata-deploy/atualizar_financas.sh" in servico
    assert re.search(r"^OnCalendar=\*-\*-\* \d\d:\d\d:\d\d$", timer, re.MULTILINE)
    assert "Persistent=true" in timer and "WantedBy=timers.target" in timer
    for texto in (servico, timer, FINANCAS_SH.read_text(encoding="utf-8")):
        assert not re.search(r"/home/|/opt/|umbrel|\b\d{1,3}(\.\d{1,3}){3}\b", texto)  # nada do servidor no repositório


def test_instalador_instala_a_atualizacao_diaria_e_liga_o_timer():
    texto = (RAIZ / "scripts" / "deploy" / "instalar.sh").read_text(encoding="utf-8")
    assert 'scripts/deploy/atualizar_financas.sh" >"$DEST/atualizar_financas.sh"' in texto
    for unit in ("legisdata-financas.service", "legisdata-financas.timer"):
        assert unit in texto
    assert "systemctl --user enable --now legisdata-financas.timer" in texto


def test_deploy_mantem_a_copia_do_script_da_atualizacao_igual_a_do_commit_implantado():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    instalacao = _posicao(texto, r'install -m 755 "\$RAIZ/scripts/deploy/atualizar_financas\.sh"')
    assert instalacao < _posicao(texto, r'^echo "\$TAG" >"\$ESTADO_DIR/ultima_tag"')  # só depois da saúde
    assert re.search(
        r'bash -n "\$RAIZ/scripts/deploy/atualizar_financas\.sh"', texto
    )  # script com erro nunca é instalado


def test_deploy_so_recarrega_as_financas_quando_o_commit_mudou_os_arquivos_ou_o_codigo_da_carga():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    inicio = _posicao(texto, r"^\s*ENTRADAS_FINANCAS=\(")
    entradas = texto[inicio : inicio + texto[inicio:].index("\n  )\n")]
    for caminho in (
        "despesas_ceap_2019_2026.json",
        "emendas_parlamentares_2019_2026.json",
        "remuneracao_parlamentares.json",
        "declaracoes_patrimonio.json",
        "tse_doacoes_campanha.json",
        "certidoes_tse.json",
        "financas_loader.py",
        "loader_helpers.py",
        "pessoa_resolver.py",
        "backend/alembic/versions",
    ):
        assert caminho in entradas, caminho
    # só pula com o `fin` já carregado e o commit anterior conhecido, comparando commit contra commit
    assert re.search(r'\[\[ "\$LEGISDATA_FIN_TEM_DADOS" == "t" && -n "\$ATUAL" \]\]', texto)
    assert re.search(r'git diff --quiet "\$ATUAL" "\$ALVO" -- "\$\{ENTRADAS_FINANCAS\[@\]\}"', texto)
    # a decisão chega à carga: as chaves excluem `financas` só com o pulo, e a variável é repassada pelo `um_comando`
    corpo = texto[_posicao(texto, r"^um_comando\(\) \{") :]
    assert 'LEGISDATA_FIN_PULAR="${LEGISDATA_FIN_PULAR:-}"' in corpo.split("\n}\n")[0]
    assert re.search(r"carregar_tudo\(engine, chaves=chaves, toleradas=toleradas\)", texto)
    assert "os.environ.get('LEGISDATA_FIN_PULAR') == '1'" in texto
