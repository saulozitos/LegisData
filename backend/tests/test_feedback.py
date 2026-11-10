"""Botão "Encontrou uma informação incorreta?": o relato chega com contexto e nunca com CPF."""

import pytest
from sqlalchemy import text

URL = "/api/v1/feedback/erros"


def _cpf_com_digitos(base9: str) -> str:
    """CPF válido calculado na hora: nenhum número de CPF fica escrito em arquivo versionado."""
    digitos = [int(c) for c in base9]
    for tamanho in (9, 10):
        soma = sum(d * (tamanho + 1 - i) for i, d in enumerate(digitos[:tamanho]))
        digitos.append((soma * 10 % 11) % 10)
    return "".join(str(d) for d in digitos)


_CPF = _cpf_com_digitos("".join(str(n) for n in (5, 2, 9, 9, 8, 2, 2, 4, 7)))
CPFS_DE_TESTE = [
    f"{_CPF[:3]}.{_CPF[3:6]}.{_CPF[6:9]}-{_CPF[9:]}",
    _CPF,
    f"{_CPF[:3]} {_CPF[3:6]} {_CPF[6:9]} {_CPF[9:]}",
]
VALIDO = {
    "alvo_tipo": "POLITICO",
    "alvo_id": "abc-123",
    "alvo_rotulo": "Fulano de Tal",
    "secao": "Histórico partidário",
    "descricao": "O partido de 2018 está errado, era outro naquele ano.",
    "contato": "pessoa@exemplo.com",
    "pagina": "https://legisdata.exemplo/?aba=raiox&politico=abc-123",
}


def _linhas(db):
    return db.execute(
        text("SELECT alvo_tipo, alvo_id, alvo_rotulo, secao, descricao, contato, status FROM etl.relato_erro")
    ).all()


@pytest.fixture(autouse=True)
def _limpa(db):
    db.execute(text("DELETE FROM etl.relato_erro"))
    db.commit()
    yield
    db.execute(text("DELETE FROM etl.relato_erro"))
    db.commit()


def test_relato_fica_ligado_ao_alvo_e_nasce_como_novo(client, db):
    resposta = client.post(URL, json=VALIDO)
    assert resposta.status_code == 201 and resposta.json()["id"] is not None
    assert _linhas(db) == [
        (
            "POLITICO",
            "abc-123",
            "Fulano de Tal",
            "Histórico partidário",
            "O partido de 2018 está errado, era outro naquele ano.",
            "pessoa@exemplo.com",
            "NOVO",
        )
    ]


def test_contato_e_opcional(client, db):
    corpo = {k: v for k, v in VALIDO.items() if k != "contato"}
    assert client.post(URL, json=corpo).status_code == 201
    assert _linhas(db)[0][5] is None


@pytest.mark.parametrize("cpf", CPFS_DE_TESTE)
def test_texto_com_cpf_e_recusado_e_nada_e_gravado(client, db, cpf):
    resposta = client.post(URL, json={**VALIDO, "descricao": f"O CPF dele é {cpf}, confira por favor."})
    assert resposta.status_code == 422 and "CPF" in resposta.json()["detail"]
    assert _linhas(db) == []


def test_numero_de_11_digitos_que_nao_e_cpf_passa(client, db):
    resposta = client.post(URL, json={**VALIDO, "descricao": "O protocolo 12345678900 não bate com a proposição."})
    assert resposta.status_code == 201


@pytest.mark.parametrize(
    "campo, valor",
    [("descricao", "curta"), ("descricao", "x" * 2001), ("alvo_tipo", "QUALQUER"), ("contato", "c" * 201)],
)
def test_entrada_invalida_e_recusada(client, db, campo, valor):
    assert client.post(URL, json={**VALIDO, campo: valor}).status_code == 422
    assert _linhas(db) == []


def test_campo_isca_preenchido_responde_igual_mas_nao_grava(client, db):
    resposta = client.post(URL, json={**VALIDO, "website": "http://spam.exemplo"})
    assert resposta.status_code == 201 and resposta.json()["id"] is None
    assert _linhas(db) == []
