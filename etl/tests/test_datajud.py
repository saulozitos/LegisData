"""Testes para a integração oficial com a API do DataJud (CNJ)."""

import json
from datetime import datetime, timedelta

import pytest

from etl.utils.datajud_client import (
    CACHE_NEGATIVO_DIAS,
    DataJudClient,
    ErroDoDataJud,
    deduzir_aliases_datajud,
    parse_cnj_parts,
)


def test_parse_cnj_parts_formatado():
    res = parse_cnj_parts("0600814-85.2022.6.00.0000")
    assert res is not None
    assert res["sequencial"] == "0600814"
    assert res["digito"] == "85"
    assert res["ano"] == "2022"
    assert res["segmento"] == "6"
    assert res["tribunal"] == "00"
    assert res["origem"] == "0000"
    assert res["limpo"] == "06008148520226000000"
    assert res["formatado"] == "0600814-85.2022.6.00.0000"


def test_parse_cnj_parts_limpo():
    res = parse_cnj_parts("06008148520226000000")
    assert res is not None
    assert res["limpo"] == "06008148520226000000"
    assert res["formatado"] == "0600814-85.2022.6.00.0000"


def test_parse_cnj_parts_invalido():
    assert parse_cnj_parts("123") is None
    assert parse_cnj_parts("Inq 4878 / DF") is None


def test_deduzir_aliases_datajud():
    # TSE
    p_tse = parse_cnj_parts("0600814-85.2022.6.00.0000")
    assert "api_publica_tse" in deduzir_aliases_datajud(p_tse)

    # TRE-PR
    p_tre = parse_cnj_parts("0604176-51.2022.6.16.0000")
    assert "api_publica_tre-pr" in deduzir_aliases_datajud(p_tre)

    # TRF-1
    p_trf1 = parse_cnj_parts("1026137-89.2019.4.01.3400")
    assert "api_publica_trf1" in deduzir_aliases_datajud(p_trf1)

    # STJ
    p_stj = parse_cnj_parts("0000001-00.2020.3.00.0000")
    assert "api_publica_stj" in deduzir_aliases_datajud(p_stj)


@pytest.mark.parametrize(
    "numero, alias",
    [
        ("1000000-00.2020.8.26.0100", "api_publica_tjsp"),  # 8.26 é o TJSP
        ("1000000-00.2020.8.25.0001", "api_publica_tjse"),  # 8.25 é o TJSE
        ("0600000-00.2022.6.26.0001", "api_publica_tre-sp"),
        ("0600000-00.2022.6.25.0001", "api_publica_tre-se"),
        ("1000000-00.2020.8.19.0001", "api_publica_tjrj"),
        ("1000000-00.2020.8.07.0001", "api_publica_tjdft"),
        ("1000000-00.2020.8.27.0001", "api_publica_tjto"),
        ("1000000-00.2020.9.26.0001", "api_publica_tjmsp"),  # Justiça Militar estadual: a mesma numeração por UF
        ("1000000-00.2020.9.13.0001", "api_publica_tjmmg"),
        ("1000000-00.2020.9.21.0001", "api_publica_tjmrs"),
    ],
)
def test_alias_da_justica_estadual_e_eleitoral_segue_a_tabela_da_resolucao_65(numero, alias):
    assert alias in deduzir_aliases_datajud(parse_cnj_parts(numero))


def test_consolidar_resumo_processo():
    sample_source = {
        "numeroProcesso": "06008148520226000000",
        "tribunal": "TSE",
        "grau": "SUP",
        "dataAjuizamento": "2022-08-19T14:30:55.000Z",
        "classe": {"codigo": 11527, "nome": "Ação de Investigação Judicial Eleitoral"},
        "assuntos": [{"codigo": 11682, "nome": "Abuso de Poder"}],
        "orgaoJulgador": {"codigo": 100, "nome": "Plenário do TSE"},
        "movimentos": [
            {"dataHora": "2023-06-30T12:00:00.000Z", "nome": "Julgamento de Mérito - Procedência"},
            {"dataHora": "2022-08-20T10:00:00.000Z", "nome": "Distribuição"},
        ],
    }
    summary = DataJudClient.consolidar_resumo_processo(sample_source)
    assert summary["numero_processo"] == "06008148520226000000"
    assert summary["tribunal"] == "TSE"
    assert summary["classe_tpu_nome"] == "Ação de Investigação Judicial Eleitoral"
    assert "Abuso de Poder" in summary["classe_assunto"]
    assert summary["data_processo"] == "2022-08-19"
    assert summary["total_movimentacoes"] == 2
    assert summary["ultimo_movimento"] == "Julgamento de Mérito - Procedência"
    assert summary["is_synthetic"] is False


# ── consultar_processo: "não existe" é diferente de "o DataJud não respondeu" ─────────────────────────────────────────

CNJ = "0000001-78.2020.8.26.0100"  # TJSP: um só alias candidato (api_publica_tjsp)


class _Resposta:
    def __init__(self, status=200, corpo=None, texto="", invalido=False):
        self.status_code = status
        self._corpo = corpo
        self.text = texto
        self._invalido = invalido

    def json(self):
        if self._invalido:
            raise ValueError("corpo ilegível")
        return self._corpo


class _Sessao:
    """Devolve as respostas na ordem; uma exceção na lista é levantada."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def post(self, *_args, **_kwargs):
        self.chamadas += 1
        atual = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        if isinstance(atual, Exception):
            raise atual
        return atual


def _cliente(tmp_path, monkeypatch, *respostas):
    monkeypatch.setattr("etl.utils.datajud_client.time.sleep", lambda _s: None)
    cliente = DataJudClient(raw_dir=tmp_path)
    cliente.session = _Sessao(*respostas)
    return cliente


def _com_hit(fonte):
    return _Resposta(corpo={"hits": {"hits": [{"_source": fonte}]}})


SEM_HIT = _Resposta(corpo={"hits": {"hits": []}})


def test_processo_localizado_volta_e_fica_em_cache(tmp_path, monkeypatch):
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "x"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "x"}
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "x"}
    assert cliente.session.chamadas == 1  # a segunda saiu do cache


def test_resposta_sem_hit_e_nao_encontrado_e_nao_erro(tmp_path, monkeypatch):
    cliente = _cliente(tmp_path, monkeypatch, SEM_HIT)
    assert cliente.consultar_processo(CNJ) is None


@pytest.mark.parametrize(
    "resposta",
    [
        _Resposta(status=503, texto="indisponível"),
        _Resposta(status=401, texto="chave inválida"),
        _Resposta(status=429),  # as três tentativas terminam em 429
        _Resposta(invalido=True),  # 200 com corpo ilegível
        _Resposta(corpo={"hits": {"hits": [{"_source": None}]}}),  # hit sem documento
        TimeoutError("lento"),
    ],
)
def test_falha_do_datajud_levanta_erro_em_vez_de_virar_nao_encontrado(tmp_path, monkeypatch, resposta):
    cliente = _cliente(tmp_path, monkeypatch, resposta)
    with pytest.raises(ErroDoDataJud, match="api_publica_tjsp"):
        cliente.consultar_processo(CNJ)
    assert not list(tmp_path.rglob("*.json"))  # falha nunca vira "não encontrado" em cache


def test_erro_transitorio_seguido_de_sucesso_na_mesma_consulta_nao_levanta(tmp_path, monkeypatch):
    cliente = _cliente(tmp_path, monkeypatch, TimeoutError("lento"), _com_hit({"numeroProcesso": "x"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "x"}


def test_inconclusivo_em_um_tribunal_e_sem_hit_no_outro_levanta_erro(tmp_path, monkeypatch):
    # justiça eleitoral de um estado: o TRE e depois o TSE
    cliente = _cliente(tmp_path, monkeypatch, _Resposta(status=503), SEM_HIT)
    with pytest.raises(ErroDoDataJud, match="api_publica_tre-pr"):
        cliente.consultar_processo("0604176-51.2022.6.16.0000")


def test_achado_em_um_tribunal_vale_mesmo_com_o_outro_fora_do_ar(tmp_path, monkeypatch):
    cliente = _cliente(tmp_path, monkeypatch, _Resposta(status=503), _com_hit({"numeroProcesso": "x"}))
    assert cliente.consultar_processo("0604176-51.2022.6.16.0000") == {"numeroProcesso": "x"}


def _plantar_miss(tmp_path, idade_dias):
    caminho = tmp_path / "datajud" / "api_publica_tjsp" / "00000017820208260100.json"
    caminho.parent.mkdir(parents=True)
    quando = (datetime.now() - timedelta(days=idade_dias)).isoformat()
    caminho.write_text(
        json.dumps({"found": False, "fetched_at": quando, "alias": "api_publica_tjsp"}), encoding="utf-8"
    )


def test_nao_encontrado_recente_nao_repete_a_consulta(tmp_path, monkeypatch):
    _plantar_miss(tmp_path, idade_dias=1)
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "x"}))
    assert cliente.consultar_processo(CNJ) is None
    assert cliente.session.chamadas == 0


def test_nao_encontrado_vencido_consulta_de_novo_e_acha_o_processo_indexado_depois(tmp_path, monkeypatch):
    _plantar_miss(tmp_path, idade_dias=CACHE_NEGATIVO_DIAS + 1)
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "x"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "x"}
    assert cliente.session.chamadas == 1


def test_data_ilegivel_no_cache_negativo_conta_como_vencido(tmp_path, monkeypatch):
    caminho = tmp_path / "datajud" / "api_publica_tjsp" / "00000017820208260100.json"
    caminho.parent.mkdir(parents=True)
    caminho.write_text(json.dumps({"found": False, "fetched_at": "ontem"}), encoding="utf-8")
    cliente = _cliente(tmp_path, monkeypatch, SEM_HIT)
    assert cliente.consultar_processo(CNJ) is None
    assert cliente.session.chamadas == 1


def test_numero_fora_do_padrao_cnj_nao_consulta(tmp_path, monkeypatch):
    cliente = _cliente(tmp_path, monkeypatch, SEM_HIT)
    assert cliente.consultar_processo("Pet 12100 / DF") is None
    assert cliente.session.chamadas == 0


# ── consolidar_resumo_processo: nada inventado, nada quebra ───────────────────────────────────────────────────────────


def test_resumo_sem_classe_nao_inventa_uma():
    resumo = DataJudClient.consolidar_resumo_processo({"numeroProcesso": "1", "assuntos": [{"nome": "A"}]})
    assert resumo["classe_tpu_nome"] is None and resumo["classe_assunto"] is None
    assert (
        resumo["ultimo_movimento"] is None and resumo["orgao_julgador"] is None and resumo["total_movimentacoes"] == 0
    )


@pytest.mark.parametrize("classe", [None, "texto", 7, [], {}, {"nome": None}, {"nome": ""}, {"nome": 5}])
def test_resumo_com_classe_de_tipo_inesperado_fica_sem_classe(classe):
    assert DataJudClient.consolidar_resumo_processo({"classe": classe})["classe_tpu_nome"] is None


def test_resumo_tolera_movimento_sem_data_ou_malformado_e_assunto_sem_nome():
    resumo = DataJudClient.consolidar_resumo_processo(
        {
            "classe": {"nome": "Classe"},
            "assuntos": [{"nome": "A"}, {"nome": None}, {"nome": 7}, "x", None],
            "movimentos": [
                {"dataHora": None, "nome": "Sem data"},
                {"dataHora": "2024-05-06T10:00:00", "nome": "Conclusão"},
                {"dataHora": 20240101, "nome": "Número"},
                "x",
                None,
            ],
        }
    )
    assert resumo["assuntos_tpu"] == ["A"] and resumo["classe_assunto"] == "Classe / A"
    assert resumo["ultimo_movimento"] == "Número" or resumo["ultimo_movimento"] == "Conclusão"
    assert resumo["total_movimentacoes"] == 3  # só os dicionários contam


@pytest.mark.parametrize("campo", ["movimentos", "assuntos", "orgaoJulgador", "classe"])
@pytest.mark.parametrize("valor", ["texto", 5, True, {"a": 1}, [[]]])
def test_resumo_nunca_levanta_para_campo_de_tipo_inesperado(campo, valor):
    DataJudClient.consolidar_resumo_processo({campo: valor})


def test_resumo_expoe_o_nivel_de_sigilo_para_quem_decide_publicar():
    assert DataJudClient.consolidar_resumo_processo({"nivelSigilo": 2})["nivel_sigilo"] == 2
    assert DataJudClient.consolidar_resumo_processo({})["nivel_sigilo"] is None
