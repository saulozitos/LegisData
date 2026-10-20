"""CEAP: robustez da leitura da fonte (dtype, linhas malformadas), do cache (hardening, reserva vencida) e do saneamento."""

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

import etl.pipelines.sync_ceap_emendas as sync
from etl.pipelines.sync_ceap_emendas import CeapAccumulator
from etl.tests.sinteticos import CPF_A, CPF_B
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
    acc, _, falhas = _camara(["ANA;123;SP;X;2023;1;COMB;10.5;POSTO;07575651000159"])
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
    acc.add("DEPUTADO_FEDERAL", 2, "Beto", 2023, 3, "PASSAGEM", "Cia", None, 100.0)
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
    "fornecedor_cpf_em_disco": (["dados", 0, "reg", "fornecedores", "Posto", "cnpj_cpf"], CPF_B),
}


@pytest.mark.parametrize("caso", list(MUTACOES))
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
    reg["fornecedores"] = {f"JOSE {CPF_B}": {**reg["fornecedores"]["Posto"], "nome": f"JOSE {CPF_B}"}}
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
def test_ano_corrente_que_ja_tinha_dados_e_volta_vazio_em_janeiro_e_falha(ausente):
    extrator = Vazio(ausente)
    r = sync._extrair_anos(None, [2027], "camara", extrator, CeapAccumulator(), None, date(2027, 1, 10), {2027})
    assert r.falhas == [2027] and r.sem_arquivo == []
    assert extrator.chamadas == (1 if ausente else 2)  # 404 não ganha nova tentativa; o vazio ganha uma


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
def test_fontes_gravadas_e_nao_gravadas_sao_complementares_e_positivas():
    for resumo, gravadas in [
        ({"ceap_gravado": True, "emendas_gravado": True}, ["ceap", "emendas"]),
        ({"ceap_gravado": False, "emendas_gravado": True}, ["emendas"]),
        ({"emendas_gravado": True}, ["emendas"]),  # sem resposta da ceap: não gravou
        ({"ceap_gravado": 1, "emendas_gravado": "sim"}, []),  # só `True` conta
        ({}, []),
    ]:
        assert sync.fontes_gravadas(resumo) == gravadas, resumo
        assert sync.fontes_nao_gravadas(resumo) == [f for f in sync.FONTES if f not in gravadas], resumo


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


# ── Fornecedores homônimos, texto vazio e nome em branco ────────────────────────────────────────────────────────────
def test_mei_homonimo_com_cnpj_diferente_nao_se_funde_e_cada_um_guarda_o_seu_cnpj():
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "T", "JOAO DA SILVA 09876543200", "11222333000181", 10.0)
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 2, "T", f"JOAO DA SILVA {CPF_A}", "02558157000162", 5.0)
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 3, "T", "JOAO DA SILVA", "02558157000162", 1.0)  # volta ao segundo
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 4, "T", "JOAO DA SILVA", None, 2.0)  # sem documento: soma no primeiro
    (reg,) = acc.finalize(FONTES).values()
    forn = reg["fornecedores"]
    assert forn["JOAO DA SILVA"] == {"nome": "JOAO DA SILVA", "cnpj_cpf": "11222333000181", "total": 12.0, "notas": 2}
    assert forn["JOAO DA SILVA [02558157000162]"]["total"] == 6.0
    assert forn["JOAO DA SILVA [02558157000162]"]["cnpj_cpf"] == "02558157000162"


def test_homonimos_tambem_ficam_separados_ao_mesclar_anos_e_voltam_do_cache(tmp_path):
    a, b = CeapAccumulator(), CeapAccumulator()
    a.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "T", "JOAO", "11222333000181", 10.0)
    b.add("DEPUTADO_FEDERAL", 1, "Ana", 2024, 1, "T", "JOAO", "02558157000162", 5.0)
    b.add("DEPUTADO_FEDERAL", 1, "Ana", 2024, 2, "T", "JOAO", "11222333000181", 1.0)
    a.mesclar(b)
    sync._gravar_cache(tmp_path, "camara", 2023, a, date(2026, 10, 1))
    lido = sync._ler_cache(tmp_path, "camara", 2023, HOJE)
    assert lido is not None
    (reg,) = lido.finalize(FONTES).values()
    assert reg["fornecedores"]["JOAO"]["total"] == 11.0
    assert reg["fornecedores"]["JOAO [02558157000162]"]["total"] == 5.0


def test_chave_de_fornecedor_que_nao_bate_com_nome_e_documento_invalida_o_cache(tmp_path):
    payload = _payload(tmp_path)
    forns = payload["dados"][0]["reg"]["fornecedores"]
    forns["OUTRO NOME"] = forns.pop("Posto")
    (tmp_path / "camara_2023.json").write_text(json.dumps(payload), encoding="utf-8")
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


def test_celula_vazia_nao_vira_o_texto_nan_nem_cria_parlamentar_fantasma():
    acc, _, falhas = _camara(
        [
            "ANA;123;SP;X;2023;1;;10.0;;07575651000159",  # descrição e fornecedor vazios
            ";;SP;X;2023;1;COMB;5.0;POSTO;07575651000159",  # sem nome e sem identificador: não é de ninguém
        ]
    )
    (reg,) = acc.finalize(FONTES).values()
    assert falhas == [] and reg["nome"] == "ANA"
    assert set(reg["por_tipo"]) == {"OUTROS"} and set(reg["fornecedores"]) == {"Não informado"}
    assert "nan" not in json.dumps(acc.para_json()).lower()


def test_nome_so_de_espacos_e_descartado_e_o_que_se_grava_volta_do_cache(tmp_path):
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", None, "   ", 2023, 1, "T", "F", None, 10.0)
    assert acc.vazio
    acc.add("DEPUTADO_FEDERAL", None, "  ana  ", 2023, 1, "T", "F", None, 10.0)
    sync._gravar_cache(tmp_path, "camara", 2023, acc, date(2026, 10, 1))
    lido = sync._ler_cache(tmp_path, "camara", 2023, HOJE)
    assert lido is not None and lido.para_json() == acc.para_json()


def test_cache_com_cargo_de_outra_casa_e_recusado(tmp_path):
    acc = CeapAccumulator()
    acc.add("SENADOR", 7, "Beto", 2023, 1, "T", "F", None, 10.0)
    sync._gravar_cache(tmp_path, "camara", 2023, acc, date(2026, 10, 1))
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


# ── Anos já publicados: do arquivo anterior e do fin ────────────────────────────────────────────────────────────────
def _extratores_que_nao_acham_2027(monkeypatch):
    """2026 vem com gasto; 2027 responde 404 nas duas casas."""

    def para(cargo, ident):
        def extrator(http, anos, acc, ausentes=None):
            if anos[0] == 2027:
                ausentes.append(2027)
                return 0, [2027]
            acc.add(cargo, ident, "Fulano", anos[0], 1, "T", "F", None, 1.0)
            return 1, []

        return extrator

    monkeypatch.setattr(sync, "extract_camara_ceap", para("DEPUTADO_FEDERAL", 1))
    monkeypatch.setattr(sync, "extract_senado_ceaps", para("SENADOR", 7))


def test_run_nao_apaga_o_ano_corrente_que_o_arquivo_anterior_ja_tinha(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    anterior = CeapAccumulator()
    anterior.add("DEPUTADO_FEDERAL", 1, "Ana", 2027, 1, "T", "F", None, 10.0)
    anterior.add("SENADOR", 7, "Beto", 2027, 1, "T", "F", None, 10.0)
    arquivo = tmp_path / sync.CEAP_OUTPUT
    arquivo.write_text(json.dumps(anterior.finalize(FONTES)), encoding="utf-8")
    original = arquivo.read_text(encoding="utf-8")
    _extratores_que_nao_acham_2027(monkeypatch)
    resumo = sync.run(2026, 2027, emendas=False, http=object(), hoje=date(2027, 1, 10))
    assert resumo["ceap_gravado"] is False and resumo["ceap_falhas"] == {"camara": [2027], "senado": [2027]}
    assert arquivo.read_text(encoding="utf-8") == original


def test_run_usa_tambem_os_anos_que_o_fin_informa_quando_o_arquivo_foi_revertido(tmp_path, monkeypatch):
    """O deploy devolve o arquivo ao retrato do git (sem 2027); quem sabe que 2027 existe é o `fin`."""
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    _extratores_que_nao_acham_2027(monkeypatch)
    sem = sync.run(2026, 2027, emendas=False, http=object(), hoje=date(2027, 1, 10))
    assert sem["ceap_gravado"] is True and sem["ceap_anos_sem_arquivo"] == {"camara": [2027], "senado": [2027]}
    com = sync.run(
        2026,
        2027,
        emendas=False,
        http=object(),
        hoje=date(2027, 1, 10),
        anos_publicados={"camara": {2027}, "senado": {2027}},
    )
    assert com["ceap_gravado"] is False and com["ceap_falhas"] == {"camara": [2027], "senado": [2027]}


def test_anos_publicados_ignora_so_o_registro_ruim_e_avisa(tmp_path, caplog):
    arquivo = tmp_path / "ceap.json"
    arquivo.write_text(
        json.dumps(
            {
                "RUIM": {"cargo": "SENADOR", "por_ano": None},
                "RUIM2": {"cargo": "SENADOR", "por_ano": {"2023.0": 5}},
                "NAN": {"cargo": "SENADOR", "por_ano": {"2021": float("nan")}},
                "BOM": {"cargo": "DEPUTADO_FEDERAL", "por_ano": {"2024": 10.0, "2023": 0}},
                "LIXO": 5,
            }
        ),
        encoding="utf-8",
    )
    assert sync.anos_publicados_no_arquivo(arquivo) == {"camara": {2024}, "senado": set()}
    assert "ilegíveis" in caplog.text


# ── Resumo: cache vencido e erro das emendas ────────────────────────────────────────────────────────────────────────
def test_run_avisa_no_resumo_o_ano_servido_pelo_cache_vencido(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path / "saida")
    (tmp_path / "saida").mkdir()
    cache = tmp_path / "cache"
    _payload(cache)  # camara_2023, gerado em 2026-10-01

    def falha(http, anos, acc, ausentes=None):
        return 0, list(anos)

    monkeypatch.setattr(sync, "extract_camara_ceap", falha)
    monkeypatch.setattr(sync, "extract_senado_ceaps", Vazio())
    resumo = sync.run(2023, 2023, emendas=False, http=object(), cache_dir=cache, hoje=date(2027, 6, 1))
    # o Senado volta vazio (falha do ano) e derruba a gravação, mas o aviso do cache vencido da Câmara consta
    assert resumo["ceap_anos_cache_vencido"] == {"camara": [2023]}


def test_erro_inesperado_das_emendas_nao_impede_a_ceap_e_fica_no_resumo(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)

    def ok(http, anos, acc, ausentes=None):
        acc.add("DEPUTADO_FEDERAL", 1, "Ana", anos[0], 1, "T", "F", None, 1.0)
        return 1, []

    monkeypatch.setattr(sync, "extract_camara_ceap", ok)

    def ok_senado(http, anos, acc, ausentes=None):
        acc.add("SENADOR", 7, "B", anos[0], 1, "T", "F", None, 1.0)
        return 1, []

    monkeypatch.setattr(sync, "extract_senado_ceaps", ok_senado)

    class Quebra:
        def __init__(self, http=None):
            pass

        def fetch_portal(self):
            raise RuntimeError("portal")

    monkeypatch.setattr(sync, "EmendasExtractor", Quebra)
    resumo = sync.run(2023, 2023, http=object(), hoje=HOJE)
    assert resumo["ceap_gravado"] is True and resumo["emendas_gravado"] is False and "portal" in resumo["emendas_erro"]


def test_casas_do_congresso_sao_as_mesmas_nos_dois_lados_do_contrato_dos_anos_publicados():
    from etl.config import CASAS_DO_CONGRESSO
    from etl.pipelines import financas_loader

    assert set(sync.CASA_DO_CARGO.values()) == set(CASAS_DO_CONGRESSO) == set(financas_loader._CASA_DA_FONTE.values())
    # mapeamentos por nome, nunca por posição: reordenar a tupla não pode trocar a Câmara pelo Senado
    fontes = {financas_loader.FONTE_CEAP_CAMARA: "camara", financas_loader.FONTE_CEAP_SENADO: "senado"}
    assert financas_loader._CASA_DA_FONTE == fontes
    assert sync.PAUSA_POR_CASA == {"camara": 10.0, "senado": 1.0}
    assert set(sync.anos_publicados_no_arquivo(Path("/nao/existe.json"))) == set(CASAS_DO_CONGRESSO)


def test_o_arquivo_tem_o_ano_e_o_fin_nao_a_uniao_protege_o_ano(tmp_path, monkeypatch):
    """A carga falhou depois de o arquivo receber 2027: o `fin` não tem o ano, o arquivo tem; um 404 não pode apagá-lo."""
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    anterior = CeapAccumulator()
    anterior.add("DEPUTADO_FEDERAL", 1, "Ana", 2027, 1, "T", "F", None, 10.0)
    anterior.add("SENADOR", 7, "Beto", 2027, 1, "T", "F", None, 10.0)
    arquivo = tmp_path / sync.CEAP_OUTPUT
    arquivo.write_text(json.dumps(anterior.finalize(FONTES)), encoding="utf-8")
    _extratores_que_nao_acham_2027(monkeypatch)
    resumo = sync.run(
        2026,
        2027,
        emendas=False,
        http=object(),
        hoje=date(2027, 1, 10),
        anos_publicados={"camara": set(), "senado": set()},  # o fin respondeu, e sem o ano
    )
    assert resumo["ceap_gravado"] is False and resumo["ceap_falhas"] == {"camara": [2027], "senado": [2027]}


@pytest.mark.parametrize(
    "erro", [NotImplementedError("compressão"), RuntimeError("File is encrypted"), RecursionError()]
)
def test_zip_cifrado_ou_com_compressao_nao_suportada_e_falha_do_ano_e_nao_derruba_o_run(erro):
    class Cliente:
        def get_bytes(self, url, **kwargs):
            raise erro

    acc = CeapAccumulator()
    _, falhas = sync.extract_camara_ceap(Cliente(), [2023], acc)
    assert falhas == [2023] and acc.vazio


def test_validador_nao_aceita_a_chave_com_none_literal(tmp_path):
    payload = _payload(tmp_path)
    forns = payload["dados"][0]["reg"]["fornecedores"]
    forn = forns.pop("Posto")
    forn["cnpj_cpf"] = None
    forns["Posto [None]"] = forn
    (tmp_path / "camara_2023.json").write_text(json.dumps(payload), encoding="utf-8")
    assert sync._ler_cache(tmp_path, "camara", 2023, HOJE) is None


def test_ignorar_cache_baixa_de_novo_regrava_o_cache_e_ainda_usa_a_reserva_vencida(tmp_path):
    cache = tmp_path / "cache"
    _payload(cache)  # camara_2023 válido (gerado em 2026-10-01)
    chamadas = []

    def extrator(http, anos, acc, ausentes=None):
        chamadas.append(list(anos))
        acc.add("DEPUTADO_FEDERAL", 1, "Ana", anos[0], 1, "T", "F", None, 99.0)
        return 1, []

    r = sync._extrair_anos(
        None, [2023], "camara", extrator, CeapAccumulator(), cache, date(2026, 10, 2), ignorar_cache=True
    )
    assert chamadas == [[2023]] and r.baixados == 1 and r.do_cache == []  # o cache válido foi ignorado
    regravado = sync._ler_cache(cache, "camara", 2023, date(2026, 10, 2))
    assert regravado.para_json()[0]["reg"]["total_gasto"] == 99.0  # e o cache foi regravado com o dado novo

    def falha(http, anos, acc, ausentes=None):
        return 0, list(anos)

    acc = CeapAccumulator()
    r2 = sync._extrair_anos(None, [2023], "camara", falha, acc, cache, date(2027, 6, 1), ignorar_cache=True)
    assert r2.cache_vencido == [2023] and r2.falhas == [] and not acc.vazio  # a reserva vencida continua valendo


def test_documento_zero_mais_cpf_que_fecha_como_cnpj_sai_do_acumulador_e_o_cache_com_ele_e_recusado_qualquer_que_seja_o_nome():
    """Uma regra só, sem desempate por nome: nem "X LTDA" nem "JOSE DE SA" mantêm o documento ambíguo, na gravação e no cache."""
    from etl.tests.sinteticos import zero_mais_cpf_que_fecha_como_cnpj

    [ambiguo] = zero_mais_cpf_que_fecha_como_cnpj()
    for fornecedor in ("FORNECEDOR EXEMPLO LTDA", "JOSE DE SA", "BANCO X S.A."):
        acc = CeapAccumulator()
        acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2024, 1, "T", fornecedor, ambiguo, 10.0)
        [item] = acc.para_json()
        assert item["reg"]["fornecedores"][fornecedor]["cnpj_cpf"] is None
        item["reg"]["fornecedores"] = {
            f"{fornecedor} [{ambiguo}]": {"nome": fornecedor, "cnpj_cpf": ambiguo, "total": 10.0, "notas": 1}
        }
        with pytest.raises(ValueError, match="saneamento"):
            CeapAccumulator.de_json([item])
