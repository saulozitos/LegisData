"""`logging.basicConfig` é do entrypoint (.claude/rules/etl.md): nunca no nível de um módulo que outros importam (nem por
uma função chamada no nível do módulo), e todo entrypoint (`if __name__ == "__main__"`) configura o próprio log."""

import ast
from pathlib import Path

import pytest

ETL = Path(__file__).resolve().parents[1]
MODULOS = sorted(p for p in ETL.rglob("*.py") if "tests" not in p.relative_to(ETL).parts and "venv" not in p.parts)
# Entrypoints que só repassam para a `main()` de outro módulo, a qual configura o log (conferido por teste abaixo)
DELEGAM = {"sync_ceap_emendas_2019_2026.py", "sync_ceap_emendas_lula_bolsonaro.py"}
CONFIGURADORES = {"basicConfig", "dictConfig", "fileConfig"}


def _configura_log(no) -> bool:
    if not isinstance(no, ast.Call):
        return False
    f = no.func
    nome = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
    return nome in CONFIGURADORES


def _e_main(no) -> bool:
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


def _violacoes(arvore: ast.Module) -> list:
    """Configurações de log executadas ao IMPORTAR o módulo: direto no nível do módulo ou por função chamada nele."""
    funcoes = {n.name: n for n in arvore.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    achados = []
    for no in arvore.body:
        if _e_main(no) or isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(no):
            if _configura_log(sub):
                achados.append(("direto", sub.lineno))
            elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id in funcoes:
                if any(_configura_log(x) for x in ast.walk(funcoes[sub.func.id])):
                    achados.append((f"via {sub.func.id}()", sub.lineno))
    return achados


@pytest.mark.parametrize("arquivo", MODULOS, ids=lambda p: p.relative_to(ETL).as_posix())
def test_nenhum_modulo_configura_o_logging_ao_ser_importado(arquivo):
    assert _violacoes(ast.parse(arquivo.read_text(encoding="utf-8"))) == [], arquivo.name


@pytest.mark.parametrize("arquivo", MODULOS, ids=lambda p: p.relative_to(ETL).as_posix())
def test_todo_entrypoint_configura_o_proprio_log(arquivo):
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    mains = [no for no in arvore.body if _e_main(no)]
    if not mains or arquivo.name in DELEGAM:
        pytest.skip("não é entrypoint (ou delega a um que configura)")
    donos = mains + [no for no in arvore.body if isinstance(no, ast.FunctionDef) and no.name == "main"]
    assert any(_configura_log(sub) for no in donos for sub in ast.walk(no)), f"{arquivo.name}: __main__ sem log"


@pytest.mark.parametrize("nome", sorted(DELEGAM))
def test_quem_delega_chama_de_fato_a_main_que_configura_o_log(nome):
    texto = next(p for p in MODULOS if p.name == nome).read_text(encoding="utf-8")
    assert "sync_ceap_emendas import" in texto and "main" in texto, nome
    main_do_sync = ast.parse((ETL / "pipelines" / "sync_ceap_emendas.py").read_text(encoding="utf-8"))
    [main] = [n for n in main_do_sync.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert any(_configura_log(sub) for sub in ast.walk(main))


@pytest.mark.parametrize(
    "codigo, esperado",
    [
        ("import logging\nlogging.basicConfig()\n", 1),
        ("from logging import basicConfig\nbasicConfig()\n", 1),
        ("import logging.config\nlogging.config.dictConfig({})\n", 1),
        ("if not x:\n    logging.basicConfig()\n", 1),
        ("def _setup():\n    logging.basicConfig()\n_setup()\n", 1),  # função chamada no nível do módulo
        ("def main():\n    logging.basicConfig()\nif __name__ == '__main__':\n    main()\n", 0),
        ("import logging\nlogger = logging.getLogger('x')\n", 0),
    ],
)
def test_a_varredura_enxerga_as_formas_de_configurar_o_log_no_import(codigo, esperado):
    """O auto-teste usa a MESMA função dos testes reais: uma regressão no filtro derruba este teste."""
    assert len(_violacoes(ast.parse(codigo))) == esperado


def test_ha_modulos_para_varrer():
    assert len(MODULOS) > 30
