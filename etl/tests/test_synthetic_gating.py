"""Geradores de dado fictício: desligados por padrão e, quando ligados, sempre marcados."""

from etl.extractors.ceap_extractor import CeapExtractor
from etl.extractors.justica_extractor import JusticaExtractor
from etl.extractors.social_indicators_extractor import MANDATO_POR_ELEICAO, SocialIndicatorsExtractor
from etl.utils.provenance import has_provenance, is_synthetic, is_trusted, mark_official, mark_synthetic


def test_certidoes_por_padrao_sao_desconhecidas_nunca_nada_consta(tmp_path):
    possui, certidoes = JusticaExtractor(tmp_path, tmp_path).get_certidoes_for_politician("Qualquer Um", "SP")
    assert possui is None and certidoes == []


def test_certidoes_sinteticas_nao_trazem_numero_data_ou_codigo(tmp_path):
    possui, certidoes = JusticaExtractor(tmp_path, tmp_path).get_certidoes_for_politician(
        "Qualquer", "SP", allow_synthetic=True
    )
    assert possui is None and certidoes
    for c in certidoes:
        assert c["is_synthetic"] is True
        assert c["numero_processo"] is None and c["data_emissao"] is None and c["codigo_autenticidade"] is None
        assert c["status_ficha"] != "Nada Consta"


def test_ceap_sintetica_desligada_por_padrao():
    ext = CeapExtractor()
    assert ext.generate_representative_ceap("Fulano") == []
    gerado = ext.generate_representative_ceap("Fulano", allow_synthetic=True)
    assert gerado and all(g["is_synthetic"] for g in gerado)
    assert gerado == ext.generate_representative_ceap("Fulano", allow_synthetic=True)  # sem hash() não determinístico


def test_eleicoes_usam_ids_de_mandato_dos_presidentes_e_nao_sao_verificadas():
    from etl.extractors.presidents_extractor import PresidentsExtractor

    ids_validos = {p["id_referencia"] for p in PresidentsExtractor.get_presidents()}
    assert set(MANDATO_POR_ELEICAO.values()) <= ids_validos
    ext = SocialIndicatorsExtractor.__new__(SocialIndicatorsExtractor)
    eleicoes = ext.get_presidential_elections_by_uf()
    assert {e["mandato_id_ref"] for e in eleicoes} <= ids_validos
    assert all(e["verificado"] is False for e in eleicoes)


def test_provenance_helpers():
    legado = {"valor": 1}
    assert not has_provenance(legado) and not is_trusted(legado)
    assert is_trusted(mark_official({"valor": 1}, "Fonte X"))
    assert is_synthetic(mark_synthetic({"valor": 1})) and not is_trusted(mark_synthetic({"valor": 1}))
