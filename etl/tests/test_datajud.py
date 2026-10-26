"""Testes para a integração oficial com a API do DataJud (CNJ)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from etl.utils.datajud_client import (
    CACHE_NEGATIVO_DIAS,
    CACHE_POSITIVO_DIAS,
    DataJudClient,
    ErroDoDataJud,
    _dia_do_datajud,
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
    assert summary["data_ultimo_movimento"] == "2023-06-30"
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


def _plantar_cache(tmp_path, idade_dias, found=False, fetched_at=None, **extra):
    caminho = tmp_path / "datajud" / "api_publica_tjsp" / "00000017820208260100.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    quando = fetched_at if fetched_at is not None else (datetime.now() - timedelta(days=idade_dias)).isoformat()
    caminho.write_text(
        json.dumps({"found": found, "fetched_at": quando, "alias": "api_publica_tjsp", **extra}), encoding="utf-8"
    )


def _plantar_miss(tmp_path, idade_dias):
    _plantar_cache(tmp_path, idade_dias)


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


def test_nao_encontrado_gravado_pelo_cliente_e_lido_de_volta_sem_nova_consulta(tmp_path, monkeypatch):
    cliente = _cliente(tmp_path, monkeypatch, SEM_HIT)
    assert cliente.consultar_processo(CNJ) is None
    assert cliente.consultar_processo(CNJ) is None
    assert cliente.session.chamadas == 1  # o formato que o cliente grava é o que ele lê


@pytest.mark.parametrize(
    "quando",
    [
        "ontem",  # ilegível
        "",
        "None",  # o que `str(None)` dá quando a chave falta
        "2024-01-01T00:00:00+00:00",  # com fuso e antigo: vencido, sem TypeError ao comparar com o relógio local
        "2999-01-01T00:00:00",  # no futuro: ainda "recente" (o relógio local é a referência)
    ],
)
def test_data_do_cache_ilegivel_ou_com_fuso_e_tratada_sem_quebrar(tmp_path, monkeypatch, quando):
    _plantar_cache(tmp_path, 0, fetched_at=quando)
    cliente = _cliente(tmp_path, monkeypatch, SEM_HIT)
    assert cliente.consultar_processo(CNJ) is None
    esperado = 0 if quando == "2999-01-01T00:00:00" else 1
    assert cliente.session.chamadas == esperado


def test_data_com_fuso_recente_no_cache_vale(tmp_path, monkeypatch):
    agora = datetime.now(timezone.utc).isoformat()
    _plantar_cache(tmp_path, 0, found=True, fetched_at=agora, source={"numeroProcesso": "cache"})
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "rede"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "cache"} and cliente.session.chamadas == 0


def test_achado_recente_sai_do_cache(tmp_path, monkeypatch):
    _plantar_cache(tmp_path, 0, found=True, source={"numeroProcesso": "cache"})
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "rede"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "cache"} and cliente.session.chamadas == 0


def test_achado_vencido_e_consultado_de_novo_para_o_andamento_nao_ficar_congelado(tmp_path, monkeypatch):
    _plantar_cache(tmp_path, CACHE_POSITIVO_DIAS + 1, found=True, source={"numeroProcesso": "antigo"})
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "novo"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "novo"} and cliente.session.chamadas == 1


def test_achado_vencido_com_o_datajud_fora_do_ar_levanta_erro_em_vez_de_servir_o_antigo(tmp_path, monkeypatch):
    _plantar_cache(tmp_path, CACHE_POSITIVO_DIAS + 1, found=True, source={"numeroProcesso": "antigo"})
    cliente = _cliente(tmp_path, monkeypatch, _Resposta(status=503))
    with pytest.raises(ErroDoDataJud):
        cliente.consultar_processo(CNJ)


def test_cache_de_achado_sem_documento_e_ignorado(tmp_path, monkeypatch):
    _plantar_cache(tmp_path, 0, found=True, source=None)
    cliente = _cliente(tmp_path, monkeypatch, _com_hit({"numeroProcesso": "rede"}))
    assert cliente.consultar_processo(CNJ) == {"numeroProcesso": "rede"}


def test_mesmo_numero_em_varios_graus_vale_o_documento_atualizado_mais_recentemente(tmp_path, monkeypatch):
    numero = "00000017820208260100"
    g2 = {"numeroProcesso": numero, "grau": "G2", "dataHoraUltimaAtualizacao": "2024-03-01T10:00:00.000Z"}
    g1 = {"numeroProcesso": numero, "grau": "G1", "dataHoraUltimaAtualizacao": "2024-07-01T10:00:00.000Z"}
    sem_data = {"numeroProcesso": numero, "grau": "JE"}
    outro = {
        "numeroProcesso": "99999999999999999999",
        "grau": "G9",
        "dataHoraUltimaAtualizacao": "2030-01-01T00:00:00Z",
    }
    resposta = _Resposta(corpo={"hits": {"hits": [{"_source": x} for x in (g2, sem_data, outro, g1)]}})
    cliente = _cliente(tmp_path, monkeypatch, resposta)
    assert cliente.consultar_processo(CNJ)["grau"] == "G1"  # nem a ordem da busca, nem o documento de outro número


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
    # a data numérica (2024-01-01) é anterior a 2024-05-06: a ordem é cronológica, não a do texto ('0' > '-' em ASCII)
    assert resumo["ultimo_movimento"] == "Conclusão" and resumo["data_ultimo_movimento"] == "2024-05-06"
    assert resumo["total_movimentacoes"] == 3  # só os dicionários contam


@pytest.mark.parametrize("campo", ["movimentos", "assuntos", "orgaoJulgador", "classe"])
@pytest.mark.parametrize("valor", ["texto", 5, True, {"a": 1}, [[]]])
def test_resumo_nunca_levanta_para_campo_de_tipo_inesperado(campo, valor):
    resumo = DataJudClient.consolidar_resumo_processo({campo: valor})
    # nada é inventado: o que não se lê fica vazio
    assert resumo["classe_tpu_nome"] is None and resumo["classe_assunto"] is None
    assert resumo["orgao_julgador"] is None and resumo["assuntos_tpu"] == []
    assert resumo["ultimo_movimento"] is None and resumo["total_movimentacoes"] == 0


@pytest.mark.parametrize(
    "valor, dia",
    [
        ("2018-10-29T00:00:00.000Z", "2018-10-29"),  # meia-noite UTC é como o DataJud escreve uma data sem hora
        ("2019-05-30T01:15:00Z", "2019-05-29"),  # 01:15 UTC ainda é 29/05 em Brasília
        ("2019-05-30T12:00:00.000Z", "2019-05-30"),
        ("2024-05-06T10:00:00", "2024-05-06"),  # sem fuso: já é horário de Brasília
        ("2024-05-06", "2024-05-06"),
        ("20180309000000", "2018-03-09"),  # formato compacto de alguns tribunais
        ("20180309", "2018-03-09"),
        (20240101, "2024-01-01"),
        ("ontem", None),
        ("2024-02-30", None),
        ("", None),
        (None, None),
        (True, None),
        (1.5, None),
    ],
)
def test_dia_do_datajud_em_horario_de_brasilia(valor, dia):
    assert _dia_do_datajud(valor) == dia


def test_resumo_com_data_ilegivel_fica_sem_data_em_vez_de_vazia():
    resumo = DataJudClient.consolidar_resumo_processo(
        {"dataAjuizamento": "ontem", "movimentos": [{"dataHora": "sem data", "nome": "X"}]}
    )
    assert resumo["data_processo"] is None and resumo["data_ultimo_movimento"] is None
    assert resumo["ultimo_movimento"] == "X"


def test_resumo_expoe_o_nivel_de_sigilo_para_quem_decide_publicar():
    assert DataJudClient.consolidar_resumo_processo({"nivelSigilo": 2})["nivel_sigilo"] == 2
    assert DataJudClient.consolidar_resumo_processo({})["nivel_sigilo"] is None
