"""`logging.basicConfig` é do entrypoint (.claude/rules/etl.md): nunca no nível de um módulo que outros importam (nem por
uma função chamada no nível do módulo), e todo entrypoint (`if __name__ == "__main__"`) configura o próprio log."""

import ast
from pathlib import Path
from typing import Optional

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


def _funcoes_de(arvore: ast.AST) -> dict:
    return {n.name: n for n in arvore.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _importadas(arvore: ast.Module) -> dict:
    """Nome local => (função, módulo etl.* de onde veio) das importações `from etl... import f` do módulo."""
    return {
        (a.asname or a.name): (a.name, n.module)
        for n in arvore.body
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "etl" and n.level == 0
        for a in n.names
    }


def _configura_transitivamente(
    nome: str, funcoes: dict, vistos: set, importadas: Optional[dict] = None, modulo_atual: str = ""
) -> bool:
    """A função `nome` configura o log, direto, por outra função do módulo ou por uma função importada de `etl.*`."""
    if (modulo_atual, nome) in vistos:
        return False
    vistos.add((modulo_atual, nome))
    if nome not in funcoes and importadas and nome in importadas:
        original, modulo = importadas[nome]
        caminho = ETL.parent.joinpath(*modulo.split(".")).with_suffix(".py")
        if not caminho.is_file():
            return False
        alvo = ast.parse(caminho.read_text(encoding="utf-8"))
        return _configura_transitivamente(original, _funcoes_de(alvo), vistos, _importadas(alvo), modulo)
    if nome not in funcoes:
        return False
    for sub in ast.walk(funcoes[nome]):
        if _configura_log(sub):
            return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            if _configura_transitivamente(sub.func.id, funcoes, vistos, importadas, modulo_atual):
                return True
    return False


def _violacoes(arvore: ast.Module) -> list:
    """
    Configurações de log executadas ao IMPORTAR o módulo: direto no nível do módulo, no corpo de uma classe (que roda no
    import), ou por uma função chamada no nível do módulo (do próprio módulo ou importada de `etl.*`), com fecho transitivo.
    """
    funcoes, importadas = _funcoes_de(arvore), _importadas(arvore)
    achados = []

    def codigo_de_import(no):
        """Os nós que rodam ao importar: tudo fora de `def` (o corpo de classe roda; o de função não)."""
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        yield no
        for filho in ast.iter_child_nodes(no):
            yield from codigo_de_import(filho)

    for no in arvore.body:
        if _e_main(no) or isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in codigo_de_import(no):
            if _configura_log(sub):
                achados.append(("direto", sub.lineno))
            elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if _configura_transitivamente(sub.func.id, funcoes, set(), importadas):
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
    arvore = ast.parse(next(p for p in MODULOS if p.name == nome).read_text(encoding="utf-8"))
    importa_main = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "etl.pipelines.sync_ceap_emendas"
        and any(a.name == "main" for a in n.names)
        for n in ast.walk(arvore)
    )
    chama_a_main = any(
        isinstance(c, ast.Call) and getattr(c.func, "id", "") in ("main", "_main")
        for n in arvore.body
        for c in ast.walk(n)
    ) and any(_e_main(n) for n in arvore.body)
    assert importa_main and chama_a_main, nome
    sync = ast.parse((ETL / "pipelines" / "sync_ceap_emendas.py").read_text(encoding="utf-8"))
    [main] = [n for n in sync.body if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert any(_configura_log(sub) for sub in ast.walk(main))


@pytest.mark.parametrize(
    "codigo, esperado",
    [
        ("import logging\nlogging.basicConfig()\n", 1),
        ("from logging import basicConfig\nbasicConfig()\n", 1),
        ("import logging.config\nlogging.config.dictConfig({})\n", 1),
        ("if not x:\n    logging.basicConfig()\n", 1),
        ("def _setup():\n    logging.basicConfig()\n_setup()\n", 1),  # função chamada no nível do módulo
        ("def _a():\n    logging.basicConfig()\ndef _b():\n    _a()\n_b()\n", 1),  # e por um helper do helper
        ("class Cfg:\n    logging.basicConfig()\n", 1),  # o corpo de uma classe roda no import
        ("class Cfg:\n    def setup(self):\n        logging.basicConfig()\n", 0),  # um método só quando chamado
        (
            "from etl.pipelines.sync_ceap_emendas import main\nmain()\n",
            1,
        ),  # função importada de etl.* que configura o log
        ("def main():\n    logging.basicConfig()\nif __name__ == '__main__':\n    main()\n", 0),
        ("import logging\nlogger = logging.getLogger('x')\n", 0),
    ],
)
def test_a_varredura_enxerga_as_formas_de_configurar_o_log_no_import(codigo, esperado):
    """O auto-teste usa a MESMA função dos testes reais: uma regressão no filtro derruba este teste."""
    assert len(_violacoes(ast.parse(codigo))) == esperado


def test_ha_modulos_para_varrer():
    assert len(MODULOS) > 30
