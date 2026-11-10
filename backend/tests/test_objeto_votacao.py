"""O placar sempre diz o que foi votado: urgência e destaque não são a aprovação do projeto."""

import pytest
from sqlalchemy import text

BASE = "/api/v1/legislative"

# frases reais da deliberação da Câmara (descrição da votação) e o objeto esperado
CASOS = [
    ("Aprovado o Requerimento de Urgência (Art. 155 do RICD). Sim: 339; não: 18; total: 357.", "URGENCIA"),
    ("Rejeitado o Requerimento. Sim: 2; não: 269; total: 271.", "REQUERIMENTO"),
    ("Mantido o texto. Sim: 258; não: 129; total: 387.", "DESTAQUE"),
    ("Suprimido o texto. Sim: 21; não: 300; total: 321.", "DESTAQUE"),
    ("Rejeitada a Emenda de Plenário nº 3. Sim: 100; não: 300; total: 400.", "EMENDA"),
    ("Aprovada a Subemenda Substitutiva Global ao Projeto de Lei nº 1, de 2021.", "EMENDA"),
    ("Rejeitadas as Emendas de n°s 6 e 8. Sim: 182; não: 282; total: 465.", "EMENDA"),
    ("Aprovado, em apreciação preliminar, o Parecer da Comissão Mista.", "PARECER"),
    ("Aprovada a redação final.", "REDACAO_FINAL"),
    ("Aprovado o Projeto de Lei nº 2.253, de 2022. Sim: 300; não: 100; total: 400.", "TEXTO_PRINCIPAL"),
    ("Aprovada, em segundo turno, a Proposta de Emenda à Constituição nº 45, de 2019.", "TEXTO_PRINCIPAL"),
    ("Aprovado o Substitutivo ao Projeto de Lei Complementar nº 68, de 2024.", "TEXTO_PRINCIPAL"),
    ("Votação nominal", None),  # a fonte não diz o que foi votado: sem objeto, nada é suposto
    ("Votação nominal.", None),
]


@pytest.mark.parametrize("frase, esperado", CASOS)
def test_regras_do_banco_classificam_a_deliberacao(db, frase, esperado):
    codigo = db.execute(
        text("SELECT codigo FROM ref.objeto_votacao_regra WHERE lower(:t) ~ padrao ORDER BY ordem LIMIT 1"),
        {"t": frase},
    ).scalar()
    assert codigo == esperado


def test_urgencia_e_destaque_nao_decidem_o_merito_do_projeto(db):
    decide = dict(db.execute(text("SELECT codigo, decide_merito FROM ref.objeto_votacao")).all())
    assert decide["TEXTO_PRINCIPAL"] is True
    assert not any(decide[c] for c in ("URGENCIA", "REQUERIMENTO", "DESTAQUE", "EMENDA", "PARECER", "REDACAO_FINAL"))


def test_calendario_traz_o_objeto_de_cada_votacao_e_deixa_nulo_o_que_a_fonte_nao_diz(client, seed):
    dias = {d["data"]: d for d in client.get(f"{BASE}/calendar", params={"year": 2023}).json()["dias"]}
    destaque = dias["2023-05-03"]["sessoes"][0]["objeto"]
    assert destaque["codigo"] == "DESTAQUE" and destaque["decide_merito"] is False
    assert "Não é a votação do projeto inteiro" in destaque["explicacao"]
    assert dias["2023-05-02"]["sessoes"][0]["objeto"] is None  # "Votação de mérito" não diz o objeto
