"""Testes do extrator da PNAD Contínua. Usa um microdado posicional SINTÉTICO montado no próprio teste."""

import io
import json
import urllib.error
import zipfile
from pathlib import Path

import numpy as np
import pytest

from etl.extractors import pnad_extractor as pnad
from etl.extractors.pnad_extractor import PNADError, PNADExtractor

# Dicionário no formato SAS do IBGE (colunas fora de ordem e com tipos misturados, como o original)
LAYOUT = """/* PROGRAMA DE LEITURA */
input
@0001 Ano   $4.   /* Ano */
@0006 UF   $2.   /* UF */
@0008 V2005   $2.   /* Condicao no domicilio */
@0010 V1032   10.   /* Peso */
@0020 VD4002   $1.   /* Ocupacao */
@0021 VD4019   8.   /* Rendimento trabalho */
@0029 VD5007   8.   /* Renda domiciliar */
@0037 VD5008   8.   /* Renda per capita */
"""


def _montar_linha(ano, uf, resp, peso, ocup, trabalho, total, per_capita):
    """Monta a linha respeitando EXATAMENTE as posições do LAYOUT acima (1-based)."""
    buf = [" "] * 60

    def poe(pos, largura, valor):
        texto = ("" if valor is None else str(valor)).ljust(largura)[:largura]
        for i, ch in enumerate(texto):
            buf[pos - 1 + i] = ch

    poe(1, 4, ano)
    poe(6, 2, uf)
    poe(8, 2, resp)
    poe(10, 10, peso)
    poe(20, 1, ocup)
    poe(21, 8, trabalho)
    poe(29, 8, total)
    poe(37, 8, per_capita)
    return "".join(buf)


SM = 1000.0
# (uf, resp, peso, ocup, trabalho, renda_total, per_capita)
PESSOAS = [
    ("35", "01", 100.0, "1", 3000, 3000, 3000),  # SP responsável: 3 SM domiciliar → faixa 2–4
    ("35", "02", 50.0, "1", 500, 3000, 3000),  # SP cônjuge ocupada com 0,5 SM → faixa [0,5; 1)
    ("29", "01", 200.0, "2", None, 0, 0),  # BA responsável sem rendimento → faixa 0
    ("29", "03", 100.0, "2", None, 0, 0),  # BA filho sem rendimento
    ("35", "01", 20.0, "1", 25000, 25000, 25000),  # SP responsável: 25 SM → mais de 20
    ("35", "06", 10.0, "2", None, None, None),  # pensionista: fora das bases domiciliares
]


def _microdado(ano="2024"):
    linhas = [_montar_linha(ano, *p[:2], p[2], *p[3:]) for p in PESSOAS]
    # ordem de parâmetros de _montar_linha: ano, uf, resp, peso, ocup, trabalho, total, per_capita
    return "\r\n".join(linhas) + "\r\n"


def _zip_bytes(conteudo: str, nome="PNADC_2024_visita5.txt") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(nome, conteudo.encode("latin-1"))
    return buf.getvalue()


@pytest.fixture
def limites_pequenos(monkeypatch):
    monkeypatch.setattr(pnad, "POPULACAO_MIN", 100)
    monkeypatch.setattr(pnad, "POPULACAO_MAX", 10_000)
    monkeypatch.setattr(pnad, "DOMICILIOS_MIN", 1)
    monkeypatch.setattr(pnad, "DOMICILIOS_MAX", 10_000)


# ---------------------------------------------------------------------------------------------- layout
def test_parse_layout_usa_posicoes_zero_based_e_largura():
    layout = pnad.parse_layout(LAYOUT)
    assert layout["Ano"] == (0, 4)
    assert layout["V1032"] == (9, 10)
    assert layout["VD5008"] == (36, 8)
    assert "input" not in layout


def test_colunas_do_layout_exige_todas_as_colunas():
    layout = pnad.parse_layout(LAYOUT)
    assert set(pnad.colunas_do_layout(layout)) == set(pnad.COLUNAS_NECESSARIAS)
    layout.pop("VD5007")
    with pytest.raises(PNADError, match="VD5007"):
        pnad.colunas_do_layout(layout)


def test_parse_layout_ignora_comentarios_e_linhas_sem_posicao():
    assert pnad.parse_layout("/* @0001 Fake $4. */\nnada aqui\n") == {}


# ---------------------------------------------------------------------------------------------- faixas
@pytest.mark.parametrize(
    "valor_sm, esperado",
    [
        (-1, 0),
        (0, 0),  # sem rendimento
        (0.01, 1),
        (0.4999, 1),
        (0.5, 2),  # fechado à esquerda: 0,5 já é a faixa seguinte
        (0.9999, 2),
        (1.0, 3),
        (1.99, 3),
        (2.0, 4),
        (3.99, 4),
        (4.0, 5),
        (9.99, 5),
        (10.0, 6),
        (19.99, 6),
        (20.0, 7),
        (500.0, 7),
    ],
)
def test_indice_faixa(valor_sm, esperado):
    assert int(pnad.indice_faixa(np.array([valor_sm]))[0]) == esperado


def test_faixas_e_bordas_sao_consistentes():
    assert len(pnad.FAIXAS) == pnad.N_FAIXAS == len(pnad.BORDAS_SM) + 2
    assert pnad.FAIXAS[0]["id"] == "sem_rendimento"


# ---------------------------------------------------------------------------------------------- leitura
def test_ler_blocos_extrai_colunas_e_converte_tipos():
    colunas = pnad.colunas_do_layout(pnad.parse_layout(LAYOUT))
    blocos = list(pnad._ler_blocos(io.BytesIO(_microdado().encode("latin-1")), colunas, tamanho_bloco=4))
    assert [len(b) for b in blocos] == [4, 2]  # blocos de 4 linhas
    df = blocos[0]
    assert df["Ano"].tolist() == ["2024"] * 4
    assert df["UF"].tolist() == ["35", "35", "29", "29"]
    assert df["V1032"].tolist() == [100.0, 50.0, 200.0, 100.0]
    assert np.isnan(df["VD4019"].iloc[2])  # em branco vira NaN, não zero
    assert df["VD5007"].iloc[2] == 0.0  # zero legítimo é preservado
    assert np.isnan(blocos[1]["VD5007"].iloc[1])  # pensionista sem renda domiciliar


def test_ler_blocos_ignora_linhas_em_branco():
    colunas = pnad.colunas_do_layout(pnad.parse_layout(LAYOUT))
    conteudo = "\r\n" + _microdado() + "\r\n   \r\n"
    total = sum(len(b) for b in pnad._ler_blocos(io.BytesIO(conteudo.encode("latin-1")), colunas))
    assert total == len(PESSOAS)


# ---------------------------------------------------------------------------------------------- ponderação
def test_processar_zip_pondera_pelo_peso_calibrado(tmp_path, limites_pequenos):
    zip_path = tmp_path / "PNADC_2024_visita5.zip"
    zip_path.write_bytes(_zip_bytes(_microdado()))
    res = pnad.processar_zip(zip_path, LAYOUT, SM, 2024)

    assert res["linhas_lidas"] == len(PESSOAS)
    assert res["populacao_total_estimada"] == 480  # soma de todos os pesos, inclusive o pensionista

    dom = res["nacional"]["domicilios_renda_total"]
    # responsáveis: SP 100 (3 SM → faixa 4), BA 200 (0 → faixa 0), SP 20 (25 SM → faixa 7)
    assert dom["total_estimado"] == 320
    assert dom["percentual"][4] == pytest.approx(31.25)
    assert dom["percentual"][0] == pytest.approx(62.5)
    assert dom["percentual"][7] == pytest.approx(6.25)
    assert sum(dom["percentual"]) == pytest.approx(100.0, abs=0.05)

    pessoas = res["nacional"]["pessoas_renda_domiciliar"]
    assert pessoas["total_estimado"] == 470  # o pensionista (peso 10) fica fora
    assert pessoas["percentual"][0] == pytest.approx(300 / 470 * 100, abs=0.01)

    ocupados = res["nacional"]["ocupados_renda_trabalho"]
    assert ocupados["total_estimado"] == 170  # 100 + 50 + 20, só VD4002 == '1'
    assert ocupados["percentual"][2] == pytest.approx(50 / 170 * 100, abs=0.01)  # 0,5 SM → [0,5; 1)
    assert ocupados["media_nominal_brl"] == pytest.approx((100 * 3000 + 50 * 500 + 20 * 25000) / 170, abs=0.01)


def test_processar_zip_agrega_por_uf(tmp_path, limites_pequenos):
    zip_path = tmp_path / "PNADC_2024_visita5.zip"
    zip_path.write_bytes(_zip_bytes(_microdado()))
    res = pnad.processar_zip(zip_path, LAYOUT, SM, 2024)
    assert set(res["uf"]) == {"SP", "BA"}
    assert res["uf"]["BA"]["domicilios_renda_total"]["percentual"][0] == pytest.approx(100.0)
    assert res["uf"]["BA"]["ocupados_renda_trabalho"] is None  # ninguém ocupado na BA
    assert res["uf"]["SP"]["domicilios_renda_total"]["total_estimado"] == 120


def test_processar_zip_rejeita_pesos_implausiveis(tmp_path):
    zip_path = tmp_path / "PNADC_2024_visita5.zip"
    zip_path.write_bytes(_zip_bytes(_microdado()))
    with pytest.raises(PNADError, match="fora do intervalo plausível"):
        pnad.processar_zip(zip_path, LAYOUT, SM, 2024)  # limites reais: 480 pessoas não é o Brasil


def test_processar_zip_rejeita_ano_divergente(tmp_path, limites_pequenos):
    zip_path = tmp_path / "PNADC_2024_visita5.zip"
    zip_path.write_bytes(_zip_bytes(_microdado(ano="2019")))
    with pytest.raises(PNADError, match="diferente"):
        pnad.processar_zip(zip_path, LAYOUT, SM, 2024)


def test_processar_zip_sem_txt(tmp_path):
    zip_path = tmp_path / "x.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("leia-me.pdf", b"x")
    with pytest.raises(PNADError, match="nenhum .txt"):
        pnad.processar_zip(zip_path, LAYOUT, SM, 2024)


# ---------------------------------------------------------------------------------------------- HTTP
class _Resp(io.BytesIO):
    def __init__(self, data: bytes, headers=None):
        super().__init__(data)
        self.headers = headers or {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(arquivos, chamadas=None, falhas=0):
    estado = {"falhas": falhas}

    def opener(req, timeout=None):
        url = req.full_url
        if chamadas is not None:
            chamadas.append((req.get_method(), url))
        if url not in arquivos:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        dado = arquivos[url]
        if req.get_method() == "GET" and estado["falhas"] > 0:
            estado["falhas"] -= 1
            return _Resp(dado[: len(dado) // 2], {"Content-Length": str(len(dado))})  # truncado
        return _Resp(dado)

    return opener


def test_baixar_arquivo_grava_atomicamente_e_reaproveita_cache(tmp_path):
    url = "https://x/PNADC_2024_visita5.zip"
    chamadas = []
    opener = _opener({url: b"conteudo"}, chamadas)
    destino = pnad.baixar_arquivo(url, tmp_path / "raw" / "a.zip", opener=opener)
    assert destino.read_bytes() == b"conteudo"
    assert not list((tmp_path / "raw").glob("*.part"))

    chamadas.clear()
    pnad.baixar_arquivo(url, destino, opener=opener)
    assert [m for m, _ in chamadas] == ["HEAD"]  # cache válido: não baixa de novo


def test_baixar_arquivo_refaz_download_truncado(tmp_path):
    url = "https://x/a.zip"
    opener = _opener({url: b"0123456789"}, falhas=2)
    destino = pnad.baixar_arquivo(url, tmp_path / "a.zip", opener=opener, espera=lambda s: None)
    assert destino.read_bytes() == b"0123456789"


def test_baixar_arquivo_desiste_depois_das_tentativas(tmp_path):
    url = "https://x/a.zip"
    opener = _opener({url: b"0123456789"}, falhas=10)
    with pytest.raises(PNADError, match="Não foi possível baixar"):
        pnad.baixar_arquivo(url, tmp_path / "a.zip", tentativas=2, opener=opener, espera=lambda s: None)
    assert not (tmp_path / "a.zip").exists()
    assert not list(tmp_path.glob("*.part"))


def test_baixar_arquivo_forca_novo_download_quando_cache_diverge(tmp_path):
    url = "https://x/a.zip"
    destino = tmp_path / "a.zip"
    destino.write_bytes(b"velho")
    pnad.baixar_arquivo(url, destino, opener=_opener({url: b"novo conteudo"}))
    assert destino.read_bytes() == b"novo conteudo"


def _listagens():
    base = pnad.BASE_URL.format(visita=5)
    dados = (
        '<a href="PNADC_2023_visita5_20250822.zip">z</a><a href="PNADC_2024_visita5.zip">z</a>'
        '<a href="PNADC_2025_visita5.zip">z</a>'
    )
    docs = '<a href="input_PNADC_2023_visita5_20250424.txt">i</a><a href="input_PNADC_2024_visita5.txt">i</a>'
    return base, {f"{base}/Dados/": dados.encode(), f"{base}/Documentacao/": docs.encode()}


def test_descobrir_arquivos_casa_zip_e_dicionario_por_ano():
    base, listagens = _listagens()
    achados = pnad.descobrir_arquivos(5, opener=_opener(listagens))
    assert sorted(achados) == [2023, 2024]  # 2025 não tem dicionário publicado → ignorado
    assert achados[2024] == {
        "zip": f"{base}/Dados/PNADC_2024_visita5.zip",
        "input": f"{base}/Documentacao/input_PNADC_2024_visita5.txt",
    }


def test_descobrir_arquivos_ftp_fora_do_ar():
    def opener(req, timeout=None):
        raise urllib.error.URLError("sem rede")

    with pytest.raises(PNADError, match="indisponível"):
        pnad.descobrir_arquivos(5, opener=opener)


# ---------------------------------------------------------------------------------------------- orquestração
@pytest.fixture
def ftp_falso(limites_pequenos):
    base, listagens = _listagens()
    arquivos = dict(listagens)
    for ano, nome_zip, nome_in in (
        (2023, "PNADC_2023_visita5_20250822.zip", "input_PNADC_2023_visita5_20250424.txt"),
        (2024, "PNADC_2024_visita5.zip", "input_PNADC_2024_visita5.txt"),
    ):
        arquivos[f"{base}/Dados/{nome_zip}"] = _zip_bytes(_microdado(str(ano)))
        arquivos[f"{base}/Documentacao/{nome_in}"] = LAYOUT.encode("latin-1")
    return arquivos


def test_run_grava_saida_com_proveniencia_e_e_idempotente(tmp_path, ftp_falso):
    chamadas = []
    saida = tmp_path / "out" / "pnad.json"
    ex = PNADExtractor(
        raw_dir=tmp_path / "raw",
        output_file=saida,
        opener=_opener(ftp_falso, chamadas),
        salarios_minimos={2023: 1000.0, 2024: 1000.0},
    )
    resultado = ex.run(anos=[2023, 2024])

    gravado = json.loads(saida.read_text(encoding="utf-8"))
    assert gravado["ano_mais_recente"] == 2024 and sorted(gravado["anos"]) == ["2023", "2024"]
    assert gravado["is_synthetic"] is False and "PNAD" in gravado["fonte"]  # aceito pelo loader/proveniência
    assert gravado["anos"]["2024"]["salario_minimo_brl"] == 1000.0
    assert gravado["anos"]["2024"]["arquivo_microdados"].endswith("PNADC_2024_visita5.zip")
    assert gravado["anos"]["2024"]["data_extracao"].endswith("Z")
    assert len(gravado["faixas"]) == pnad.N_FAIXAS and gravado["metodologia"]
    assert resultado["ano_mais_recente"] == 2024

    # Segunda execução: anos já extraídos do mesmo arquivo não são baixados nem recalculados
    chamadas.clear()
    ex.run(anos=[2023, 2024])
    assert not [c for c in chamadas if c[0] == "GET" and c[1].endswith(".zip")]


def test_run_ignora_ano_sem_salario_minimo(tmp_path, ftp_falso):
    ex = PNADExtractor(
        raw_dir=tmp_path / "raw",
        output_file=tmp_path / "pnad.json",
        opener=_opener(ftp_falso),
        salarios_minimos={2024: 1000.0},
    )
    ex.run(anos=[2023, 2024])
    assert sorted(json.loads((tmp_path / "pnad.json").read_text())["anos"]) == ["2024"]


def test_run_nao_cria_arquivo_quando_nenhum_ano_processa(tmp_path, ftp_falso):
    saida = tmp_path / "pnad.json"
    ex = PNADExtractor(raw_dir=tmp_path / "raw", output_file=saida, opener=_opener(ftp_falso), salarios_minimos={})
    with pytest.raises(PNADError, match="Nenhum ano processado"):
        ex.run(anos=[2024])
    assert not saida.exists()


def test_run_preserva_saida_anterior_quando_o_novo_ano_falha(tmp_path, ftp_falso, monkeypatch):
    saida = tmp_path / "pnad.json"
    ex = PNADExtractor(
        raw_dir=tmp_path / "raw",
        output_file=saida,
        opener=_opener(ftp_falso),
        salarios_minimos={2023: 1000.0, 2024: 1000.0},
    )
    ex.run(anos=[2023])
    antes = saida.read_text(encoding="utf-8")
    monkeypatch.setattr(pnad, "POPULACAO_MIN", 10**9)  # força a validação a reprovar 2024
    with pytest.raises(PNADError):
        ex.run(anos=[2023, 2024])
    assert saida.read_text(encoding="utf-8") == antes


def test_run_ano_nao_publicado(tmp_path, ftp_falso):
    ex = PNADExtractor(
        raw_dir=tmp_path / "raw", output_file=tmp_path / "p.json", opener=_opener(ftp_falso), salarios_minimos={}
    )
    with pytest.raises(PNADError, match="sem microdado publicado"):
        ex.run(anos=[1999])


def test_carregar_salarios_minimos(tmp_path):
    csv = tmp_path / "resumo.csv"
    csv.write_text("ano,salario_minimo\n2023,1320.0\n2024,1412.0\n2025,\n", encoding="utf-8")
    assert pnad.carregar_salarios_minimos(csv) == {2023: 1320.0, 2024: 1412.0}
    with pytest.raises(PNADError, match="ausente"):
        pnad.carregar_salarios_minimos(tmp_path / "nao_existe.csv")


def test_etapa_pnad_esta_no_cli():
    from etl.run_etl import construir_etapas, montar_parser

    etapas = construir_etapas(montar_parser().parse_args(["--pnad"]))
    assert [e.chave for e in etapas] == ["pnad"]
    assert "pnad" in [e.chave for e in construir_etapas(montar_parser().parse_args([]))]


def test_saida_real_do_repositorio_e_coerente():
    """Se o arquivo processado existe, ele precisa ter a estrutura que o backend consome."""
    arquivo = Path(pnad.OUTPUT_FILE)
    if not arquivo.exists():
        pytest.skip("pnad_faixas_salario_minimo.json ainda não gerado")
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    assert dados["is_synthetic"] is False and dados["fonte"]
    for ano, entrada in dados["anos"].items():
        assert entrada["ano"] == int(ano)
        for indicador in pnad.INDICADORES:
            assert len(entrada["nacional"][indicador]["percentual"]) == pnad.N_FAIXAS
            assert sum(entrada["nacional"][indicador]["percentual"]) == pytest.approx(100.0, abs=0.1)
