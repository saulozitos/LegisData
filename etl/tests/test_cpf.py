"""CPF só como HMAC: cálculo, validação e o gerador de identificadores (nunca o número em arquivo ou banco)."""

import json

import pytest

from etl.extractors import cpf_extractor
from etl.tests.sinteticos import CPF_A, CPF_A_INVALIDO, CPF_B, formatado
from etl.utils import cpf as cpf_util
from etl.utils.names import normalize_plain

CPF = CPF_A  # CPF sintético válido, calculado na hora (D3: nunca por extenso)


@pytest.fixture()
def com_chave(monkeypatch):
    monkeypatch.setattr(cpf_util, "_chave", lambda: b"chave-de-teste")


def test_cpf_valido_confere_digitos_e_recusa_mascaras_do_tse():
    assert cpf_util.cpf_valido(formatado(CPF)) == CPF
    for ruim in (CPF_A_INVALIDO, "11111111111", "-4", "-1", "", None, "123"):
        assert cpf_util.cpf_valido(ruim) is None


def test_identificador_e_hmac_com_chave_e_nunca_o_proprio_cpf(com_chave):
    h = cpf_util.identificador_cpf(formatado(CPF))
    assert h == cpf_util.identificador_cpf(CPF) and len(h) == 64 and CPF not in h
    assert cpf_util.identificador_cpf(CPF_A_INVALIDO) is None  # CPF inválido


def test_sem_chave_nada_e_calculado(monkeypatch):
    monkeypatch.setattr(cpf_util, "_chave", lambda: b"")
    assert cpf_util.identificador_cpf(CPF) is None and not cpf_util.chave_configurada()


def test_chaves_diferentes_dao_valores_diferentes(monkeypatch):
    monkeypatch.setattr(cpf_util, "_chave", lambda: b"a")
    a = cpf_util.identificador_cpf(CPF)
    monkeypatch.setattr(cpf_util, "_chave", lambda: b"b")
    assert a != cpf_util.identificador_cpf(CPF)


class _Identidades:
    def __init__(self, dados):
        self.dados = dados

    def enrich(self, camara, senado):
        return 0

    def get(self, chave):
        return self.dados.get(chave)


def test_gerador_liga_deputado_pela_camara_e_senador_pelo_tse_e_omite_par_ambiguo(com_chave, tmp_path):
    (tmp_path / "deputados_camara.json").write_text(
        json.dumps([{"camara_id": 1, "nome_civil": "ANA"}]), encoding="utf-8"
    )
    (tmp_path / "senadores_senado.json").write_text(
        json.dumps(
            [
                {"senado_id": 9, "nome_civil": "Beto da Silva", "data_nascimento": "1960-01-02"},
                {"senado_id": 10, "nome_civil": "Caio Homonimo", "data_nascimento": "1970-03-04"},
            ]
        ),
        encoding="utf-8",
    )
    from datetime import date

    indice = {
        (normalize_plain("Beto da Silva"), date(1960, 1, 2)): {CPF},
        (normalize_plain("Caio Homonimo"), date(1970, 3, 4)): {
            CPF,
            CPF_B,
        },  # dois CPFs para o mesmo par: ambíguo
    }
    identidades = _Identidades({"camara:1": {"cpf": CPF_B}})
    resultado = cpf_extractor.gerar(tmp_path, tmp_path, indice=indice, identidades=identidades)
    texto = (tmp_path / cpf_extractor.SAIDA).read_text(encoding="utf-8")
    saida = {(i["id_tipo"], i["id_valor"]): i for i in json.loads(texto)}
    assert set(saida) == {("CAMARA_ID", "1"), ("SENADO_ID", "9")} and resultado["gerados"] == 2
    assert saida[("SENADO_ID", "9")]["origem"] == "TSE" and saida[("CAMARA_ID", "1")]["origem"] == "CAMARA_API"
    assert CPF not in texto and CPF_B not in texto  # nenhum CPF no arquivo


def test_gerador_sem_chave_nao_grava_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(cpf_util, "_chave", lambda: b"")
    assert cpf_extractor.gerar(tmp_path, tmp_path, indice={}, identidades=_Identidades({}))["gerados"] == 0
    assert not (tmp_path / cpf_extractor.SAIDA).exists()


class _HttpSenado:
    """Resposta do detalhe `/senador/{codigo}`; o código 2 não informa nascimento."""

    def get_json(self, url, *args, **kwargs):
        codigo = int(url.rsplit("/", 1)[1].split(".")[0])
        basicos = (
            {"DataNascimento": "1943-06-21", "Naturalidade": "Itirapuã", "UfNaturalidade": "SP"} if codigo == 1 else {}
        )
        return {
            "DetalheParlamentar": {
                "Parlamentar": {
                    "IdentificacaoParlamentar": {
                        "NomeCompletoParlamentar": f"Nome Completo {codigo}",
                        "SexoParlamentar": "Masculino",
                    },
                    "DadosBasicosParlamentar": basicos,
                }
            }
        }


def test_dados_basicos_do_senado_viram_pessoa_e_cpf_pelo_nome_e_nascimento(tmp_path, com_chave):
    from etl.carga.pessoas import Lote, ler_senadores_basicos
    from etl.extractors import senadores_basicos_extractor as sb
    from etl.extractors.presenca_extractor import ARQ_RESUMO

    (tmp_path / ARQ_RESUMO).write_text(
        json.dumps(
            {
                "resumos": [
                    {"casa": "SENADO", "parlamentar_id": 1, "nome": "Um"},
                    {"casa": "SENADO", "parlamentar_id": 2, "nome": "Dois"},
                ]
            }
        ),
        encoding="utf-8",
    )
    assert sb.gerar(tmp_path, _HttpSenado()) == {"senadores": 2, "baixados": 2}
    assert sb.gerar(tmp_path, _HttpSenado())["baixados"] == 0  # o que já foi baixado não é pedido de novo

    lote = Lote()
    ler_senadores_basicos(lote, tmp_path)
    um, dois = lote.pessoas[("SENADO_ID", "1")], lote.pessoas[("SENADO_ID", "2")]
    assert (um["nome_civil"], str(um["data_nascimento"])) == ("Nome Completo 1", "1943-06-21")
    assert dois["data_nascimento"] is None  # desconhecido é nulo

    indice = {(normalize_plain("Nome Completo 1"), cpf_extractor.parse_date("1943-06-21")): {CPF}}
    cpf_extractor.gerar(tmp_path, tmp_path, consultar_apis=False, indice=indice)
    gerado = json.loads((tmp_path / "cpf_identificadores.json").read_text(encoding="utf-8"))
    assert [(g["id_tipo"], g["id_valor"]) for g in gerado] == [("SENADO_ID", "1")]
    assert CPF not in json.dumps(gerado)


# ── chave curta, índice do TSE com CPF mascarado, senadores básicos e filiações ───────────────────────────────────────
def test_chave_curta_demais_e_tratada_como_nao_configurada(monkeypatch):
    from app.core.config import settings

    cpf_util._chave.cache_clear()
    try:
        monkeypatch.setattr(settings, "CPF_HMAC_KEY", "curta")
        assert cpf_util._chave() == b"" and cpf_util.identificador_cpf(CPF) is None
        cpf_util._chave.cache_clear()
        monkeypatch.setattr(settings, "CPF_HMAC_KEY", "x" * cpf_util.TAMANHO_MINIMO_DA_CHAVE)
        assert cpf_util.chave_configurada() and cpf_util.identificador_cpf(CPF)
    finally:
        cpf_util._chave.cache_clear()


def test_indice_do_tse_so_guarda_cpf_valido_e_ignora_mascara_e_vazio(tmp_path):
    from datetime import date

    from etl.tests.test_tse_extractors import CAND_COLS, cand_row, zip_csv

    zip_csv(
        tmp_path / "consulta_cand_2022.zip",
        {
            "consulta_cand_2022_BRASIL.csv": (
                CAND_COLS,
                [
                    cand_row(1, "Fulano de Tal", "Fulano", cpf=CPF, nasc="01/01/1980"),
                    cand_row(2, "Beltrano Qualquer", "Beltrano", cpf="-4", nasc="02/02/1975"),  # máscara do TSE
                    cand_row(3, "Sicrano Outro", "Sicrano", cpf="", nasc="03/03/1970"),  # sem CPF
                ],
            )
        },
    )
    indice = cpf_extractor.indice_do_tse(anos=[2022], raw_dir=tmp_path)
    assert indice == {(normalize_plain("Fulano de Tal"), date(1980, 1, 1)): {CPF}}


class _HttpSenadoVariado:
    """Detalhe do senador com respostas diferentes por código: completo, sem nome, sem nascimento ou fora do ar."""

    def __init__(self):
        self.pedidos = []

    def get_json(self, url, *args, **kwargs):
        from etl.utils.http_client import HttpError

        codigo = int(url.rsplit("/", 1)[1].split(".")[0])
        self.pedidos.append(codigo)
        if codigo == 8:
            raise HttpError(url, 503, "fora do ar")
        identificacao = {} if codigo == 3 else {"NomeCompletoParlamentar": f"Nome {codigo}"}
        basicos = {} if codigo == 3 else {"DataNascimento": "1950-05-05"}
        return {
            "DetalheParlamentar": {
                "Parlamentar": {"IdentificacaoParlamentar": identificacao, "DadosBasicosParlamentar": basicos}
            }
        }


def test_senadores_basicos_cobre_votos_e_anteriores_refaz_o_que_veio_sem_nome_e_nao_inventa_na_falha(tmp_path):
    import gzip

    from etl.extractors import senadores_basicos_extractor as sb

    pasta = tmp_path / "votacoes"
    pasta.mkdir()
    with gzip.open(pasta / "senado_2022.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"parlamentares": {"5": {"nome": "Cinco"}, "3": {"nome": "Tres"}, "8": {"nome": "Oito"}}}, fh)
    (tmp_path / "parlamentares_legislaturas_anteriores.json").write_text(
        json.dumps(
            {
                "senadores": [
                    {"senado_id": 6, "nome_eleitoral": "Seis"},  # sem nascimento: entra
                    {"senado_id": 7, "nome_eleitoral": "Sete", "data_nascimento": "1950-01-01"},  # já tem: fica de fora
                    {"nome_eleitoral": "Sem Codigo"},  # sem código não tem como pedir ao Senado
                ]
            }
        ),
        encoding="utf-8",
    )
    http = _HttpSenadoVariado()
    assert sb.gerar(tmp_path, http) == {"senadores": 4, "baixados": 4}
    assert sorted(http.pedidos) == [3, 5, 6, 8]
    registros = {s["senado_id"]: s for s in sb.ler_senadores_basicos(tmp_path)}
    assert registros[5]["nome_civil"] == "Nome 5" and registros[5]["data_nascimento"] == "1950-05-05"
    assert (
        "nome_civil" not in registros[3] and "data_nascimento" not in registros[3]
    )  # a fonte não informou: nada inventado
    assert "nome_civil" not in registros[8]  # API fora do ar: desconhecido, não chute

    http2 = _HttpSenadoVariado()
    assert sb.gerar(tmp_path, http2)["baixados"] == 2
    assert sorted(http2.pedidos) == [3, 8]  # só o que ficou sem nome é pedido de novo


class _HttpFiliacoes:
    def __init__(self):
        self.pedidos = []

    def get_json(self, url, *args, **kwargs):
        from etl.utils.http_client import HttpError

        codigo = int(url.rsplit("/", 2)[1])
        self.pedidos.append(codigo)
        if codigo == 3:
            raise HttpError(url, 503, "fora do ar")
        filiacoes = {
            1: [  # em curso: a lista vem do mais recente ao mais antigo
                {"Partido": {"SiglaPartido": "PL"}, "DataFiliacao": "2021-04-08"},
                {"Partido": {"SiglaPartido": "PODE"}, "DataFiliacao": "2017-07-04", "DataDesfiliacao": "2021-04-07"},
            ],
            2: {"Partido": {"SiglaPartido": "PSB"}, "DataFiliacao": "2003-02-01", "DataDesfiliacao": "2010-12-31"},
        }.get(codigo, [])
        return {"FiliacaoParlamentar": {"Parlamentar": {"Codigo": str(codigo), "Filiacoes": {"Filiacao": filiacoes}}}}


def test_filiacoes_dos_senadores_so_repetem_o_pedido_de_quem_tem_filiacao_em_curso_ou_falhou(tmp_path):
    from etl.extractors import senadores_filiacoes_extractor as sf

    (tmp_path / "senadores_senado.json").write_text(
        json.dumps([{"senado_id": 1}, {"senado_id": 2}, {"senado_id": 3}]), encoding="utf-8"
    )
    http = _HttpFiliacoes()
    assert sf.gerar(tmp_path, http) == {"senadores": 2, "baixados": 3, "sem_resposta": 1}
    registros = {s["senado_id"]: s["filiacoes"] for s in sf.ler_filiacoes(tmp_path)}
    assert registros[1][0] == {"sigla": "PL", "inicio": "2021-04-08", "fim": None}
    assert registros[2] == [{"sigla": "PSB", "inicio": "2003-02-01", "fim": "2010-12-31"}]  # um só item vira lista
    assert 3 not in registros  # falhou: sem registro, nunca filiação inventada
    http2 = _HttpFiliacoes()
    assert sf.gerar(tmp_path, http2)["baixados"] == 2
    assert sorted(http2.pedidos) == [1, 3]  # a filiação encerrada de 2 não é pedida de novo
