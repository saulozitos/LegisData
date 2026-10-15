"""Presença em plenário e remuneração: parsers, extratores (HTTP falso), cliente educado e cargas (SQLite)."""

import gzip
import json
import urllib.error
from datetime import date, datetime
from decimal import Decimal

import pytest
from app.models import (
    AttendanceRecord,
    Base,
    CargoPoliticoEnum,
    CasaLegislativaEnum,
    Mandate,
    PoliticalParty,
    Politician,
    PoliticianRemuneration,
    TipoPresencaEnum,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.extractors import presenca_extractor as pe
from etl.extractors import remuneracao_extractor as re_
from etl.pipelines import load_attendance_and_remuneration as loader
from etl.utils.http_client import HttpError
from etl.utils.io_utils import EmptyResultError
from etl.utils.provenance import SYNTHETIC_TAG


# ------------------------------------------------------------------------------------------------ fixtures HTML
def pagina_presenca(dias, sessoes=(), resumo=None, nome="Fulano"):
    """Reproduz o markup do relatório oficial: linhas de dia, linhas de sessão e a tabela de resumo."""
    linhas = []
    for data, rotulo in dias:
        linhas.append(
            f'<tr class="info-data"><td class="info-data__data-formatada">{data} '
            f'<span class="info-presenca-dia">{rotulo}</span></td><td>&nbsp;</td>'
            f'<td class="info-presenca-dia">\n   {rotulo}\n  </td></tr>'
        )
    for data, rotulo in sessoes:
        linhas.append(
            f'<tr class="info-data__child"><td><span class="ml-3">EXTRAORDINÁRIA Nº 001 - {data}</span></td>'
            f'<td>\n {rotulo} Observações ?\n</td><td class="info-presenca-dia">&nbsp;</td></tr>'
        )
    rodape = ""
    if resumo:
        rodape = (
            '<table><tbody><tr class="info-data"><td><strong>2024</strong></td><td></td><td></td></tr>'
            f"<tr><td><b>Total de sessões deliberativas com Ordem do Dia iniciada, na Sessão Legislativa*</b></td>"
            f"<td><strong>{resumo['sessoes']}</strong></td><td>100,00%</td></tr>"
            f"<tr><td><b>Total de ausências não justificadas em sessões deliberativas com Ordem do Dia iniciada*</b></td>"
            f"<td><strong>{resumo['aus_sessoes']}</strong></td><td>1,00%</td></tr>"
            f"<tr><td><b>Total de dias com sessões deliberativas realizadas no período</b></td><td>{resumo['dias']}</td></tr>"
            f"<tr><td><b>Total de dias com presença nas sessões deliberativas</b></td><td>{resumo['pres']}</td></tr>"
            f"<tr><td><b>Total de dias com ausências justificadas em sessões deliberativas</b></td><td>{resumo['just']}</td></tr>"
            f"<tr><td><b>Total de dias com ausências não justificadas em sessões deliberativas</b></td>"
            f"<td>{resumo['nao_just']}</td></tr></tbody></table>"
        )
    return (
        f"<html><body><h1>Presença em Plenário do Deputado(a) {nome}</h1><table><tbody>"
        + "".join(linhas)
        + "</tbody></table>"
        + rodape
        + "</body></html>"
    )


DIAS_PAGINA = [
    ("06/02/2024", "Presença"),
    ("20/02/2024", "Ausência"),
    ("27/02/2024", "Missão Autorizada"),
    ("28/02/2024", "Presença (~)"),
    ("05/03/2024", "Licença para Tratamento de Saúde"),
    ("06/03/2024", "Decisão da Mesa"),
]
RESUMO_PAGINA = {"sessoes": 7, "aus_sessoes": 1, "dias": 6, "pres": 2, "just": 3, "nao_just": 1}


class HttpFalso:
    """Substitui o HttpClient: respostas por URL (exata ou prefixo) e registro das chamadas."""

    def __init__(self, respostas):
        self.respostas = respostas
        self.chamadas = []

    def _achar(self, url):
        self.chamadas.append(url)
        for chave, valor in self.respostas.items():
            if url == chave or url.startswith(chave):
                if isinstance(valor, Exception):
                    raise valor
                return valor
        raise HttpError(url, 404, "sem resposta no fake")

    def get_bytes(self, url, **_):
        valor = self._achar(url)
        return valor if isinstance(valor, bytes) else valor.encode("utf-8")

    def get_json(self, url, **_):
        return self._achar(url)


# ------------------------------------------------------------------------------------------------ Câmara: parsing
@pytest.mark.parametrize(
    "rotulo,status,justificativa",
    [
        ("Presença", pe.PRESENTE, None),
        ("Presença (~)", pe.PRESENTE, None),
        ("Ausência", pe.AUSENCIA_NAO_JUSTIFICADA, None),
        ("Missão Autorizada", pe.MISSAO_OFICIAL, "Missão Autorizada"),
        ("Licença para Tratamento de Saúde", pe.LICENCA_MEDICA, "Licença para Tratamento de Saúde"),
        ("Decisão da Mesa", pe.AUSENCIA_JUSTIFICADA, "Decisão da Mesa"),
        ("Licença Maternidade", pe.AUSENCIA_JUSTIFICADA, "Licença Maternidade"),
        ("  Ausência   Observações ? ", pe.AUSENCIA_NAO_JUSTIFICADA, None),
    ],
)
def test_classificar_rotulo_camara(rotulo, status, justificativa):
    assert pe.classificar_rotulo_camara(rotulo) == (status, justificativa)


def test_classificar_rotulo_vazio_e_erro():
    with pytest.raises(ValueError):
        pe.classificar_rotulo_camara("   ")


def test_parse_presenca_camara_dias_sessoes_e_resumo():
    html = pagina_presenca(
        DIAS_PAGINA, sessoes=[("06/02/2024", "Presença"), ("20/02/2024", "Ausência")], resumo=RESUMO_PAGINA
    )
    parsed = pe.parse_presenca_camara(html)
    assert [d["data"] for d in parsed["dias"]] == [
        "2024-02-06",
        "2024-02-20",
        "2024-02-27",
        "2024-02-28",
        "2024-03-05",
        "2024-03-06",
    ]
    assert parsed["sessoes"][1] == {
        "data": "2024-02-20",
        "descricao": "EXTRAORDINÁRIA Nº 001 - 20/02/2024",
        "rotulo": "Ausência",
    }
    assert parsed["resumo"] == {
        "total_sessoes": 7,
        "ausencias_nao_justificadas_sessoes": 1,
        "total_dias": 6,
        "dias_presenca": 2,
        "dias_ausencia_justificada": 3,
        "dias_ausencia_nao_justificada": 1,
    }
    regs, rotulos = pe.registros_dia_camara(parsed)
    cont = pe.contagens_camara(regs)
    # confere com o resumo oficial da própria página
    assert cont == {"total_dias": 6, "presencas": 2, "faltas_justificadas": 3, "faltas_nao_justificadas": 1}
    assert rotulos["Presença (~)"] == 1
    assert pe.taxa_presenca(cont["presencas"], cont["total_dias"]) == pytest.approx(33.33)
    assert pe.taxa_presenca(0, 0) is None


def test_parse_presenca_camara_sem_dados_retorna_none():
    assert pe.parse_presenca_camara("<p>Não há dados disponíveis para o ano de 2019.</p>") is None
    assert pe.parse_presenca_camara("<html><body>nada aqui</body></html>") is None


# ------------------------------------------------------------------------------------------------ Senado
def test_classificar_voto_senado():
    assert pe.classificar_voto_senado("Sim")[:2] == (pe.PRESENTE, None)
    assert pe.classificar_voto_senado("P-NRV")[0] == pe.PRESENTE
    assert pe.classificar_voto_senado("Presidente (art. 51 RISF)")[0] == pe.PRESENTE
    assert pe.classificar_voto_senado("AP")[:2] == (pe.AUSENCIA_JUSTIFICADA, "Atividade parlamentar")
    assert pe.classificar_voto_senado("MIS")[0] == pe.MISSAO_OFICIAL
    assert pe.classificar_voto_senado("LS")[0] == pe.LICENCA_MEDICA
    assert pe.classificar_voto_senado("LP")[0] == pe.AUSENCIA_JUSTIFICADA
    assert pe.classificar_voto_senado("Ausente")[0] == pe.AUSENCIA_NAO_JUSTIFICADA
    assert pe.classificar_voto_senado("NA") is None  # dispositivo não citado: não informa presença
    assert pe.classificar_voto_senado("XYZ") is None
    assert pe.classificar_voto_senado("NCom")[0] == "AUSENCIA_NAO_JUSTIFICADA"


def votacao(codigo, data, votos):
    return {
        "CodigoSessaoVotacao": codigo,
        "DataSessao": data,
        "Votos": {
            "VotoParlamentar": [
                {"CodigoParlamentar": str(c), "NomeParlamentar": f"Sen {c}", "Voto": v} for c, v in votos
            ]
        },
    }


def test_parse_votacoes_senado_aceita_lista_dict_unico_e_ignora_sem_votos():
    payload = {
        "ListaVotacoes": {
            "Votacoes": {
                "Votacao": [
                    votacao("1", "2024-03-05", [(10, "Sim"), (11, "AP")]),
                    {"CodigoSessaoVotacao": "2", "DataSessao": "2024-03-06", "Votos": {}},  # secreta/sem votos
                ]
            }
        }
    }
    saida = pe.parse_votacoes_senado(payload)
    assert saida == [
        {"codigo": "1", "data": "2024-03-05", "votos": [[10, "Sen 10", "Sim"], [11, "Sen 11", "AP"]], "partidos": {}}
    ]
    unico = {"ListaVotacoes": {"Votacoes": {"Votacao": votacao("3", "2024-03-07", [(10, "Não")])}}}
    assert len(pe.parse_votacoes_senado(unico)) == 1
    assert pe.parse_votacoes_senado({}) == []


def test_agregar_dias_senado_prioridade_dedup_e_codigos_desconhecidos():
    votacoes = [
        {"codigo": "a", "data": "2024-03-05", "votos": [[1, "S1", "AP"], [2, "S2", "Sim"], [3, "S3", "XYZ"]]},
        {"codigo": "b", "data": "2024-03-05", "votos": [[1, "S1", "Sim"], [2, "S2", "AP"], [4, "S4", "AP"]]},
        {"codigo": "c", "data": "2024-03-06", "votos": [[4, "S4", "AP"], [4, "S4", "MIS"], [5, "S5", "NA"]]},
        {"codigo": "a", "data": "2024-03-05", "votos": [[9, "S9", "Sim"]]},  # votação repetida: ignorada
    ]
    dias, desconhecidos = pe.agregar_dias_senado(votacoes)
    assert dias[(1, "2024-03-05")]["status"] == pe.PRESENTE  # presente em ao menos uma votação do dia
    assert dias[(2, "2024-03-05")]["status"] == pe.PRESENTE
    assert dias[(4, "2024-03-05")] == {
        "status": pe.AUSENCIA_JUSTIFICADA,
        "justificativa": "Atividade parlamentar",
        "nome": "S4",
    }
    assert dias[(4, "2024-03-06")]["status"] == pe.MISSAO_OFICIAL  # MIS tem prioridade sobre AP
    assert (5, "2024-03-06") not in dias and (3, "2024-03-05") not in dias
    assert (9, "2024-03-05") not in dias
    assert dict(desconhecidos) == {"XYZ": 1}


def test_janelas_mensais_corta_no_dia_corrente():
    j = pe.janelas_mensais(2025, hoje=date(2025, 3, 10))
    assert j == [
        (date(2025, 1, 1), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 28)),
        (date(2025, 3, 1), date(2025, 3, 10)),
    ]
    assert len(pe.janelas_mensais(2024, hoje=date(2026, 1, 1))) == 12


# ------------------------------------------------------------------------------------------------ cliente educado
def test_cliente_educado_espera_resfriamento_crescente_e_zera_no_sucesso(monkeypatch):
    esperas = []
    respostas = [
        urllib.error.HTTPError("u", 429, "Too Many", {}, None),
        urllib.error.HTTPError("u", 429, "Too Many", {}, None),
        "ok",
        urllib.error.HTTPError("u", 429, "Too Many", {}, None),
        "ok2",
    ]

    class Resp:
        status = 200

        def __init__(self, corpo):
            self.corpo = corpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.corpo.encode()

    def urlopen(req, timeout=None):
        r = respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return Resp(r)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    cli = pe.PoliteHttpClient(base_interval=0, cooldown_inicial=45, cooldown_max=100, sleep=esperas.append)
    assert cli.get_bytes("http://x") == b"ok"
    assert esperas == [45, 90]  # dobra a cada 429 seguido
    assert cli.get_bytes("http://x") == b"ok2"
    assert esperas == [45, 90, 45]  # o sucesso zerou o resfriamento


def test_cliente_educado_desiste_apos_429_persistente_e_nao_mascara_outros_erros(monkeypatch):
    def sempre_429(req, timeout=None):
        raise urllib.error.HTTPError("u", 429, "Too Many", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", sempre_429)
    cli = pe.PoliteHttpClient(base_interval=0, tentativas_429=3, sleep=lambda s: None)
    with pytest.raises(HttpError) as exc:
        cli.get_bytes("http://x")
    assert exc.value.status == 429

    def erro_404(req, timeout=None):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", erro_404)
    with pytest.raises(HttpError) as exc:
        cli.get_bytes("http://x")
    assert exc.value.status == 404


# ------------------------------------------------------------------------------------------------ extrator Câmara
def deputados_api(ids):
    return {"dados": [{"id": i, "nome": f"Dep {i}"} for i in ids], "links": [{"rel": "self"}]}


def montar_extrator(tmp_path, http, hoje=date(2025, 6, 1)):
    return pe.PresencaExtractor(raw_dir=tmp_path / "raw", processed_dir=tmp_path / "proc", http=http, hoje=hoje)


def http_camara(paginas):
    respostas = {
        f"{pe.URL_CAMARA_API}/deputados?idLegislatura=57": deputados_api([101, 102]),
        f"{pe.URL_CAMARA_API}/deputados?idLegislatura=56": deputados_api([101, 103]),
    }
    respostas.update(paginas)
    return HttpFalso(respostas)


def test_listar_deputados_pagina_e_usa_cache(tmp_path):
    pag1 = {"dados": [{"id": 1, "nome": "A"}], "links": [{"rel": "next"}]}
    pag2 = {"dados": [{"id": 2, "nome": "B"}], "links": []}
    http = HttpFalso(
        {
            f"{pe.URL_CAMARA_API}/deputados?idLegislatura=57&itens=100&pagina=1": pag1,
            f"{pe.URL_CAMARA_API}/deputados?idLegislatura=57&itens=100&pagina=2": pag2,
        }
    )
    ext = montar_extrator(tmp_path, http)
    assert [d["id"] for d in ext.listar_deputados(57)] == [1, 2]
    n = len(http.chamadas)
    assert [d["id"] for d in ext.listar_deputados(57)] == [1, 2]
    assert len(http.chamadas) == n  # segunda chamada veio do cache

    vazio = montar_extrator(
        tmp_path / "outro", HttpFalso({f"{pe.URL_CAMARA_API}/deputados?idLegislatura=57": {"dados": [], "links": []}})
    )
    with pytest.raises(EmptyResultError):
        vazio.listar_deputados(57)


def test_extrair_camara_filtra_ids_respeita_orcamento_e_retoma_do_cache(tmp_path):
    html = pagina_presenca(DIAS_PAGINA, resumo=RESUMO_PAGINA)
    paginas = {pe.URL_CAMARA_PRESENCA.format(id=i, ano=a): html for i in (101, 102, 103) for a in (2020, 2024, 2025)}
    http = http_camara(paginas)
    ext = montar_extrator(tmp_path, http)

    r1 = ext.extrair_camara(anos=[2024, 2025], ids_permitidos={101, 102}, max_paginas_novas=2, flush_cada=0)
    assert r1["paginas_novas"] == 2 and r1["paginas_pendentes"] == 2
    assert len(r1["resumos"]) == 2
    assert all(c["parlamentar_id"] in (101, 102) for c in r1["resumos"])  # 103 não permitido
    assert r1["divergencias_resumo_oficial"] == 0

    n_paginas = sum(1 for u in http.chamadas if "presenca-plenario" in u)
    r2 = ext.extrair_camara(anos=[2024, 2025], ids_permitidos={101, 102}, flush_cada=0)
    assert r2["paginas_pendentes"] == 0 and len(r2["resumos"]) == 4
    # só as 2 páginas faltantes foram buscadas: as demais saíram do cache
    assert sum(1 for u in http.chamadas if "presenca-plenario" in u) - n_paginas == 2
    resumo = r2["resumos"][0]
    assert (
        resumo["total_dias"] == 6 and resumo["presencas"] == 2 and resumo["taxa_presenca_pct"] == pytest.approx(33.33)
    )
    assert resumo["unidade"] == pe.UNIDADE_CAMARA
    assert len(r2["dias"]) == 4 * 6 and r2["dias"][0][2] in {
        pe.PRESENTE,
        pe.AUSENCIA_NAO_JUSTIFICADA,
        pe.MISSAO_OFICIAL,
    }


def test_extrair_camara_registra_falha_sem_abortar_e_ignora_anos_sem_dados(tmp_path):
    ok = pagina_presenca(DIAS_PAGINA, resumo=RESUMO_PAGINA)
    http = http_camara(
        {
            pe.URL_CAMARA_PRESENCA.format(id=101, ano=2024): ok,
            pe.URL_CAMARA_PRESENCA.format(id=102, ano=2024): HttpError("u", 500, "quebrou"),
            pe.URL_CAMARA_PRESENCA.format(id=101, ano=2023): "<p>Não há dados disponíveis para o ano de 2023.</p>",
            pe.URL_CAMARA_PRESENCA.format(id=102, ano=2023): "<p>Não há dados disponíveis para o ano de 2023.</p>",
        }
    )
    r = montar_extrator(tmp_path, http).extrair_camara(anos=[2023, 2024], ids_permitidos={101, 102}, flush_cada=0)
    assert [c["parlamentar_id"] for c in r["resumos"]] == [101]
    assert len(r["falhas"]) == 1 and "102/2024" in r["falhas"][0]


def test_divergencia_com_resumo_oficial_e_contada(tmp_path):
    resumo_errado = dict(RESUMO_PAGINA, pres=5)
    http = http_camara(
        {pe.URL_CAMARA_PRESENCA.format(id=101, ano=2024): pagina_presenca(DIAS_PAGINA, resumo=resumo_errado)}
    )
    r = montar_extrator(tmp_path, http).extrair_camara(anos=[2024], ids_permitidos={101}, flush_cada=0)
    assert r["divergencias_resumo_oficial"] == 1


# ------------------------------------------------------------------------------------------------ extrator Senado + gravação
def http_senado(meses):
    return HttpFalso(
        {
            pe.URL_SENADO_VOTACOES.format(ini=ini, fim=fim): {"ListaVotacoes": {"Votacoes": {"Votacao": votos}}}
            for (ini, fim), votos in meses.items()
        }
    )


def test_run_grava_resumo_e_dias_preserva_outra_casa_e_recusa_resultado_vazio(tmp_path):
    ok = pagina_presenca(DIAS_PAGINA, resumo=RESUMO_PAGINA)
    http = http_camara({pe.URL_CAMARA_PRESENCA.format(id=101, ano=2025): ok})
    ext = montar_extrator(tmp_path, http, hoje=date(2025, 2, 10))
    ext.run(anos_camara=[2025], camara=True, senado=False, ids_camara={101})

    resumo = json.loads((tmp_path / "proc" / pe.ARQ_RESUMO).read_text(encoding="utf-8"))
    assert resumo["is_synthetic"] is False and "Câmara" in resumo["fonte"]
    assert [r["casa"] for r in resumo["resumos"]] == ["CAMARA"]

    http_s = http_senado(
        {
            ("20250101", "20250131"): [votacao("v1", "2025-01-30", [(7, "Sim"), (8, "LS")])],
            ("20250201", "20250210"): [],
        }
    )
    ext_s = montar_extrator(tmp_path, http_s, hoje=date(2025, 2, 10))
    ext_s.run(anos_senado=[2025], camara=False, senado=True)

    resumo = json.loads((tmp_path / "proc" / pe.ARQ_RESUMO).read_text(encoding="utf-8"))
    casas = {r["casa"] for r in resumo["resumos"]}
    assert casas == {"CAMARA", "SENADO"}  # a Câmara já gravada não foi apagada
    sen = next(r for r in resumo["resumos"] if r["casa"] == "SENADO" and r["parlamentar_id"] == 8)
    assert sen["faltas_justificadas"] == 1 and sen["faltas_nao_justificadas"] == 0
    assert "NCom" in resumo["metodologia"]["SENADO"]

    dias = pe.carregar_dias(tmp_path / "proc")
    assert dias["is_synthetic"] is False and len(dias["camara"]) == 6 and len(dias["senado"]) == 2
    assert [7, "2025-01-30", pe.PRESENTE, None] in dias["senado"]
    assert [8, "2025-01-30", pe.LICENCA_MEDICA, "Licença saúde"] in dias["senado"]

    # extração que não devolve nada não destrói os arquivos bons
    vazio = pe.PresencaExtractor(
        raw_dir=tmp_path / "raw_vazio", processed_dir=tmp_path / "proc", http=HttpFalso({}), hoje=date(2025, 2, 10)
    )
    antes = (tmp_path / "proc" / pe.ARQ_RESUMO).read_bytes()
    with pytest.raises(EmptyResultError):
        vazio.run(camara=False, senado=True, anos_senado=[2025])
    assert (tmp_path / "proc" / pe.ARQ_RESUMO).read_bytes() == antes


def test_votacoes_senado_do_mes_corrente_sao_refeitas_e_meses_fechados_vem_do_cache(tmp_path):
    chamadas = []

    class H(HttpFalso):
        def get_json(self, url, **_):
            chamadas.append(url)
            return super().get_json(url)

    h = H(
        {
            pe.URL_SENADO_VOTACOES.format(ini="20250101", fim="20250131"): {"ListaVotacoes": {}},
            pe.URL_SENADO_VOTACOES.format(ini="20250201", fim="20250210"): {"ListaVotacoes": {}},
            pe.URL_SENADO_VOTACOES.format(ini="20250201", fim="20250215"): {"ListaVotacoes": {}},
        }
    )
    ext = montar_extrator(tmp_path, h, hoje=date(2025, 2, 10))
    ext._votacoes_mes(date(2025, 1, 1), date(2025, 1, 31), True)
    ext._votacoes_mes(date(2025, 1, 1), date(2025, 1, 31), True)
    assert len(chamadas) == 1  # mês fechado: cache
    ext._votacoes_mes(date(2025, 2, 1), date(2025, 2, 10), True)
    ext._votacoes_mes(date(2025, 2, 1), date(2025, 2, 10), True)
    assert len(chamadas) == 2  # mesmo dia final: cache recente vale
    ext.hoje = date(2025, 2, 15)
    ext._votacoes_mes(date(2025, 2, 1), date(2025, 2, 15), True)
    assert len(chamadas) == 3  # janela mudou: refaz


def test_ids_deputados_conhecidos(tmp_path):
    assert pe.ids_deputados_conhecidos(tmp_path) is None
    (tmp_path / "deputados_camara.json").write_text(json.dumps([{"camara_id": 5}, {"camara_id": None}, {"x": 1}]))
    assert pe.ids_deputados_conhecidos(tmp_path) == {5}


def test_cache_vale_para_anos_encerrados_e_ano_corrente_por_24h():
    hoje = date(2025, 6, 1)
    assert pe._cache_vale(None, 2024, hoje) is True
    assert pe._cache_vale(None, 2025, hoje) is False
    assert pe._cache_vale(datetime.now().isoformat(), 2025, hoje) is True
    assert pe._cache_vale("2000-01-01T00:00:00", 2025, hoje) is False
    assert pe._cache_vale("lixo", 2025, hoje) is False


# ------------------------------------------------------------------------------------------------ remuneração
PAG_ANUAL = """<table><tbody>
<tr><td class="text-center">01</td><td class="text-right"><a href="x">
   41.650,922
</a></td></tr>
<tr><td class="text-center">02</td><td class="text-right"><a href="x"> 44.008,52 </a></td></tr>
<tr><td class="text-center">03</td><td class="text-right"><a href="x"> 16.881,50 </a></td></tr>
</tbody></table>"""

PAG_DETALHE = """<html><body>Mês/Ano de Referência/Tipo Folha: 06/2024 -FOLHA NORMAL Descrição Valor R$
1 - Remuneração Básica a - Remuneração Fixa 44.008,52 b - Vantagens de Natureza Pessoal 0,00
4 - Descontos Obrigatórios(-) b - Contribuição Previdenciária -7.208,15
5 - Remuneração após Descontos Obrigatórios a - Remuneração após Descontos Obrigatórios 27.822,06
6 - Outros a - Diárias 11.796,91
Mês/Ano de Referência/Tipo Folha: 06/2024 -FOLHA DE GRATIFICAÇÃO NATALINA
1 - Remuneração Básica a - Remuneração Fixa 0,00
5 - Remuneração após Descontos Obrigatórios a - Remuneração após Descontos Obrigatórios 6.290,07
</body></html>"""


def test_parse_valor_br_ignora_marcador_de_nota_de_rodape():
    assert re_.parse_valor_br("41.650,922") == 41650.92  # "2" é a nota de rodapé colada ao número
    assert re_.parse_valor_br("  7.717,26 ") == 7717.26
    assert re_.parse_valor_br("33.763,00") == 33763.0
    assert re_.parse_valor_br("-7.208,15") == -7208.15
    assert re_.parse_valor_br("sem valor") is None and re_.parse_valor_br("") is None


def test_parse_remuneracao_anual_e_detalhe():
    assert re_.parse_remuneracao_anual(PAG_ANUAL) == {1: 41650.92, 2: 44008.52, 3: 16881.5}
    assert re_.parse_remuneracao_anual("<p>nada</p>") == {}
    # o líquido é o da FOLHA NORMAL, não o da folha de gratificação natalina
    assert re_.parse_remuneracao_detalhe(PAG_DETALHE) == {"fixa": 44008.52, "liquido": 27822.06}
    assert re_.parse_remuneracao_detalhe("<p>sem folha</p>") is None


def montar_rem(tmp_path, http, hoje=date(2025, 3, 20)):
    return re_.RemuneracaoExtractor(raw_dir=tmp_path / "raw", processed_dir=tmp_path / "proc", http=http, hoje=hoje)


def test_remuneracao_extractor_liquido_so_do_mes_mais_recente(tmp_path):
    http = HttpFalso(
        {
            f"{pe.URL_CAMARA_API}/deputados?idLegislatura=57": deputados_api([101, 102]),
            re_.URL_ANUAL.format(id=101, ano=2025): PAG_ANUAL,
            re_.URL_ANUAL.format(id=101, ano=2024): PAG_ANUAL,
            re_.URL_DETALHE.format(id=101, ano=2025, mes=3): PAG_DETALHE,
        }
    )
    res = montar_rem(tmp_path, http).run(anos=[2024, 2025], ids_permitidos={101})
    regs = res["registros"]
    assert len(regs) == 6 and res["is_synthetic"] is False
    liquidos = {(r["ano"], r["mes"]): r["salario_liquido"] for r in regs}
    assert liquidos[(2025, 3)] == 27822.06
    assert sum(v is not None for v in liquidos.values()) == 1  # demais meses: null
    assert (tmp_path / "proc" / re_.ARQ_REMUNERACAO).exists()
    assert "Senado" in res["metodologia"]  # lacuna documentada


def test_remuneracao_extractor_nao_grava_arquivo_vazio(tmp_path):
    http = HttpFalso(
        {
            f"{pe.URL_CAMARA_API}/deputados?idLegislatura=57": deputados_api([101]),
            re_.URL_ANUAL.format(id=101, ano=2025): "<p>sem tabela</p>",
        }
    )
    with pytest.raises(EmptyResultError):
        montar_rem(tmp_path, http).run(anos=[2025], ids_permitidos={101})
    assert not (tmp_path / "proc" / re_.ARQ_REMUNERACAO).exists()


# ------------------------------------------------------------------------------------------------ cargas (SQLite)
@pytest.fixture
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def deputado(
    sessao,
    camara_id=101,
    senado_id=None,
    cargo=CargoPoliticoEnum.DEPUTADO_FEDERAL,
    inicio=date(2023, 2, 1),
    fim=date(2027, 1, 31),
):
    pol = Politician(
        civil_name=f"Pol {camara_id or senado_id}", electoral_name="X", camara_id=camara_id, senado_id=senado_id
    )
    partido = PoliticalParty(acronym=f"P{camara_id or senado_id}", full_name="Partido")
    sessao.add_all([pol, partido])
    sessao.flush()
    m = Mandate(
        politician_id=pol.id,
        party_id=partido.id,
        office=cargo,
        jurisdiction_state="SP",
        election_year=2022,
        start_date=inicio,
        end_date=fim,
    )
    sessao.add(m)
    sessao.flush()
    return pol, m


def gravar_dias(pasta, camara=(), senado=(), oficial=True):
    corpo = {
        "is_synthetic": not oficial,
        "fonte": "teste",
        "camara": [list(x) for x in camara],
        "senado": [list(x) for x in senado],
    }
    if not oficial:
        corpo.pop("fonte")
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / pe.ARQ_DIAS).write_bytes(gzip.compress(json.dumps(corpo).encode()))


def test_load_attendances_insere_e_e_idempotente(sessao, tmp_path):
    pol, m = deputado(sessao)
    sessao.commit()
    gravar_dias(
        tmp_path,
        camara=[
            (101, "2024-02-06", "PRESENTE", None),
            (101, "2024-02-20", "AUSENCIA_NAO_JUSTIFICADA", None),
            (101, "2024-02-27", "MISSAO_OFICIAL", "Missão Autorizada"),
            (999, "2024-02-06", "PRESENTE", None),  # deputado fora do banco
        ],
    )
    stats = loader.load_attendances(sessao, tmp_path)
    assert stats["inseridos"] == 3 and stats["sem_politico"] == 1 and stats["mandato_aproximado"] == 0
    regs = sessao.query(AttendanceRecord).order_by(AttendanceRecord.session_date).all()
    assert [r.attendance_status for r in regs] == [
        TipoPresencaEnum.PRESENTE,
        TipoPresencaEnum.AUSENCIA_NAO_JUSTIFICADA,
        TipoPresencaEnum.MISSAO_OFICIAL,
    ]
    assert regs[2].justification == "Missão Autorizada" and regs[0].mandate_id == m.id
    assert all(r.legislative_house == CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS for r in regs)

    stats2 = loader.load_attendances(sessao, tmp_path)
    assert stats2["apagados"] == 3 and stats2["inseridos"] == 3
    assert sessao.query(AttendanceRecord).count() == 3  # idempotente


def test_load_attendances_substitui_linhas_sinteticas_do_mesmo_periodo_e_preserva_outros_anos(sessao, tmp_path):
    pol, m = deputado(sessao)
    sessao.add_all(
        [
            AttendanceRecord(
                politician_id=pol.id,
                mandate_id=m.id,
                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                session_date=date(2024, 5, 7),
                attendance_status=TipoPresencaEnum.LICENCA_MEDICA,
                justification=f"{SYNTHETIC_TAG}sorteado",
            ),
            AttendanceRecord(
                politician_id=pol.id,
                mandate_id=m.id,
                legislative_house=CasaLegislativaEnum.CAMARA_DOS_DEPUTADOS,
                session_date=date(2023, 5, 7),
                attendance_status=TipoPresencaEnum.PRESENTE,
                justification=None,
            ),
            AttendanceRecord(  # outra casa no mesmo ano: não pode ser tocada
                politician_id=pol.id,
                mandate_id=m.id,
                legislative_house=CasaLegislativaEnum.SENADO_FEDERAL,
                session_date=date(2024, 5, 7),
                attendance_status=TipoPresencaEnum.PRESENTE,
                justification=None,
            ),
        ]
    )
    sessao.commit()
    gravar_dias(tmp_path, camara=[(101, "2024-02-06", "PRESENTE", None)])
    loader.load_attendances(sessao, tmp_path)
    datas = sorted((r.session_date, r.legislative_house.value) for r in sessao.query(AttendanceRecord))
    assert datas == [
        (date(2023, 5, 7), "CAMARA_DOS_DEPUTADOS"),
        (date(2024, 2, 6), "CAMARA_DOS_DEPUTADOS"),
        (date(2024, 5, 7), "SENADO_FEDERAL"),
    ]
    assert not any((r.justification or "").startswith(SYNTHETIC_TAG) for r in sessao.query(AttendanceRecord))


def test_load_attendances_senado_e_mandato_aproximado(sessao, tmp_path):
    # senador só tem mandato cadastrado a partir de 2023; presença de 2021 usa o mais próximo, contabilizado
    pol, m = deputado(sessao, camara_id=None, senado_id=55, cargo=CargoPoliticoEnum.SENADOR)
    sessao.commit()
    gravar_dias(
        tmp_path,
        senado=[(55, "2021-03-02", "PRESENTE", None), (55, "2024-03-02", "AUSENCIA_JUSTIFICADA", "Licença particular")],
    )
    stats = loader.load_attendances(sessao, tmp_path)
    assert stats["inseridos"] == 2 and stats["mandato_aproximado"] == 1
    assert {r.mandate_id for r in sessao.query(AttendanceRecord)} == {m.id}


def test_load_attendances_sem_mandato_e_arquivo_ausente_ou_sem_proveniencia(sessao, tmp_path):
    pol, _ = deputado(sessao, camara_id=101, cargo=CargoPoliticoEnum.SENADOR)  # tem mandato de outro cargo
    sessao.commit()
    gravar_dias(tmp_path, camara=[(101, "2024-02-06", "PRESENTE", None)])
    stats = loader.load_attendances(sessao, tmp_path)
    assert stats["sem_mandato"] == 1 and stats["inseridos"] == 0

    assert loader.load_attendances(sessao, tmp_path / "inexistente")["arquivo_ausente"] == 1
    gravar_dias(tmp_path / "x", camara=[(101, "2024-02-06", "PRESENTE", None)], oficial=False)
    with pytest.raises(ValueError, match="proveniência"):
        loader.load_attendances(sessao, tmp_path / "x")
    assert sessao.query(AttendanceRecord).count() == 0


def test_mandate_resolver_vigente_anterior_e_posterior(sessao):
    pol, m = deputado(sessao, inicio=date(2019, 2, 1), fim=date(2023, 1, 31))
    _, m2 = deputado(sessao, camara_id=202)
    sessao.commit()
    r = loader.MandateResolver(sessao.query(Mandate).all())
    cargo = CargoPoliticoEnum.DEPUTADO_FEDERAL
    assert r.resolver(pol.id, cargo, date(2020, 1, 1)).id == m.id and r.aproximados == 0
    assert r.resolver(pol.id, cargo, date(2024, 1, 1)).id == m.id and r.aproximados == 1  # após o fim: o mais recente
    assert r.resolver(pol.id, cargo, date(2010, 1, 1)).id == m.id and r.aproximados == 2  # antes do início: o primeiro
    assert r.resolver(pol.id, CargoPoliticoEnum.SENADOR, date(2020, 1, 1)) is None


def gravar_remuneracao(pasta, registros, oficial=True):
    corpo = {"is_synthetic": not oficial, "fonte": "teste", "registros": registros}
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / re_.ARQ_REMUNERACAO).write_text(json.dumps(corpo), encoding="utf-8")


def test_load_remunerations_bruto_liquido_nulo_e_idempotente(sessao, tmp_path):
    pol, m = deputado(sessao)
    sessao.add(
        PoliticianRemuneration(  # linha sintética antiga do mesmo ano: substituída
            politician_id=pol.id,
            mandate_id=m.id,
            reference_year=2024,
            reference_month=1,
            gross_salary=Decimal("1"),
            net_salary=Decimal("1"),
            parliamentary_quota_ceap=Decimal("9999"),
            housing_allowance=Decimal("0"),
            other_benefits=Decimal("0"),
            data_source=f"{SYNTHETIC_TAG}simulado",
        )
    )
    sessao.commit()
    gravar_remuneracao(
        tmp_path,
        [
            {"camara_id": 101, "ano": 2024, "mes": 1, "salario_bruto": 41650.92, "salario_liquido": None},
            {"camara_id": 101, "ano": 2024, "mes": 2, "salario_bruto": 44008.52, "salario_liquido": 27822.06},
            {"camara_id": 999, "ano": 2024, "mes": 2, "salario_bruto": 1.0, "salario_liquido": None},
        ],
    )
    stats = loader.load_remunerations(sessao, tmp_path)
    assert stats["inseridos"] == 2 and stats["apagados"] == 1 and stats["sem_politico"] == 1
    rs = sessao.query(PoliticianRemuneration).order_by(PoliticianRemuneration.reference_month).all()
    assert rs[0].gross_salary == Decimal("41650.92") and rs[0].net_salary is None
    assert rs[1].net_salary == Decimal("27822.06")
    # o que a fonte não informa é NULL, nunca 0
    assert all(
        r.parliamentary_quota_ceap is None and r.housing_allowance is None and r.other_benefits is None for r in rs
    )
    assert not any(r.data_source.startswith(SYNTHETIC_TAG) for r in rs)

    loader.load_remunerations(sessao, tmp_path)
    assert sessao.query(PoliticianRemuneration).count() == 2


def test_load_remunerations_recusa_sem_proveniencia_e_tolera_arquivo_ausente(sessao, tmp_path):
    deputado(sessao)
    sessao.commit()
    assert loader.load_remunerations(sessao, tmp_path / "nada")["arquivo_ausente"] == 1
    gravar_remuneracao(tmp_path / "x", [{"camara_id": 101, "ano": 2024, "mes": 1, "salario_bruto": 1.0}], oficial=False)
    with pytest.raises(ValueError, match="proveniência"):
        loader.load_remunerations(sessao, tmp_path / "x")


def test_partidos_por_data_registra_so_as_mudancas():
    votacoes = [
        {"codigo": "b", "data": "2024-03-06", "votos": [], "partidos": {1: "PSD", 2: "PT"}},
        {"codigo": "a", "data": "2024-03-05", "votos": [], "partidos": {1: "PSD"}},
        {"codigo": "c", "data": "2024-08-01", "votos": [], "partidos": {1: "PL"}},
    ]
    assert pe.partidos_por_data(votacoes) == [
        [1, "2024-03-05", "PSD"],
        [1, "2024-08-01", "PL"],
        [2, "2024-03-06", "PT"],
    ]
