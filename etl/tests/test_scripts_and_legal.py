"""Scripts de saneamento e cargas sintéticas de presença/remuneração."""

from datetime import date

import pytest

from etl.pipelines import stg_tabela
from etl.scripts.diagnose_anomalies import nome_aparece
from etl.scripts.fix_author_associations import sanitize_all_proposition_authors
from etl.utils.copia import transacao_de_carga

LIMPAR = "TRUNCATE stg.votos_parlamentares, stg.sessoes_votacao, stg.proposicoes, stg.politicos CASCADE"


@pytest.fixture
def staging(pg_engine):
    """O staging limpo antes e depois: o saneamento lê e grava `stg.politicos` e `stg.proposicoes`."""
    from sqlalchemy import text

    with pg_engine.begin() as conn:
        conn.execute(text(LIMPAR))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text(LIMPAR))


def politico(tabela, eleitoral, civil=None):
    return tabela.nova(civil_name=civil or eleitoral, electoral_name=eleitoral)


def proposicao(tabela, numero, autor_nome, autor_id):
    return tabela.nova(
        proposition_type="PL",
        number=numero,
        year=2023,
        title=f"PL {numero}/2023",
        summary="x",
        presentation_date=date(2023, 1, 1),
        author_name=autor_nome,
        author_politician_id=autor_id,
    )


def _autor(engine, identificador):
    with transacao_de_carga(engine) as cursor:
        return next(p.author_politician_id for p in stg_tabela.proposicoes().carregar(cursor) if p.id == identificador)


def _sanear(engine, apply):
    with transacao_de_carga(engine) as cursor:
        resultado = sanitize_all_proposition_authors(cursor, apply=apply)
        if not apply:
            cursor.connection.rollback()  # simulação: nada fica
    return resultado


def test_saneamento_reatribui_falso_positivo_sem_remover_vinculo_correto(staging):
    pessoas, props = stg_tabela.politicos(), stg_tabela.proposicoes()
    edu = politico(pessoas, "Eduardo Bolsonaro", "Eduardo Nantes Bolsonaro")
    dino = politico(pessoas, "Flávio Dino")
    joao = politico(pessoas, "João da Silva")
    errada = proposicao(props, 1, "Flávio Dino", edu.id)  # vínculo errado (caso clássico)
    certa = proposicao(props, 2, "Joao da Silva", joao.id)  # sem acento na fonte: antes o vínculo era APAGADO
    sem_pessoa = proposicao(props, 3, "Poder Executivo", edu.id)
    desconhecida = proposicao(props, 4, "Maria Qualquer", edu.id)  # nada em comum com o político atual
    coautor = proposicao(props, 5, "Eduardo Bolsonaro, Flávio Dino", edu.id)  # primeiro signatário correto
    with transacao_de_carga(staging) as cursor:
        pessoas.gravar(cursor)
        props.gravar(cursor)

    # Padrão: simulação, nada é gravado
    resultado = _sanear(staging, apply=False)
    assert resultado["reatribuidos"] == 1 and resultado["desvinculados"] == 2
    assert _autor(staging, errada.id) == edu.id

    _sanear(staging, apply=True)
    assert _autor(staging, errada.id) == dino.id
    assert _autor(staging, certa.id) == joao.id
    assert _autor(staging, sem_pessoa.id) is None
    assert _autor(staging, desconhecida.id) is None
    assert _autor(staging, coautor.id) == edu.id


def test_saneamento_tolera_nomes_nulos(staging):
    pessoas, props = stg_tabela.politicos(), stg_tabela.proposicoes()
    p = politico(pessoas, "Fulano")
    proposicao(props, 1, None, p.id)
    with transacao_de_carga(staging) as cursor:
        pessoas.gravar(cursor)
        props.gravar(cursor)
    assert _sanear(staging, apply=True)["total_analisado"] == 1


def test_diagnostico_ignora_nome_vazio_e_acentos():
    assert nome_aparece("Flávio Dino", "Flavio Dino (PSB/MA)")
    assert not nome_aparece("", "Qualquer")  # antes `"" in texto` era sempre True
    # O diagnóstico é deliberadamente MAIS permissivo que o loader (subconjunto de tokens): serve para listar
    # suspeitos, não para decidir vínculos. O vínculo em si é decidido pelo AuthorResolver (igualdade exata).
    assert nome_aparece("Dr. Flávio", "Flávio Dino")
    assert not nome_aparece("Eduardo Bolsonaro", "Flávio Dino")
