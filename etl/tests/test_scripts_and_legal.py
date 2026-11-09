"""Diagnóstico de autoria (somente leitura) e cargas sintéticas."""

from etl.scripts.diagnose_anomalies import nome_aparece


def test_diagnostico_ignora_nome_vazio_e_acentos():
    assert nome_aparece("Flávio Dino", "Flavio Dino (PSB/MA)")
    assert not nome_aparece("", "Qualquer")  # antes `"" in texto` era sempre True
    # O diagnóstico é deliberadamente MAIS permissivo que o loader (subconjunto de tokens): serve para listar
    # suspeitos, não para decidir vínculos. O vínculo em si é decidido pelo AuthorResolver (igualdade exata).
    assert nome_aparece("Dr. Flávio", "Flávio Dino")
    assert not nome_aparece("Eduardo Bolsonaro", "Flávio Dino")
