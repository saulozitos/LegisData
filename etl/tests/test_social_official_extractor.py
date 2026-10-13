"""Indicadores sociais oficiais: séries por tabela, sem interpolação e com quebras metodológicas explícitas."""

from etl.extractors import social_official_extractor as mod
from etl.extractors.social_official_extractor import SocialOfficialExtractor
from etl.utils.http_client import HttpError


def linha(ano, valor, uf=None, mn="%", periodo=None):
    r = {"V": str(valor), "D3C": str(periodo or ano), "MN": mn}
    if uf is not None:
        r["D1C"] = str(uf)
    return r


class SidraFalso:
    """Responde por (tabela, nível); parâmetros extras são ignorados."""

    def __init__(self, tabelas):
        self.tabelas = tabelas

    def try_values(self, tabela, nivel=1, locais="all", variaveis="all", periodos="all", classificacoes=None):
        chave = (tabela, nivel, (classificacoes or {}).get(12404))
        return self.tabelas.get(chave) or self.tabelas.get((tabela, nivel)) or []


class HttpPME:
    def __init__(self, dados=None, erro=None):
        self.dados, self.erro = dados, erro

    def get_json(self, url, **_):
        if self.erro:
            raise self.erro
        return self.dados


def pme_completo(ano, valor):
    return [{"data": f"01/{m:02d}/{ano}", "valor": str(valor)} for m in range(1, 13)]


def montar(tabelas, http=None, tmp_path=None):
    return SocialOfficialExtractor(
        output_dir=tmp_path, sidra=SidraFalso(tabelas), http=http or HttpPME(erro=HttpError("u", 500, "x"))
    )


def test_gini_usa_pnadc_a_partir_de_2012_e_pnad_antes_com_quebra(tmp_path):
    ext = montar(
        {
            (1167, 1): [linha(2009, 0.518), linha(2011, 0.508)],
            (7435, 1): [linha(2012, 0.540), linha(2011, 0.999)],  # PNADC 2011 (não existe de fato) vence a PNAD antiga
        },
        tmp_path=tmp_path,
    )
    serie = {r["ano"]: r for r in ext.get_annual_social_indicators()}
    assert serie[2009]["gini"] == 0.518 and "PNAD — pessoas de 10+" in serie[2009]["serie_gini"]
    assert serie[2012]["gini"] == 0.54 and "PNAD Contínua" in serie[2012]["serie_gini"]
    assert serie[2012]["quebra_metodologica_gini"] is True and serie[2011]["quebra_metodologica_gini"] is False
    assert all(r["is_synthetic"] is False and r["fonte"] for r in serie.values())


def test_lacunas_ficam_none_e_anos_sem_dado_nao_aparecem(tmp_path):
    ext = montar({(5817, 1): [linha(2012, 8.8), linha(2013, "-")]}, tmp_path=tmp_path)
    serie = {r["ano"]: r for r in ext.get_annual_social_indicators()}
    assert 2013 not in serie  # 2013 sem valor não vira linha nem zero
    assert serie[2012]["analfabetismo"] is None and serie[2012]["gini"] is None


def test_extrema_pobreza_em_milhoes_deriva_da_populacao(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "populacao_brasil", lambda _s: {2012: 200_000_000})
    ext = montar({(5817, 1): [linha(2012, 10.0), linha(2013, 5.0)]}, tmp_path=tmp_path)
    serie = {r["ano"]: r for r in ext.get_annual_social_indicators()}
    assert serie[2012]["extrema_pobreza_milhoes"] == 20.0
    assert serie[2013]["extrema_pobreza_milhoes"] is None  # sem população publicada: não estima


def test_inseguranca_alimentar_separa_pesquisas_e_nao_mistura_penssan(tmp_path):
    ext = montar(
        {
            (3017, 1, "109102"): [linha(2004, 6.47)],
            (3017, 1, "109099"): [linha(2004, 34.79)],
            (9552, 1, "109102"): [linha(2023, 4.1)],
            (9552, 1, "109099"): [linha(2023, 27.6)],
            (9552, 1): [],
        },
        tmp_path=tmp_path,
    )
    serie = {r["ano"]: r for r in ext.get_annual_social_indicators()}
    assert serie[2004]["inseguranca_alimentar_pct"] == 6.47 and "2004" in serie[2004]["fonte_inseguranca_alimentar"]
    assert serie[2023]["inseguranca_alimentar_pct"] == 4.1 and serie[2023]["inseguranca_alimentar_total_pct"] == 27.6
    assert 2009 not in serie and 2013 not in serie  # pesquisas fora do SIDRA: lacuna, nunca interpolação


def test_rede_penssan_fica_em_campos_proprios(tmp_path):
    ext = montar({(7435, 1): [linha(2022, 0.517)]}, tmp_path=tmp_path)
    serie = {r["ano"]: r for r in ext.get_annual_social_indicators()}
    assert serie[2022]["rede_penssan_fome_pct"] == 15.5 and "II VIGISAN" in serie[2022]["rede_penssan_fonte"]
    assert serie[2022]["inseguranca_alimentar_pct"] is None  # a série do IBGE não é preenchida com a da Rede PENSSAN
    assert set(serie) == {2022}  # a Rede PENSSAN nunca cria uma linha sozinha


def test_desemprego_pme_exige_ano_completo_e_pnadc_exige_4_trimestres(tmp_path):
    http = HttpPME(pme_completo(2010, 6.7) + pme_completo(2011, 6.0)[:11])  # 2011 incompleto
    ext = montar(
        {
            (6468, 1): [
                linha(2022, 11.0, periodo="202201"),
                linha(2022, 9.0, periodo="202202"),
                linha(2022, 8.0, periodo="202203"),
                linha(2022, 8.0, periodo="202204"),
                linha(2023, 8.4, periodo="202301"),  # só 1 trimestre: não fecha o ano
            ]
        },
        http=http,
        tmp_path=tmp_path,
    )
    d = ext.desemprego_anual()
    assert d[2010] == 6.7 and 2011 not in d
    assert d[2022] == 9.0 and 2023 not in d


def test_desemprego_pme_indisponivel_nao_derruba_a_extracao(tmp_path):
    ext = montar({(6468, 1): []}, tmp_path=tmp_path)
    assert ext.desemprego_anual() == {}


def test_indicadores_por_uf_so_com_dados_oficiais(tmp_path):
    ext = montar(
        {
            (7435, 3): [linha(2022, 0.49, uf=21)],  # MA
            (7113, 3): [linha(2022, 12.0, uf=21), linha(2022, 3.0, uf=35)],  # MA e SP
        },
        tmp_path=tmp_path,
    )
    registros = {(r["uf"], r["ano"]): r for r in ext.get_state_social_indicators()}
    assert registros[("MA", 2022)]["indice_gini"] == 0.49 and registros[("MA", 2022)]["taxa_analfabetismo_pct"] == 12.0
    assert registros[("SP", 2022)]["indice_gini"] is None and registros[("SP", 2022)]["taxa_analfabetismo_pct"] == 3.0
    assert all(r["is_synthetic"] is False for r in registros.values())
    assert ("AC", 2022) not in registros  # UF sem nenhum indicador: sem registro (nada de fator inventado)


def test_export_nao_sobrescreve_com_resultado_vazio(tmp_path):
    (tmp_path / "indicadores_sociais_anuais.json").write_text('[{"ano": 1}]', encoding="utf-8")
    ext = montar({}, tmp_path=tmp_path)
    assert ext.export() == {"total_anuais": 0, "total_uf_sociais": 0}
    assert (tmp_path / "indicadores_sociais_anuais.json").read_text(encoding="utf-8") == '[{"ano": 1}]'
