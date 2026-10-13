"""Funções puras da carga: autores, partidos, datas, contatos inventados e classificação."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from etl.pipelines.loader_helpers import (
    AuthorResolver,
    _dec,
    _to_date,
    classify_proposition_impact,
    legislatura_datas,
    limpar_contatos_inventados,
    resolve_party_id,
)


def pol(ident, eleitoral, civil=None):
    return SimpleNamespace(id=ident, electoral_name=eleitoral, civil_name=civil or eleitoral)


@pytest.fixture
def resolver():
    politicos = [
        pol("edu", "Eduardo Bolsonaro", "Eduardo Nantes Bolsonaro"),
        pol("dino", "Flávio Dino", "Flávio Dino de Castro e Costa"),
        pol("drflavio", "Dr. Flávio", "Flávio Cesar Souza"),
        pol("ana1", "Ana Souza"),
        pol("ana2", "Ana Souza"),
        pol("gil", "Gil Diniz"),
        pol("gilmar", "Gil"),
    ]
    return AuthorResolver(politicos, deputy_map={10: "dep10"}, senator_map={20: "sen20"})


def test_resolve_por_id_oficial_tem_prioridade(resolver):
    assert resolver.resolve("Qualquer Nome", camara_id=10) == "dep10"
    assert resolver.resolve("Qualquer Nome", senado_id=20) == "sen20"


def test_flavio_dino_nao_vira_flavio_nem_eduardo(resolver):
    """Regressão do caso Eduardo Bolsonaro: colisão de tokens atribuía autores errados."""
    assert resolver.resolve("Flávio Dino") == "dino"
    assert resolver.resolve("Senador Flávio Dino (PSB/MA)") == "dino"
    assert resolver.resolve("Eduardo Bolsonaro") == "edu"
    assert resolver.resolve("Flavio Bolsonaro") is None  # não existe na base: nunca o "mais parecido"


def test_gil_diniz_nao_casa_com_gil(resolver):
    assert resolver.resolve("Gil Diniz") == "gil"
    assert resolver.resolve("Gil") == "gilmar"


def test_homonimos_resolvem_para_none(resolver):
    assert resolver.resolve("Ana Souza") is None


def test_autores_que_nao_sao_pessoas_ou_vazios(resolver):
    assert resolver.resolve("Poder Executivo") is None
    assert resolver.resolve("Mesa Diretora") is None
    assert resolver.resolve(None) is None
    assert resolver.resolve("") is None


def test_apenas_primeiro_signatario_conta(resolver):
    assert resolver.resolve("Flávio Dino, Eduardo Bolsonaro") == "dino"


def test_resolve_party_id_case_e_vazio():
    mapa = {"PT": 1, "S.PART.": 9}
    assert resolve_party_id(mapa, "PT") == 1
    assert resolve_party_id(mapa, "pt") == 1  # cai para a chave em maiúsculas
    assert resolve_party_id({"PCdoB": 2, "PCDOB": 2}, "PCdoB") == 2
    assert resolve_party_id(mapa, "PTX") is None  # sigla desconhecida não vira "Sem Partido" aqui
    assert resolve_party_id(mapa, "") == 9
    assert resolve_party_id(mapa, None) == 9
    assert resolve_party_id(mapa, float("nan")) == 9


def test_legislatura_datas():
    assert legislatura_datas(57) == (date(2023, 2, 1), date(2027, 1, 31))
    assert legislatura_datas(56) == (date(2019, 2, 1), date(2023, 1, 31))
    assert legislatura_datas(58)[0] == date(2027, 2, 1)


def test_dec_preserva_zero_e_trata_nan_none_vazio():
    assert _dec(0) == Decimal("0")
    assert _dec("0.0") == Decimal("0.0")
    assert _dec(None) is None
    assert _dec(float("nan")) is None
    assert _dec("  ") is None
    assert _dec("abc") is None
    assert _dec(1.5) == Decimal("1.5")


def test_to_date():
    assert _to_date("2023-02-01T10:00:00") == date(2023, 2, 1)
    assert _to_date(None) is None
    assert _to_date("None") is None
    assert _to_date("nan") is None
    assert _to_date("sem data") is None


def test_limpar_contatos_inventados_so_remove_padroes_exatos():
    sintetico = SimpleNamespace(
        email="dep.123@camara.leg.br", cabinet_room="Anexo IV, Gabinete 345", cabinet_phone="(61) 3215-5345"
    )
    assert limpar_contatos_inventados(sintetico) is True
    assert sintetico.email is None and sintetico.cabinet_room is None and sintetico.cabinet_phone is None

    real = SimpleNamespace(
        email="fulano@camara.leg.br", cabinet_room="Anexo 4, Gabinete 345", cabinet_phone="(61) 3215-5345"
    )
    assert limpar_contatos_inventados(real) is False
    assert real.email == "fulano@camara.leg.br" and real.cabinet_room == "Anexo 4, Gabinete 345"


def test_classificacao_sem_correspondencia_nao_inventa_eixo():
    eixo, tags = classify_proposition_impact(
        "PL", 5, 2021, "Dispõe sobre algo", "Assunto sem palavras-chave conhecidas xyz"
    )
    assert eixo is None and tags is None


def test_materias_estruturantes_exigem_tipo_numero_e_ano():
    eixo, _ = classify_proposition_impact("PLP", 93, 2023, "x", "y")
    assert eixo == "Responsabilidade Fiscal"
    # Mesmo número em outro ano NÃO é o arcabouço fiscal
    eixo_outro, _ = classify_proposition_impact("PLP", 93, 2005, "x", "assunto neutro qualquer")
    assert eixo_outro is None
