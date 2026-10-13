"""Normalização de nomes e índice sem correspondência por substring."""

from etl.utils.names import NameIndex, build_unique_name_map, first_signatory, normalize_name_tokens


def test_normalize_remove_acentos_titulos_e_siglas():
    assert normalize_name_tokens("Dr. João da Silva (PL/SP)") == "joao da silva"
    assert normalize_name_tokens("Delegada  Érika Kokay [PT-DF]") == "erika kokay"
    assert normalize_name_tokens(None) == ""
    assert normalize_name_tokens("") == ""


def test_titulos_nao_deixam_nome_de_um_unico_token_ambiguo_por_engano():
    # "Dr. Flávio" vira "flavio": por isso o ETL nunca casa por subconjunto de tokens
    assert normalize_name_tokens("Dr. Flávio") == "flavio"
    assert normalize_name_tokens("Flávio Dino") == "flavio dino"
    assert normalize_name_tokens("Dr. Flávio") != normalize_name_tokens("Flávio Dino")


def test_first_signatory_pega_apenas_o_primeiro_autor():
    assert first_signatory("Fulano de Tal, Beltrano; Ciclana") == "Fulano de Tal"
    assert first_signatory(None) == ""


def test_name_index_so_resolve_nome_inequivoco():
    idx = NameIndex([(1, "Ana Souza"), (2, "Ana Souza"), (3, "Lula da Fonte"), (4, "Lula")])
    assert idx.lookup("Ana Souza") is None  # homônimos
    assert idx.is_ambiguous("ANA SOUZA")
    assert idx.lookup("Lula") == 4
    assert idx.lookup("Lula da Fonte") == 3  # não casa com "Lula" por substring
    assert idx.lookup("Inexistente") is None


def test_build_unique_name_map_descarta_homonimos_e_aceita_mesmo_id_repetido():
    mapa = build_unique_name_map([(1, "João Alves"), (1, "Joao Alves"), (2, "Maria"), (3, "Maria")])
    assert mapa == {"joao alves": 1}
