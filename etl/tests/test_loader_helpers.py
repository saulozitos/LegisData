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
    normalizar_sigla_presenca,
    resolve_party_id,
)
from etl.tests.sinteticos import CNPJ_DE_RAIZ_ZERADA, CPF_A, CPF_A_INVALIDO, formatado


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


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("s/partido", "S.PART."),
        ("S/Partido", "S.PART."),
        ("Sem registro", None),
        ("sem registro", None),
        ("", None),
        (None, None),
        ("  PL ", "PL"),
        ("PODE", "PODE"),
    ],
)
def test_normalizar_sigla_presenca(bruto, esperado):
    assert normalizar_sigla_presenca(bruto) == esperado


@pytest.mark.parametrize(
    "digitos, esperado",
    [(CPF_A, True), (CPF_A_INVALIDO, False), ("11111111111", False), ("5299822472", False), ("abc", False)],
)
def test_cpf_valido_confere_tamanho_repeticao_e_digitos_verificadores(digitos, esperado):
    from etl.pipelines.loader_helpers import cpf_valido

    assert cpf_valido(digitos) is esperado


@pytest.mark.parametrize(
    "documento, esperado",
    [
        ("000" + CPF_A, None),  # CPF válido com enchimento de zeros à esquerda
        (f"000.{CPF_A[:3]}.{CPF_A[3:6]}/{CPF_A[6:10]}-{CPF_A[10]}", None),
        ("00001974000190", "00001974000190"),  # CNPJ real com zeros à esquerda que não fecha como CPF
        ("02.558.157/0001-62", "02558157000162"),
        ("12345678", None),
    ],
)
def test_cnpj_do_fornecedor_barra_cpf_com_enchimento_e_mantem_cnpj(documento, esperado):
    from etl.pipelines.loader_helpers import cnpj_do_fornecedor

    assert cnpj_do_fornecedor(documento) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        " ".join(CPF_A),  # um dígito por grupo (11 grupos)
        f"{CPF_A[:3]}     {CPF_A[3:]}",  # separador de 5 espaços
        f"{CPF_A[:3]}-{CPF_A[3:6]}-{CPF_A[6:9]}-{CPF_A[9:]}",
        "0" * 6 + CPF_A,  # muitos zeros de enchimento
        "000 " + " ".join((CPF_A[:3], CPF_A[3:6], CPF_A[6:9], CPF_A[9:])),
        formatado(CPF_A),
    ],
)
def test_nome_sem_cpf_remove_o_cpf_valido_em_qualquer_agrupamento(texto):
    from etl.pipelines.loader_helpers import cpfs_validos_em, nome_sem_cpf

    assert cpfs_validos_em(texto) == 1
    assert nome_sem_cpf(f"FULANO {texto}") == "FULANO"


@pytest.mark.parametrize(
    "texto",
    ["LOJA 2020 2021 2022", "TEL 61 3215 1234", "11.222.333/0001-81", "VALOR 1.234,56", "1 2 3 4 5 6 7 8 9 10 11 12"],
)
def test_nome_sem_cpf_deixa_o_que_nao_e_cpf(texto):
    from etl.pipelines.loader_helpers import cpfs_validos_em, nome_sem_cpf

    assert cpfs_validos_em(texto) == 0 and nome_sem_cpf(f"LOJA {texto}") == f"LOJA {texto}"


def test_o_saneamento_de_texto_hostil_e_linear():
    import time

    from etl.pipelines.loader_helpers import nome_sem_cpf

    t0 = time.time()
    nome_sem_cpf("1 " * 300_000)
    nome_sem_cpf("1" + " " * 600_000 + "1")
    assert time.time() - t0 < 10


@pytest.mark.parametrize(
    "digitos, esperado",
    [
        ("00000000000191", True),
        ("11222333000181", True),
        ("11222333000182", False),
        ("11111111111111", False),
        ("123", False),
    ],
)
def test_cnpj_dv_valido(digitos, esperado):
    from etl.pipelines.loader_helpers import cnpj_dv_valido

    assert cnpj_dv_valido(digitos) is esperado


def test_cnpj_de_raiz_zerada_que_fecha_como_cnpj_nao_e_tratado_como_cpf_com_enchimento():
    """O CNPJ do Banco do Brasil (00.000.000/0001-91) passa nos dígitos de CPF por acaso: é CNPJ e fica."""
    from etl.pipelines.loader_helpers import cnpj_do_fornecedor, cpf_com_zeros, cpfs_validos_em, nome_sem_cpf

    d = CNPJ_DE_RAIZ_ZERADA
    formatado_ = f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    assert cnpj_do_fornecedor(formatado_) == d
    assert cpf_com_zeros(d) is False
    assert nome_sem_cpf(f"BANCO {d}") == f"BANCO {d}"
    assert nome_sem_cpf(f"BANCO {formatado_}") == f"BANCO {formatado_}"
    assert cpfs_validos_em(f"BANCO {d}") == 0


def test_cpf_com_zeros_aceita_enchimento_de_qualquer_tamanho_e_nao_o_cnpj_que_fecha():
    from etl.pipelines.loader_helpers import cpf_com_zeros

    assert cpf_com_zeros(CPF_A) and cpf_com_zeros("0" + CPF_A) and cpf_com_zeros("0" * 20 + CPF_A)
    assert not cpf_com_zeros("1" + CPF_A) and not cpf_com_zeros(CPF_A_INVALIDO) and not cpf_com_zeros("123")


def test_cpf_com_enchimento_dentro_de_cnpj_formatado_sai_do_nome_e_o_do_documento_vira_none():
    from etl.pipelines.loader_helpers import cnpj_do_fornecedor, nome_sem_cpf

    d = "000" + CPF_A
    mascara = f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"  # a máscara de CNPJ (NN.NNN.NNN/NNNN-NN) com CPF dentro
    assert cnpj_do_fornecedor(mascara) is None
    assert nome_sem_cpf(f"MEI {mascara}") == "MEI"


@pytest.mark.parametrize("sufixo", [", 2", " / 2024", ", 12345678000195", " , "])
def test_cpf_seguido_de_virgula_ou_barra_nao_se_esconde_atras_dela(sufixo):
    """A vírgula e a barra não juntam grupos: cada lado é avaliado sozinho."""
    from etl.pipelines.loader_helpers import cpfs_validos_em, nome_sem_cpf

    texto = f"FULANO {CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]}{sufixo}"
    assert cpfs_validos_em(texto) == 1
    assert CPF_A[:4] not in (nome_sem_cpf(texto) or "")


def test_texto_sem_cpf_tem_contrato_mais_frouxo_que_o_do_nome():
    """Documentado: texto livre preserva valor em reais ('R$ ...'); o nome tira o CPF comprovado em qualquer agrupamento."""
    from etl.pipelines.loader_helpers import nome_sem_cpf, texto_sem_cpf

    assert "Contrato" in texto_sem_cpf.__doc__ and "nome_sem_cpf" in texto_sem_cpf.__doc__
    assert nome_sem_cpf(f"X {CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]}") == "X"
