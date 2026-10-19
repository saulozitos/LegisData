"""CEAP: robustez da leitura da fonte (dtype, linhas malformadas), do cache (hardening, reserva vencida) e do saneamento."""

import io
import json
import zipfile
from datetime import date

import pytest

import etl.pipelines.sync_ceap_emendas as sync
from etl.pipelines.sync_ceap_emendas import CeapAccumulator
from etl.utils.http_client import HttpError

FONTES = {"DEPUTADO_FEDERAL": "camara", "SENADOR": "senado"}
CABECALHO = (
    "txNomeParlamentar;ideCadastro;sgUF;sgPartido;numAno;numMes;txtDescricao;vlrLiquido;txtFornecedor;txtCNPJCPF"
)


@pytest.fixture(autouse=True)
def sem_pausas(monkeypatch):
    monkeypatch.setattr(sync.time, "sleep", lambda _s: None)


def _zip(linhas, cabecalho=CABECALHO):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Ano-2023.csv", "\n".join([cabecalho, *linhas]) + "\n")
    return buf.getvalue()


class Camara:
    def __init__(self, conteudo):
        self.conteudo = conteudo

    def get_bytes(self, url, **kwargs):
        assert kwargs["max_bytes"] == sync.TETO_DO_DOWNLOAD
        return self.conteudo


def _camara(linhas, **kw):
    acc, ausentes = CeapAccumulator(), []
    total, falhas = sync.extract_camara_ceap(Camara(_zip(linhas, **kw)), [2023], acc, ausentes)
    return acc, total, falhas


def test_cnpj_so_de_digitos_com_zero_a_esquerda_nao_vira_float():
    acc, _, falhas = _camara(["ANA;123;SP;X;2023;1;COMB;10,5;POSTO;07575651000159".replace("10,5", "10.5")])
    (reg,) = acc.finalize(FONTES).values()
    assert falhas == [] and reg["fornecedores"]["POSTO"]["cnpj_cpf"] == "07575651000159"
    assert reg["camara_id"] == 123


def test_linha_sem_valor_numerico_fica_de_fora_sem_virar_gasto_zero(caplog):
    acc, _, falhas = _camara(
        ["ANA;123;SP;X;2023;1;COMB;10.5;POSTO;07575651000159", "ANA;123;SP;X;2023;1;COMB;;POSTO;07575651000159"]
    )
    (reg,) = acc.finalize(FONTES).values()
    assert falhas == [] and reg["total_gasto"] == 10.5 and reg["total_notas"] == 1
    assert "sem valor numérico" in caplog.text


def test_csv_com_coluna_renomeada_e_falha_do_ano():
    acc, _, falhas = _camara(
        ["ANA;123;SP;X;2023;1;COMB;10;POSTO;07575651000159"], cabecalho=CABECALHO.replace("vlrLiquido", "valor")
    )
    assert falhas == [2023] and acc.vazio


def test_zip_corrompido_e_falha_do_ano_e_nao_excecao():
    acc, ausentes = CeapAccumulator(), []
    total, falhas = sync.extract_camara_ceap(Camara(b"PK\x03\x04quebrado"), [2023], acc, ausentes)
    assert falhas == [2023] and acc.vazio


@pytest.mark.parametrize("corpo", [None, {"despesas": None}, {"outra": 1}, "texto"])
def test_senado_com_corpo_inesperado_e_falha_do_ano(corpo):
    class Cliente:
        def get_json(self, url, **kwargs):
            assert kwargs["max_bytes"] == sync.TETO_DO_DOWNLOAD
            return corpo

    acc = CeapAccumulator()
    _, falhas = sync.extract_senado_ceaps(Cliente(), [2023], acc)
    assert falhas == [2023] and acc.vazio


def test_senado_ignora_item_que_nao_e_objeto_e_valor_gigante():
    class Cliente:
        def get_json(self, url, **kwargs):
            return [
                1,
                {"codSenador": 1, "nomeSenador": "S", "valorReembolsado": 10**400},
                {"codSenador": 1, "nomeSenador": "S", "valorReembolsado": "7,5", "fornecedor": "F"},
            ]

    acc = CeapAccumulator()
    _, falhas = sync.extract_senado_ceaps(Cliente(), [2023], acc)
    (reg,) = acc.finalize(FONTES).values()
    assert falhas == [] and reg["total_gasto"] == 7.5


@pytest.mark.parametrize("valor", [None, True, "", "abc", float("nan"), float("inf"), 10**400, 10**14])
def test_num_devolve_none_para_o_que_nao_e_valor(valor):
    assert sync._num(valor) is None


def test_num_aceita_virgula_decimal_e_negativo():
    assert sync._num("1234,5") == 1234.5 and sync._num(-3) == -3.0


# ── Cache: forma, identificadores, saneamento e datas ───────────────────────────────────────────────────────────────
HOJE = date(2026, 10, 19)


def _payload(tmp_path):
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "COMB", "Posto", "02558157000162", 10.0)
    acc.add("SENADOR", 7, "Beto", 2023, 3, "PASSAGEM", "Cia", None, 100.0)
    sync._gravar_cache(tmp_path, "camara", 2023, acc, date(2026, 10, 1))
    return json.loads((tmp_path / "camara_2023.json").read_text(encoding="utf-8"))


def _com(payload, caminho, valor):
    alvo = payload
    for passo in caminho[:-1]:
        alvo = alvo[passo]
    alvo[caminho[-1]] = valor
    return payload


MUTACOES = {
    "versao_antiga": (["versao"], 1),
    "casa_trocada": (["casa"], "senado"),
    "ano_trocado": (["ano"], 2022),
    "gerado_em_invalido": (["gerado_em"], "ontem"),
    "gerado_em_futuro": (["gerado_em"], "2026-12-01"),
    "gerado_antes_de_fechar": (["gerado_em"], "2024-02-01"),
    "nome_vazio": (["dados", 0, "reg", "nome"], ""),
    "camara_id_trocado": (["dados", 0, "reg", "camara_id"], 99),
    "senado_id_em_deputado": (["dados", 0, "reg", "senado_id"], 1),
    "chave_com_bool": (["dados", 0, "chave"], ["SENADOR", True]),
    "por_tipo_invalido": (["dados", 0, "reg", "por_tipo"], {"X": "a"}),
    "por_ano_nulo": (["dados", 0, "reg", "por_ano"], None),
    "total_nan": (["dados", 0, "reg", "total_gasto"], "NaN"),
    "fornecedor_nome_nao_texto": (["dados", 0, "reg", "fornecedores", "Posto", "nome"], 5),
    "fornecedor_cpf_em_disco": (["dados", 0, "reg", "fornecedores", "Posto", "cnpj_cpf"], "12345678909"),
    "nome_com_cpf_em_disco": (["dados", 0, "reg", "nome"], "ANA"),
}


@pytest.mark.parametrize("caso", [c for c in MUTACOES if c != "nome_com_cpf_em_disco"])
def test_cache_com_um_campo_adulterado_e_recusado(tmp_path, caso):
    caminho, valor = MUTACOES[caso]
    payload = _com(_payload(tmp_path), caminho, valor)
    (tmp_path / "camara_2023.json").write_text(json.dumps(payload), encoding="utf-8")
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


def test_o_cache_sem_adulteracao_e_aceito(tmp_path):
    _payload(tmp_path)
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is not None


def test_cache_com_chave_repetida_e_recusado(tmp_path):
    payload = _payload(tmp_path)
    payload["dados"].append(payload["dados"][0])
    (tmp_path / "camara_2023.json").write_text(json.dumps(payload), encoding="utf-8")
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


def test_cache_com_nome_de_fornecedor_com_cpf_e_recusado(tmp_path):
    payload = _payload(tmp_path)
    reg = payload["dados"][0]["reg"]
    reg["fornecedores"] = {"JOSE 12345678909": {**reg["fornecedores"]["Posto"], "nome": "JOSE 12345678909"}}
    (tmp_path / "camara_2023.json").write_text(json.dumps(payload), encoding="utf-8")
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


def test_cache_com_inteiro_gigante_e_recusado_sem_excecao(tmp_path):
    payload = _payload(tmp_path)
    texto = json.dumps(payload).replace('"total_gasto": 10.0', '"total_gasto": ' + "9" * 400, 1)
    (tmp_path / "camara_2023.json").write_text(texto, encoding="utf-8")
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


def test_cache_vencido_so_serve_como_reserva(tmp_path):
    _payload(tmp_path)
    muito_depois = date(2027, 6, 1)
    assert sync._ler_cache(tmp_path, "camara", 2023, muito_depois) is None
    assert sync._ler_cache(tmp_path, "camara", 2023, muito_depois, aceitar_vencido=True) is not None


def test_cache_vencido_e_usado_quando_a_baixa_falha_e_o_resumo_avisa(tmp_path):
    _payload(tmp_path)

    class Falha:
        def __call__(self, http, anos, acc, ausentes=None):
            return 0, list(anos)

    acc = CeapAccumulator()
    r = sync._extrair_anos(None, [2023], "camara", Falha(), acc, tmp_path, date(2027, 6, 1))
    assert r.cache_vencido == [2023] and r.falhas == [] and not acc.vazio


# ── Começo do ano: o vazio só vale se o ano ainda não tinha sido publicado ──────────────────────────────────────────
class Vazio:
    def __init__(self, ausente=False):
        self.ausente, self.chamadas = ausente, 0

    def __call__(self, http, anos, acc, ausentes=None):
        self.chamadas += 1
        if self.ausente:
            ausentes.append(anos[0])
            return 0, list(anos)
        return 0, []


@pytest.mark.parametrize("ausente", [False, True])
def test_ano_corrente_que_ja_tinha_dados_e_volta_vazio_em_janeiro_e_falha(tmp_path, ausente):
    r = sync._extrair_anos(None, [2027], "camara", Vazio(ausente), CeapAccumulator(), None, date(2027, 1, 10), {2027})
    assert r.falhas == [2027] and r.sem_arquivo == []


@pytest.mark.parametrize("hoje, esperado", [(date(2027, 3, 31), [2027]), (date(2027, 4, 1), [])])
def test_o_vazio_do_ano_novo_vale_ate_marco(hoje, esperado):
    r = sync._extrair_anos(None, [2027], "senado", Vazio(), CeapAccumulator(), None, hoje)
    assert r.sem_arquivo == esperado


def test_anos_publicados_no_arquivo_le_os_anos_com_gasto_por_casa(tmp_path):
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "X", "F", None, 10.0)
    acc.add("SENADOR", 7, "Beto", 2024, 1, "X", "F", None, 10.0)
    arquivo = tmp_path / "ceap.json"
    arquivo.write_text(json.dumps(acc.finalize(FONTES)), encoding="utf-8")
    assert sync.anos_publicados_no_arquivo(arquivo) == {"camara": {2023}, "senado": {2024}}
    assert sync.anos_publicados_no_arquivo(tmp_path / "nao_existe.json") == {"camara": set(), "senado": set()}


# ── Resumo e injeção de http ────────────────────────────────────────────────────────────────────────────────────────
def test_fontes_nao_gravadas_usa_lista_positiva():
    assert sync.fontes_nao_gravadas({"ceap_gravado": True, "emendas_gravado": True}) == []
    assert sync.fontes_nao_gravadas({"ceap_gravado": False, "emendas_gravado": True}) == ["ceap"]
    assert sync.fontes_nao_gravadas({"emendas_gravado": False}) == ["emendas"]  # a ceap não foi pedida
    assert sync.fontes_nao_gravadas({}) == []


def test_run_repassa_o_http_injetado_ao_extrator_de_emendas(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    recebido = []

    class Falso:
        def __init__(self, http=None, **_):
            recebido.append(http)

        def fetch_portal(self):
            return []

    monkeypatch.setattr(sync, "EmendasExtractor", Falso)
    cliente = object()
    sync.run(2023, 2023, ceap=False, http=cliente, hoje=HOJE)
    assert recebido == [cliente]


def test_erro_inesperado_numa_fonte_nao_impede_a_outra(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)

    def quebra(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(sync, "_sincronizar_ceap", quebra)

    class Falso:
        def __init__(self, http=None):
            pass

        def fetch_portal(self):
            return [{"ano": 2023, "codigo": 1}]

    monkeypatch.setattr(sync, "EmendasExtractor", Falso)
    resumo = sync.run(2023, 2023, hoje=HOJE)
    assert resumo["ceap_gravado"] is False and "boom" in resumo["ceap_erro"] and resumo["emendas_gravado"] is True


def test_http_error_404_nao_e_confundido_com_outro_status():
    class Cliente:
        def get_bytes(self, url, **kwargs):
            raise HttpError(url, 500, "x")

    ausentes = []
    _, falhas = sync.extract_camara_ceap(Cliente(), [2023], CeapAccumulator(), ausentes)
    assert falhas == [2023] and ausentes == []


# ── Emendas: o mesmo teto e os mesmos erros de leitura do ZIP ──────────────────────────────────────────────────────
def test_o_teto_do_csv_e_um_so_e_cabe_no_conteiner_de_2_gb():
    from etl import config
    from etl.extractors import emendas_extractor

    assert emendas_extractor.TETO_DO_CSV is config.TETO_DO_CSV and sync.TETO_DO_CSV is config.TETO_DO_CSV
    assert config.TETO_DO_CSV <= 512 * 1024 * 1024  # o CSV vira bytes, texto e DataFrame ao mesmo tempo (várias cópias)
    assert config.TETO_DO_CSV > 82 * 1024 * 1024  # e o maior CSV real (Câmara 2023, 82 MB) cabe com folga


@pytest.mark.parametrize("erro", [__import__("zlib").error("corrompido"), EOFError("cortado")])
def test_emendas_zip_corrompido_no_meio_devolve_lista_vazia_em_vez_de_excecao(erro, monkeypatch):
    from etl.extractors.emendas_extractor import EmendasExtractor

    class Cliente:
        def get_bytes(self, url, **kwargs):
            return b"x"

    monkeypatch.setattr("etl.extractors.emendas_extractor.zipfile.ZipFile", lambda *a, **k: (_ for _ in ()).throw(erro))
    assert EmendasExtractor(http=Cliente()).fetch_portal() == []


def test_hoje_no_brasil_e_a_data_de_brasilia_e_nao_a_do_utc(monkeypatch):
    from datetime import datetime, timedelta, timezone

    class RelogioFalso(datetime):
        @classmethod
        def now(cls, tz=None):
            utc = datetime(
                2027, 4, 1, 1, 30, tzinfo=timezone.utc
            )  # 31/03 22:30 em Brasília: o ano de 2026 ainda não fechou
            return utc.astimezone(tz) if tz else utc

    monkeypatch.setattr(sync, "datetime", RelogioFalso)
    assert sync.hoje_no_brasil() == date(2027, 3, 31)
    assert sync.FUSO_DO_BRASIL.utcoffset(None) == timedelta(hours=-3)
    assert not sync._definitivo(2026, sync.hoje_no_brasil())


def test_o_arquivo_versionado_da_ceap_nao_tem_cpf_em_documento_nem_em_nome():
    """D3: o retrato do git também não pode carregar CPF (a primeira atualização diária o regrava, mas o git o serve antes)."""
    import re

    from etl.pipelines.loader_helpers import cnpj_do_fornecedor, nome_do_fornecedor

    arquivo = sync.PROCESSED_DATA_DIR / sync.CEAP_OUTPUT
    for parlamentar, dados in json.loads(arquivo.read_text(encoding="utf-8")).items():
        for forn in dados["fornecedores"].values():
            documento = forn["cnpj_cpf"]
            assert documento is None or len(re.sub(r"\D", "", documento)) == 14, (parlamentar, forn["nome"])
            assert documento is None or cnpj_do_fornecedor(documento) is not None, (parlamentar, forn["nome"])
            assert nome_do_fornecedor(forn["nome"]) == forn["nome"], (parlamentar, forn["nome"])
