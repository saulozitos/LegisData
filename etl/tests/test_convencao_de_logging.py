"""`logging.basicConfig` é do entrypoint (.claude/rules/etl.md): nunca no nível de um módulo que outros importam, e todo
entrypoint (`if __name__ == "__main__"`) configura o próprio log."""

import ast
from pathlib import Path

import pytest

ETL = Path(__file__).resolve().parents[1]
MODULOS = sorted(p for p in ETL.rglob("*.py") if "tests" not in p.relative_to(ETL).parts and "venv" not in p.parts)
# Entrypoints que só repassam para a `main()` de outro módulo, a qual configura o log
DELEGAM = {"sync_ceap_emendas_2019_2026.py", "sync_ceap_emendas_lula_bolsonaro.py"}


def _chama_basic_config(no):
    if not isinstance(no, ast.Call):
        return False
    f = no.func
    return (isinstance(f, ast.Attribute) and f.attr == "basicConfig") or (
        isinstance(f, ast.Name) and f.id == "basicConfig"
    )


def _e_main(no):
    """`if __name__ == "__main__":`, e só ele (outro `if` no nível do módulo conta como código de importação)."""
    t = no.test if isinstance(no, ast.If) else None
    return (
        isinstance(t, ast.Compare)
        and isinstance(t.left, ast.Name)
        and t.left.id == "__name__"
        and len(t.ops) == 1
        and isinstance(t.ops[0], ast.Eq)
        and isinstance(t.comparators[0], ast.Constant)
        and t.comparators[0].value == "__main__"
    )


@pytest.mark.parametrize("arquivo", MODULOS, ids=lambda p: p.relative_to(ETL).as_posix())
def test_nenhum_modulo_configura_o_logging_ao_ser_importado(arquivo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in arvore.body:
        if _e_main(no) or isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        assert not any(_chama_basic_config(sub) for sub in ast.walk(no)), f"{arquivo.name}: basicConfig no módulo"


@pytest.mark.parametrize("arquivo", MODULOS, ids=lambda p: p.relative_to(ETL).as_posix())
def test_todo_entrypoint_configura_o_proprio_log(arquivo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    mains = [no for no in arvore.body if _e_main(no)]
    if not mains or arquivo.name in DELEGAM:
        pytest.skip("não é entrypoint (ou delega a um que configura)")
    donos = mains + [no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == "main"]
    assert any(_chama_basic_config(sub) for no in donos for sub in ast.walk(no)), f"{arquivo.name}: __main__ sem log"


def test_a_varredura_enxerga_if_que_nao_e_main_e_import_de_basic_config():
    ruim = ast.parse("if not x:\n    logging.basicConfig()\nfrom logging import basicConfig\nbasicConfig()\n")
    achados = [no for no in ruim.body if not _e_main(no) and any(_chama_basic_config(s) for s in ast.walk(no))]
    assert len(achados) == 2


def test_ha_modulos_para_varrer():
    assert len(MODULOS) > 30
