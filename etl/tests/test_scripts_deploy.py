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
    assert re.search(r"^from etl\.pipelines\.carga_economica import carregar_tudo", carga, re.MULTILINE)
    assert _posicao(texto, r"alembic upgrade head") < _posicao(texto, r"^\s*um_comando python -c ")
    assert _posicao(texto, r"^\s*um_comando python -c ") < _posicao(texto, r"^docker compose up ")


def test_deploy_repassa_a_liberacao_de_encolhimento_vazia_por_padrao_e_tolera_so_as_financas():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    inicio = _posicao(texto, r"^um_comando\(\) \{")
    corpo = texto[inicio : inicio + texto[inicio:].index("\n}\n")]
    # a variável é repassada DENTRO de `um_comando` (não solta no script) e vazia quando o operador não a define
    assert re.search(r"-e LEGISDATA_ACEITAR_ENCOLHIMENTO=\"\$\{LEGISDATA_ACEITAR_ENCOLHIMENTO:-\}\"", corpo)
    # só as finanças são toleradas, com qualquer espaçamento ou aspas
    assert re.search(r"toleradas\s*=\s*\(\s*['\"]financas['\"]\s*,?\s*\)", texto)
    assert not re.search(r"toleradas\s*=\s*\([^)]*['\"](series|presidencia|composicao|pnad)['\"]", texto)
