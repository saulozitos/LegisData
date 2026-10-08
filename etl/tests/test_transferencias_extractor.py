"""Repasses federais por UF a partir do Portal da Transparência: agregação, bloqueio 405 e cobertura incompleta."""

import io
import json
import zipfile
from datetime import date

from etl.extractors import transferencias_extractor as mod
from etl.extractors.transferencias_extractor import (
    TransferenciasExtractor,
    agregar_zip,
    area_tematica,
    mandato_do_mes,
    meses_no_intervalo,
)
from etl.utils.http_client import HttpError

CABECALHO = '"ANO / MÊS";"TIPO TRANSFERÊNCIA";"TIPO FAVORECIDO";"UF";"NOME FUNÇÃO";"VALOR TRANSFERIDO"'

MANDATOS = [
    {"id_referencia": "dilma-2011", "data_inicio": "2011-01-01", "data_fim": "2015-01-01"},
    {"id_referencia": "dilma-2015", "data_inicio": "2015-01-01", "data_fim": "2016-08-31"},
    {"id_referencia": "temer-2016", "data_inicio": "2016-08-31", "data_fim": "2019-01-01"},
]


def zip_mensal(linhas):
    corpo = "\n".join([CABECALHO] + linhas).encode("latin-1")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("202401_Transferencias.csv", corpo)
    return buf.getvalue()


def linha(uf, tipo, funcao, valor):
    return f'"202401";"{tipo}";"Municipal";"{uf}";"{funcao}";"{valor}"'


def test_area_tematica_agrupa_funcoes():
    assert area_tematica("Constitucionais e Royalties", "Encargos especiais") == "Constitucionais e Royalties"
    assert area_tematica("Legais, Voluntárias e Específicas", "Saúde") == "Saúde"
    assert area_tematica("Legais, Voluntárias e Específicas", "Segurança pública") == "Segurança Pública"
    assert area_tematica("Legais, Voluntárias e Específicas", "Urbanismo") == "Infraestrutura"
    assert area_tematica("Legais, Voluntárias e Específicas", "Cultura") == "Outras funções"


def test_agregar_zip_soma_por_uf_e_area_e_ignora_uf_invalida():
    conteudo = zip_mensal(
        [
            linha("AC", "Constitucionais e Royalties", "Encargos especiais", "1000,50"),
            linha("AC", "Constitucionais e Royalties", "Encargos especiais", "0,25"),
            linha("AC", "Legais, Voluntárias e Específicas", "Saúde", "200,00"),
            linha("", "Legais, Voluntárias e Específicas", "Saúde", "999,00"),  # sem UF
            linha("ND", "Legais, Voluntárias e Específicas", "Saúde", "999,00"),  # UF inexistente
            linha("SP", "Legais, Voluntárias e Específicas", "Saúde", "não-numero"),  # valor inválido
        ]
    )
    assert agregar_zip(conteudo) == {("AC", "Constitucionais e Royalties"): 1000.75, ("AC", "Saúde"): 200.0}


def test_meses_e_mandato_do_mes():
    assert meses_no_intervalo((2014, 11), (2015, 2)) == ["201411", "201412", "201501", "201502"]
    assert mandato_do_mes("201412", MANDATOS) == "dilma-2011"
    assert mandato_do_mes("201608", MANDATOS) == "dilma-2015"  # 1º dia do mês ainda é governo Dilma
    assert mandato_do_mes("201609", MANDATOS) == "temer-2016"
    assert mandato_do_mes("200001", MANDATOS) is None


class HttpPortal:
    """Devolve ZIPs por mês; `bloqueios` simula respostas 405 antes do sucesso."""

    def __init__(self, mensal, bloqueios=0, falha_permanente=()):
        self.mensal = mensal
        self.bloqueios = bloqueios
        self.falha_permanente = set(falha_permanente)
        self.chamadas = []

    def get_bytes(self, url, **_):
        ym = url.rsplit("/", 1)[1]
        self.chamadas.append(ym)
        if ym in self.falha_permanente:
            raise HttpError(url, 500, "falha")
        if self.bloqueios > 0:
            self.bloqueios -= 1
            raise HttpError(url, 405, "Not Allowed")
        return self.mensal


def extrator(tmp_path, http, hoje, esperas=None, monkeypatch=None):
    esperas = esperas if esperas is not None else []
    ext = TransferenciasExtractor(
        output_dir=tmp_path,
        raw_dir=tmp_path / "raw",
        http=http,
        sidra=object(),
        hoje=hoje,
        sleep=esperas.append,
    )
    return ext, esperas


def test_bloqueio_405_e_retentado_com_espera_crescente(tmp_path):
    http = HttpPortal(zip_mensal([linha("AC", "x", "Saúde", "1,00")]), bloqueios=2)
    ext, esperas = extrator(tmp_path, http, date(2020, 1, 15))
    assert ext.baixar_mes("201801") is not None
    assert esperas == [60, 120]
    assert (tmp_path / "raw" / "201801_Transferencias.zip").exists()


def test_bloqueio_permanente_devolve_none_sem_loop_infinito(tmp_path):
    ext, esperas = extrator(tmp_path, HttpPortal(b"", bloqueios=999), date(2020, 1, 15))
    assert ext.baixar_mes("201801") is None
    assert len(esperas) == mod.MAX_TENTATIVAS_BLOQUEIO - 1


def test_mes_antigo_em_cache_nao_e_baixado_de_novo(tmp_path):
    http = HttpPortal(zip_mensal([linha("AC", "x", "Saúde", "1,00")]))
    ext, _ = extrator(tmp_path, http, date(2020, 1, 15))
    ext.baixar_mes("201801")
    ext.baixar_mes("201801")
    assert http.chamadas == ["201801"]


def test_resposta_que_nao_e_zip_e_ignorada(tmp_path):
    ext, _ = extrator(tmp_path, HttpPortal(b"<html>405</html>"), date(2020, 1, 15))
    assert ext.baixar_mes("201801") is None


def _preparar(monkeypatch, populacao=None):
    monkeypatch.setattr(mod, "load_json", lambda *_a, **_k: MANDATOS)
    monkeypatch.setattr(mod, "populacao_uf", lambda _s: populacao or {"AC": {2016: 1_000}})


def test_run_grava_totais_por_mandato_uf_area_com_per_capita(tmp_path, monkeypatch):
    _preparar(monkeypatch)
    mensal = zip_mensal(
        [
            linha("AC", "Constitucionais e Royalties", "Encargos especiais", "600,00"),
            linha("AC", "Legais, Voluntárias e Específicas", "Saúde", "400,00"),
        ]
    )
    # Janela 2016-07..2016-09: 07 e 08 = Dilma; 09 = Temer
    ext, _ = extrator(tmp_path, HttpPortal(mensal), date(2016, 9, 20))
    monkeypatch.setattr(mod, "PRIMEIRO_MES_DISPONIVEL", (2016, 7))
    resultado = ext.run(ano_inicio=2016)
    assert resultado["gerado"] is True
    registros = json.loads((tmp_path / "repasses_federais_uf.json").read_text(encoding="utf-8"))
    por_chave = {(r["mandato_id_ref"], r["uf"], r["area_tematica"]): r for r in registros}
    dilma = por_chave[("dilma-2015", "AC", "Saúde")]
    assert dilma["valor_pago_brl"] == 800.0  # 2 meses × 400
    assert dilma["meses_cobertos"] == 2 and dilma["periodo_inicio"] == "2016-07" and dilma["periodo_fim"] == "2016-08"
    assert dilma["populacao_estimada"] == 1_000 and dilma["valor_per_capita_brl"] == 0.8
    assert dilma["is_synthetic"] is False and "Portal da Transparência" in dilma["fonte"]
    assert por_chave[("temer-2016", "AC", "Constitucionais e Royalties")]["valor_pago_brl"] == 600.0


def test_run_nao_grava_quando_falta_mes_antigo(tmp_path, monkeypatch):
    _preparar(monkeypatch)
    (tmp_path / "repasses_federais_uf.json").write_text('["anterior"]', encoding="utf-8")
    mensal = zip_mensal([linha("AC", "x", "Saúde", "1,00")])
    ext, _ = extrator(tmp_path, HttpPortal(mensal, falha_permanente={"201607"}), date(2016, 9, 20))
    monkeypatch.setattr(mod, "PRIMEIRO_MES_DISPONIVEL", (2016, 6))
    resultado = ext.run(ano_inicio=2016)
    assert resultado["gerado"] is False and "201607" in resultado["meses_faltantes"]
    assert (tmp_path / "repasses_federais_uf.json").read_text(encoding="utf-8") == '["anterior"]'


def test_run_tolera_mes_corrente_ainda_nao_publicado(tmp_path, monkeypatch):
    _preparar(monkeypatch)
    mensal = zip_mensal([linha("AC", "x", "Saúde", "1,00")])
    ext, _ = extrator(tmp_path, HttpPortal(mensal, falha_permanente={"201609"}), date(2016, 9, 20))
    monkeypatch.setattr(mod, "PRIMEIRO_MES_DISPONIVEL", (2016, 7))
    assert ext.run(ano_inicio=2016)["gerado"] is True  # o mês em curso pode não existir ainda
