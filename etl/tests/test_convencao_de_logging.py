"""`logging.basicConfig` é do entrypoint (.claude/rules/etl.md): nunca no nível de um módulo que outros importam."""

import ast
from pathlib import Path

import pytest

ETL = Path(__file__).resolve().parents[1]
MODULOS = sorted(p for p in ETL.rglob("*.py") if "tests" not in p.relative_to(ETL).parts and "venv" not in p.parts)


def _chama_basic_config(no):
    return isinstance(no, ast.Call) and getattr(no.func, "attr", "") == "basicConfig"


@pytest.mark.parametrize("arquivo", MODULOS, ids=lambda p: p.relative_to(ETL).as_posix())
def test_nenhum_modulo_configura_o_logging_ao_ser_importado(arquivo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.If):  # `if __name__ == "__main__":` é entrypoint
            continue
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        assert not any(_chama_basic_config(sub) for sub in ast.walk(no)), f"{arquivo.name}: basicConfig no módulo"


def test_ha_modulos_para_varrer():
    assert len(MODULOS) > 30
