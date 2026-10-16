"""Os scripts de deploy precisam ao menos ter sintaxe válida: um erro de shell só apareceria no servidor."""

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


def test_deploy_descarta_saidas_do_cron_e_se_atualiza_antes_do_merge():
    texto = (RAIZ / "scripts" / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    assert texto.index("DEPLOY_REEXEC=1 exec") < texto.index("docker exec politica_postgres pg_dump")  # reexecuta antes de tocar no banco
    assert texto.index("git checkout -q -- etl/data/processed") < texto.index("git merge --ff-only")
    assert "composicao_loader" in texto and "pnad_loader" in texto
