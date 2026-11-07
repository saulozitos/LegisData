"""CPF só como HMAC: cálculo, validação e o gerador de identificadores (nunca o número em arquivo ou banco)."""

import json

import pytest

from etl.extractors import cpf_extractor
from etl.utils import cpf as cpf_util
from etl.utils.names import normalize_plain

CPF = "52998224725"  # CPF válido de exemplo (dígitos verificadores conferem)


@pytest.fixture()
def com_chave(monkeypatch):
    monkeypatch.setattr(cpf_util, "_chave", lambda: b"chave-de-teste")


def test_cpf_valido_confere_digitos_e_recusa_mascaras_do_tse():
    assert cpf_util.cpf_valido("529.982.247-25") == CPF
    for ruim in ("52998224726", "11111111111", "-4", "-1", "", None, "123"):
        assert cpf_util.cpf_valido(ruim) is None


def test_identificador_e_hmac_com_chave_e_nunca_o_proprio_cpf(com_chave):
    h = cpf_util.identificador_cpf("529.982.247-25")
    assert h == cpf_util.identificador_cpf(CPF) and len(h) == 64 and CPF not in h
    assert cpf_util.identificador_cpf("52998224726") is None  # CPF inválido


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
            "39053344705",
        },  # dois CPFs para o mesmo par: ambíguo
    }
    identidades = _Identidades({"camara:1": {"cpf": "39053344705"}})
    resultado = cpf_extractor.gerar(tmp_path, tmp_path, indice=indice, identidades=identidades)
    texto = (tmp_path / cpf_extractor.SAIDA).read_text(encoding="utf-8")
    saida = {(i["id_tipo"], i["id_valor"]): i for i in json.loads(texto)}
    assert set(saida) == {("CAMARA_ID", "1"), ("SENADO_ID", "9")} and resultado["gerados"] == 2
    assert saida[("SENADO_ID", "9")]["origem"] == "TSE" and saida[("CAMARA_ID", "1")]["origem"] == "CAMARA_API"
    assert CPF not in texto and "39053344705" not in texto  # nenhum CPF no arquivo


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
