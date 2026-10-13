"""Scripts de saneamento, carga de processos (gated) e cargas sintéticas de presença/remuneração."""

from datetime import date

import pytest
from app.models import (
    Base,
    Politician,
    ProcessoJudicial,
    Proposition,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.extractors.processos_loader import chave_registro, populate_processos_judiciais
from etl.scripts.diagnose_anomalies import nome_aparece
from etl.scripts.fix_author_associations import sanitize_all_proposition_authors


@pytest.fixture
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as s:
        yield s


def politico(s, eleitoral, civil=None):
    p = Politician(civil_name=civil or eleitoral, electoral_name=eleitoral)
    s.add(p)
    s.flush()
    return p


def proposicao(s, numero, autor_nome, autor_id):
    pr = Proposition(
        proposition_type="PL",
        number=numero,
        year=2023,
        title=f"PL {numero}/2023",
        summary="x",
        presentation_date=date(2023, 1, 1),
        author_name=autor_nome,
        author_politician_id=autor_id,
    )
    s.add(pr)
    s.flush()
    return pr


def test_saneamento_reatribui_falso_positivo_sem_remover_vinculo_correto(sessao):
    edu = politico(sessao, "Eduardo Bolsonaro", "Eduardo Nantes Bolsonaro")
    dino = politico(sessao, "Flávio Dino")
    joao = politico(sessao, "João da Silva")
    errada = proposicao(sessao, 1, "Flávio Dino", edu.id)  # vínculo errado (caso clássico)
    certa = proposicao(sessao, 2, "Joao da Silva", joao.id)  # sem acento na fonte: antes o vínculo era APAGADO
    sem_pessoa = proposicao(sessao, 3, "Poder Executivo", edu.id)
    desconhecida = proposicao(sessao, 4, "Maria Qualquer", edu.id)  # nada em comum com o político atual
    coautor = proposicao(sessao, 5, "Eduardo Bolsonaro, Flávio Dino", edu.id)  # primeiro signatário correto
    sessao.commit()

    # Padrão: simulação, nada é gravado
    resultado = sanitize_all_proposition_authors(sessao, apply=False)
    assert resultado["reatribuidos"] == 1 and resultado["desvinculados"] == 2
    sessao.expire_all()
    assert sessao.get(Proposition, errada.id).author_politician_id == edu.id

    sanitize_all_proposition_authors(sessao, apply=True)
    sessao.expire_all()
    assert sessao.get(Proposition, errada.id).author_politician_id == dino.id
    assert sessao.get(Proposition, certa.id).author_politician_id == joao.id
    assert sessao.get(Proposition, sem_pessoa.id).author_politician_id is None
    assert sessao.get(Proposition, desconhecida.id).author_politician_id is None
    assert sessao.get(Proposition, coautor.id).author_politician_id == edu.id


def test_saneamento_tolera_nomes_nulos(sessao):
    p = Politician(civil_name="Fulano", electoral_name="Fulano")
    sessao.add(p)
    sessao.flush()
    proposicao(sessao, 1, None, p.id)
    sessao.commit()
    assert sanitize_all_proposition_authors(sessao, apply=True)["total_analisado"] == 1


def test_diagnostico_ignora_nome_vazio_e_acentos():
    assert nome_aparece("Flávio Dino", "Flavio Dino (PSB/MA)")
    assert not nome_aparece("", "Qualquer")  # antes `"" in texto` era sempre True
    # O diagnóstico é deliberadamente MAIS permissivo que o loader (subconjunto de tokens): serve para listar
    # suspeitos, não para decidir vínculos. O vínculo em si é decidido pelo AuthorResolver (igualdade exata).
    assert nome_aparece("Dr. Flávio", "Flávio Dino")
    assert not nome_aparece("Eduardo Bolsonaro", "Flávio Dino")


def test_chave_registro_por_igualdade_exata():
    assert chave_registro("Lula (Lula 3)", "Luiz Inácio Lula da Silva") == "lula"
    assert chave_registro("Lula da Fonte", "Lula da Fonte") is None
    assert chave_registro("Eduardo Bolsonaro", None) == "eduardo_bolsonaro"
    assert chave_registro("Moroni", "Moroni da Silva") is None  # "moro" in "moroni" não casa mais
    assert chave_registro("Jairo Souza", None) is None


def test_processos_so_com_autorizacao_explicita(sessao):
    politico(sessao, "Jair Bolsonaro", "Jair Messias Bolsonaro")
    sessao.commit()
    assert populate_processos_judiciais(sessao) == 0
    assert sessao.query(ProcessoJudicial).count() == 0
    inseridos = populate_processos_judiciais(sessao, allow_unverified=True)
    assert inseridos > 0
    # idempotente: segunda execução substitui os do político, não duplica
    assert populate_processos_judiciais(sessao, allow_unverified=True) == inseridos
    assert sessao.query(ProcessoJudicial).count() == inseridos
