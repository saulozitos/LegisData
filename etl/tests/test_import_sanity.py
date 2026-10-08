"""Sanidade de import: nenhum módulo do ETL pode referenciar nome indefinido (regressão do NameError `Optional`)."""

import importlib
from pathlib import Path

import pytest

ETL_DIR = Path(__file__).resolve().parents[1]


def modulos_etl():
    """Todo .py do ETL (exceto testes e dados) como nome de módulo; `etl` é pacote-namespace, então varre o disco."""
    for arquivo in sorted(ETL_DIR.rglob("*.py")):
        partes = arquivo.relative_to(ETL_DIR).with_suffix("").parts
        if partes[0] in ("tests", "data") or partes[-1] == "__init__":
            continue
        yield ".".join(("etl",) + partes)


@pytest.mark.parametrize("nome", sorted(modulos_etl()))
def test_modulo_importa(nome):
    importlib.import_module(nome)


def test_db_loader_importa_e_expoe_api_publica():
    db_loader = importlib.import_module("etl.pipelines.db_loader")
    assert hasattr(db_loader, "DatabaseLoader")
    for metodo in (
        "load_all",
        "_load_political_parties",
        "_load_politicians",
        "_load_party_affiliations",
        "_load_mandates",
        "_load_propositions",
        "_load_voting_sessions_and_votes",
        "_load_ceap_expenses",
        "_load_emendas_parlamentares",
    ):
        assert callable(getattr(db_loader.DatabaseLoader, metodo))


def test_nenhum_nome_indefinido_nos_fontes():
    pyflakes_api = pytest.importorskip("pyflakes.api")
    import io

    from pyflakes.reporter import Reporter

    problemas = []
    for arquivo in ETL_DIR.rglob("*.py"):
        if "data" in arquivo.relative_to(ETL_DIR).parts:
            continue
        saida = io.StringIO()
        pyflakes_api.checkPath(str(arquivo), Reporter(saida, saida))
        problemas += [linha for linha in saida.getvalue().splitlines() if "undefined name" in linha]
    assert problemas == []
