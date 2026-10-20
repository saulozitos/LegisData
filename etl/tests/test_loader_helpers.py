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
from etl.tests.sinteticos import (
    CNPJ_DE_RAIZ_ZERADA,
    CPF_A,
    CPF_A_INVALIDO,
    formatado,
    zero_mais_cpf_que_fecha_como_cnpj,
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


def test_texto_sem_cpf_tira_o_cpf_comprovado_em_qualquer_agrupamento_e_preserva_valor_em_reais():
    from etl.pipelines.loader_helpers import nome_sem_cpf, texto_sem_cpf

    assert "nome_sem_cpf" in texto_sem_cpf.__doc__ and "reais" in texto_sem_cpf.__doc__
    grupos = f"{CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]}"
    assert nome_sem_cpf(f"X {grupos}") == "X" and texto_sem_cpf(f"X {grupos} Y") == "X Y"
    assert texto_sem_cpf(f"X {' '.join(CPF_A)} Y") == "X Y"  # um dígito por vez
    assert texto_sem_cpf(f"X {formatado(CPF_A)} Y") == "X Y"
    assert texto_sem_cpf(f"pago R$ {CPF_A},50 ao fornecedor") == f"pago R$ {CPF_A},50 ao fornecedor"  # valor em reais
    assert texto_sem_cpf(f"saldo {CPF_A},50") == f"saldo {CPF_A},50"
    assert texto_sem_cpf("Processo 500600700800 arquivado") == "Processo 500600700800 arquivado"


def test_nome_sem_cpf_tira_o_cpf_colado_a_dois_digitos_mas_deixa_o_cnpj_sem_o_zero():
    """13 dígitos: ou é um CNPJ que perdeu o zero à esquerda (fecha com "0" na frente), ou um CPF com 2 dígitos grudados."""
    from etl.pipelines.loader_helpers import cnpj_dv_valido, nome_sem_cpf

    assert nome_sem_cpf(f"FULANO 99{CPF_A}") == "FULANO" and nome_sem_cpf(f"FULANO {CPF_A}99") == "FULANO"
    from etl.pipelines.loader_helpers import cpf_valido

    # um CNPJ de 14 dígitos que começa por zero, escrito sem ele (13 dígitos), e sem nenhuma janela que seja CPF
    sem_zero = next(
        d
        for raiz in range(1222333, 1222333 + 5000)
        for dv in range(100)
        if cnpj_dv_valido("0" + (d := f"{raiz}0001{dv:02d}")) and not any(cpf_valido(d[i : i + 11]) for i in range(3))
    )
    assert len(sem_zero) == 13 and nome_sem_cpf(f"BANCO {sem_zero}") == f"BANCO {sem_zero}"


@pytest.mark.parametrize("digitos", ["²" * 11, "١٢٣٤٥٦٧٨٩٠١", "１２３４５６７８９０１", "abcdefghijk"])
def test_cpf_valido_e_cnpj_dv_valido_nao_levantam_com_digitos_que_nao_sao_ascii(digitos):
    from etl.pipelines.loader_helpers import cnpj_dv_valido, cpf_valido

    assert cpf_valido(digitos) is False and cnpj_dv_valido(digitos + "123") is False


@pytest.mark.parametrize(
    "raiz", sorted(__import__("etl.pipelines.loader_helpers", fromlist=["x"]).RAIZES_ZERADAS_CONHECIDAS)
)
def test_as_raizes_zeradas_conhecidas_existem_nos_dados_versionados_ou_sao_a_do_banco_do_brasil(raiz):
    """A allowlist não pode acumular raízes sem origem: toda raiz é a do BB ou aparece num arquivo de dados versionado."""

    from etl.config import PROCESSED_DATA_DIR

    if raiz == "00000000":
        return
    texto = (PROCESSED_DATA_DIR / "tse_doacoes_campanha.json").read_text(encoding="utf-8")
    # a máscara completa do CNPJ (XX.XXX.XXX/), não uma sequência de 8 dígitos que cairia dentro de qualquer número
    assert f"{raiz[:2]}.{raiz[2:5]}.{raiz[5:8]}/" in texto, raiz


def test_zero_mais_cpf_que_fecha_como_cnpj_so_escapa_com_raiz_conhecida_e_o_nome_nao_desempata():
    """Uma regra só (a mesma da guarda de D3): o nome ao lado do documento não confirma um CNPJ, só a allowlist de raízes."""
    from etl.pipelines import loader_helpers as h

    assert not hasattr(h, "nome_de_pj")
    assert "nome" not in h.cnpj_do_fornecedor.__code__.co_varnames[: h.cnpj_do_fornecedor.__code__.co_argcount]
    for achado in zero_mais_cpf_que_fecha_como_cnpj(5):
        assert h.cpf_com_zeros(achado) is True and h.cnpj_do_fornecedor(achado) is None
        mascara = f"{achado[:2]}.{achado[2:5]}.{achado[5:8]}/{achado[8:12]}-{achado[12:]}"
        assert h.cpfs_suspeitos_em(f"MEI {mascara}") >= 1 and h.nome_sem_cpf(f"MEI {mascara}") == "MEI"
    conhecida = "00000000000191"  # raiz conhecida: é CNPJ
    assert h.cnpj_do_fornecedor(conhecida) == conhecida and h.cpf_com_zeros(conhecida) is False


def test_uma_raiz_zerada_legitima_entra_na_allowlist_e_deixa_de_ser_acusada_pela_guarda_e_pelo_loader(monkeypatch):
    """O contrato: o CNPJ de raiz zerada que a guarda acusa só passa depois de ser medido e posto em RAIZES_ZERADAS_CONHECIDAS."""
    from etl.pipelines import loader_helpers as h

    [achado] = zero_mais_cpf_que_fecha_como_cnpj()
    formatado_ = f"{achado[:2]}.{achado[2:5]}.{achado[5:8]}/{achado[8:12]}-{achado[12:]}"
    assert h.cnpj_do_fornecedor(achado) is None and h.cpfs_suspeitos_em(f"X {formatado_}") >= 1
    monkeypatch.setattr(h, "RAIZES_ZERADAS_CONHECIDAS", h.RAIZES_ZERADAS_CONHECIDAS | {achado[:8]})
    assert h.cnpj_do_fornecedor(achado) == achado and h.cpfs_suspeitos_em(f"X {formatado_}") == 0


@pytest.mark.parametrize("prefixo", ["123", "999", "100", "12", "99", "5"])
def test_nome_sem_cpf_tira_o_cpf_colado_a_um_a_tres_digitos_qualquer_que_seja_o_prefixo(prefixo):
    from etl.pipelines.loader_helpers import nome_sem_cpf

    assert nome_sem_cpf(f"FULANO {prefixo}{CPF_A}") == "FULANO"
    assert nome_sem_cpf(f"FULANO {CPF_A}{prefixo}") == "FULANO"


def test_nome_sem_cpf_com_13_digitos_que_fecham_como_cnpj_e_contem_cpf_so_mantem_raiz_conhecida():
    """Um CPF com 2 dígitos grudados que por acaso fecha como "0"+número (cerca de 1,4%) não escapa; um CNPJ sem CPF dentro fica."""
    from etl.pipelines import loader_helpers as h
    from etl.tests.sinteticos import cpf_com_digitos

    vazaram, exercitados = [], 0
    for base in range(123456789, 123456789 + 30000 * 7919, 7919):
        d = "99" + cpf_com_digitos(str(base))
        if h.cnpj_dv_valido("0" + d) and ("0" + d)[:8] not in h.RAIZES_ZERADAS_CONHECIDAS:
            exercitados += 1
            if h.nome_sem_cpf(f"FULANO {d}") != "FULANO":
                vazaram.append(d[:2])
    assert exercitados >= 3 and vazaram == []
    cnpj_sem_cpf_dentro = "11222333000181"  # fecha como CNPJ e nenhuma janela de 11 dígitos é CPF
    assert not any(h.cpf_valido(cnpj_sem_cpf_dentro[i : i + 11]) for i in range(4))
    assert h.nome_sem_cpf(f"LOJA {cnpj_sem_cpf_dentro}") == f"LOJA {cnpj_sem_cpf_dentro}"
    banco = "00000000000191"  # raiz conhecida, mesmo contendo um CPF válido nos 11 últimos
    assert h.cpf_valido(banco[3:]) and h.nome_sem_cpf(f"BANCO {banco}") == f"BANCO {banco}"


def test_nome_sem_cpf_com_14_digitos_tira_o_que_contem_cpf_salvo_raiz_conhecida_e_deixa_o_cnpj_sem_cpf_dentro():
    """Sair do nome não custa nada: o documento da empresa vive no campo próprio. Fica o CNPJ sem CPF dentro e o de raiz conhecida."""
    from etl.pipelines import loader_helpers as h

    vivo = "02558157000162"  # CNPJ real que fecha o verificador e tem um CPF válido numa das janelas de 11 dígitos
    assert h.cnpj_dv_valido(vivo) and any(h.cpf_valido(vivo[i : i + 11]) for i in range(4))
    assert h.nome_sem_cpf(f"TELEFONICA {vivo}") == "TELEFONICA"
    assert not h.cnpj_dv_valido("123" + CPF_A) and h.nome_sem_cpf(f"FULANO 123{CPF_A}") == "FULANO"
    sem_cpf = "11222333000181"
    assert h.cnpj_dv_valido(sem_cpf) and h.nome_sem_cpf(f"LOJA {sem_cpf}") == f"LOJA {sem_cpf}"


@pytest.mark.parametrize(
    "montar",
    [
        lambda c: f"{c[:3]},{c[3:6]},{c[6:9]},{c[9:]}",
        lambda c: f"{c[:3]}, {c[3:6]}, {c[6:9]}, {c[9:]}",
        lambda c: f'"{c[:3]}", "{c[3:6]}", "{c[6:9]}", "{c[9:]}"',
        lambda c: f"{c[:3]}/{c[3:6]}/{c[6:9]}/{c[9:]}",
        lambda c: f"{c[:3]}.{c[3:6]}.{c[6:9]}/{c[9:]}",
        lambda c: ",".join(c),
    ],
)
def test_nome_texto_e_guarda_concordam_sobre_o_cpf_repartido_por_separador_constante(montar):
    from etl.pipelines.loader_helpers import cpfs_suspeitos_em, nome_sem_cpf, texto_sem_cpf

    forma = montar(CPF_A)
    # o que sobra depois do saneamento não é mais acusado pela guarda (o saneamento nunca deixa passar o que a guarda vê)
    assert cpfs_suspeitos_em(nome_sem_cpf(f"FULANO {forma}") or "", True) == 0
    saneado = texto_sem_cpf(f"FULANO {forma} FIM") or ""
    assert cpfs_suspeitos_em(saneado, True) == 0 and "FIM" in saneado
    assert cpfs_suspeitos_em(forma, False) >= 1 and cpfs_suspeitos_em(forma, True) >= 1


def test_texto_sem_cpf_preserva_valor_em_reais_e_so_trata_casa_decimal_de_digitos_corridos():
    from etl.pipelines.loader_helpers import texto_sem_cpf

    grupos = f"{CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]}"
    assert (
        texto_sem_cpf(f"X {grupos},12 Y") == "X ,12 Y"
    )  # com separadores entre os grupos o CPF sai, mesmo seguido de ",12"
    assert texto_sem_cpf(f"saldo {CPF_A},12") == f"saldo {CPF_A},12"  # dígitos corridos + casa decimal: valor
    assert texto_sem_cpf("R$ 1,234,567,890 e 1.234.567.890,12") == "R$ 1,234,567,890 e 1.234.567.890,12"
    assert texto_sem_cpf(f"R$ {CPF_A[:3]},{CPF_A[3:6]},{CPF_A[6:9]},{CPF_A[9:]}") == (
        f"R$ {CPF_A[:3]},{CPF_A[3:6]},{CPF_A[6:9]},{CPF_A[9:]}"
    )
    assert texto_sem_cpf("lista 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11") == "lista 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11"


def test_a_guarda_nao_acusa_a_cauda_de_um_valor_em_reais_nem_listas_de_numeros_diversos():
    from etl.pipelines.loader_helpers import cpfs_suspeitos_em

    assert cpfs_suspeitos_em("no valor de R$ 1.234.567.890,12, para os fins") == 0
    assert cpfs_suspeitos_em("(2023, 400.5, 2022.1, 33.5)") == 0
