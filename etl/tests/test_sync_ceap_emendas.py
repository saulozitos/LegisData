"""Pipeline unificado de CEAP/emendas: agregação idempotente por id oficial e parsing do CSV do Portal."""

import json

import pytest

import etl.pipelines.sync_ceap_emendas as sync
from etl.extractors.emendas_extractor import EmendasExtractor, parse_brl, parse_emendas_csv, stable_id
from etl.pipelines.sync_ceap_emendas import CeapAccumulator

FONTES = {"DEPUTADO_FEDERAL": "camara", "SENADOR": "senado"}


def test_agregacao_por_id_oficial_e_homonimos_nao_se_misturam():
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", 1, "Marcelo", 2023, 1, "COMBUSTÍVEL", "Posto A", "1", 100.0)
    acc.add("DEPUTADO_FEDERAL", 2, "Marcelo", 2023, 1, "COMBUSTÍVEL", "Posto A", "1", 50.0)
    saida = acc.finalize(FONTES)
    assert len(saida) == 2
    totais = sorted(v["total_gasto"] for v in saida.values())
    assert totais == [50.0, 100.0]
    assert {v["camara_id"] for v in saida.values()} == {1, 2}


def test_estorno_reduz_total_mas_nao_conta_como_nota():
    acc = CeapAccumulator()
    acc.add("SENADOR", 7, "Fulana", 2024, 3, "PASSAGEM", "Cia", None, 200.0)
    acc.add("SENADOR", 7, "Fulana", 2024, 4, "PASSAGEM", "Cia", None, -50.0)
    (reg,) = acc.finalize(FONTES).values()
    assert reg["total_gasto"] == 150.0 and reg["total_notas"] == 1
    assert reg["por_ano"] == {"2024": 150.0}
    assert reg["por_ano_tipo"] == {"2024": {"PASSAGEM": 150.0}}
    assert reg["is_synthetic"] is False and reg["fonte"] == "senado"


def test_recalcular_com_as_mesmas_entradas_e_idempotente():
    def construir():
        acc = CeapAccumulator()
        for _ in range(2):  # a mesma sequência montada duas vezes (rodar o pipeline duas vezes)
            pass
        acc.add("DEPUTADO_FEDERAL", 1, "A", 2023, 1, "X", "F", None, 10.0)
        acc.add("DEPUTADO_FEDERAL", 1, "A", 2024, 1, "X", "F", None, 5.0)
        return acc.finalize(FONTES)

    assert construir() == construir()
    assert construir()["A"]["total_gasto"] == 15.0  # não soma por cima de execução anterior


def test_stable_id_e_deterministico():
    assert stable_id("Fulano de Tal") == stable_id("Fulano de Tal")
    assert stable_id("A") != stable_id("B")


def test_parse_brl():
    assert parse_brl("1.234.567,89") == 1234567.89
    assert parse_brl("0,00") == 0.0
    assert parse_brl("") is None and parse_brl(None) is None and parse_brl("abc") is None
    assert parse_brl(12) == 12.0


CSV = (
    "Código da Emenda;Ano da Emenda;Tipo de Emenda;Código do Autor da Emenda;Nome do Autor da Emenda;"
    "Localidade de aplicação do recurso;Função;Valor Empenhado;Valor Pago\n"
    "202301;2023;Emenda Individual;12;FULANO DE TAL;CURITIBA - PR;Saúde;1.000,50;500,00\n"
    ";abc;Emenda;1;SEM ANO;X;Y;1,00;1,00\n"
    "202302;2024;Emenda de Bancada;;;LOCAL;Educação;2,00;1,00\n"
).encode("latin-1")


def test_parse_emendas_csv_descarta_linhas_invalidas_e_marca_proveniencia():
    registros = parse_emendas_csv(CSV)
    assert len(registros) == 1
    r = registros[0]
    assert r["valor_empenhado"] == 1000.5 and r["valor_pago"] == 500.0 and r["politician_name"] == "FULANO DE TAL"
    assert r["is_synthetic"] is False and "Portal da Transparência" in r["fonte"]


def test_parse_emendas_csv_exige_colunas():
    with pytest.raises(ValueError):
        parse_emendas_csv(b"coluna;outra\n1;2\n")


def test_emendas_sinteticas_so_com_autorizacao(tmp_path):
    ext = EmendasExtractor(raw_dir=tmp_path, processed_dir=tmp_path)
    assert ext.generate_emendas_for_politician("Fulano", "SP", 1) == []
    emendas = ext.generate_emendas_for_politician("Fulano", "SP", 1, allow_synthetic=True)
    assert emendas and all(e["is_synthetic"] for e in emendas)
    assert emendas == ext.generate_emendas_for_politician("Fulano", "SP", 1, allow_synthetic=True)  # determinístico


class ClienteFalso:
    """HttpClient falso: devolve JSON/bytes por URL ou levanta erro."""

    def __init__(self, erros_por_ano=()):
        self.erros = set(erros_por_ano)

    def get_json(self, url, **_):
        from etl.utils.http_client import HttpError

        ano = int(url.rsplit("/", 1)[1])
        if ano in self.erros:
            raise HttpError(url, 500, "falhou")
        return [
            {
                "codSenador": 1,
                "nomeSenador": "S",
                "ano": ano,
                "mes": 1,
                "tipoDespesa": "T",
                "fornecedor": "F",
                "cpfCnpj": None,
                "valorReembolsado": 10,
            }
        ]


def test_senado_ceaps_acumula_por_codigo(tmp_path):
    acc = CeapAccumulator()
    total, falhas = sync.extract_senado_ceaps(ClienteFalso(), [2023, 2024], acc)
    assert (total, falhas) == (2, [])
    (reg,) = acc.finalize(FONTES).values()
    assert reg["por_ano"] == {"2023": 10.0, "2024": 10.0} and reg["senado_id"] == 1


def test_ano_com_falha_aborta_gravacao_e_preserva_arquivo_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    anterior = tmp_path / sync.CEAP_OUTPUT
    anterior.write_text(json.dumps({"BOM": {"total_gasto": 1}}), encoding="utf-8")

    monkeypatch.setattr(sync, "extract_camara_ceap", lambda http, anos, acc: (0, []))
    resumo = sync.run(2023, 2024, ceap=True, emendas=False, http=ClienteFalso(erros_por_ano=[2024]))
    assert resumo["ceap_gravado"] is False
    assert json.loads(anterior.read_text(encoding="utf-8")) == {"BOM": {"total_gasto": 1}}


def test_run_grava_quando_completo(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "extract_camara_ceap", lambda http, anos, acc: (0, []))
    resumo = sync.run(2023, 2024, ceap=True, emendas=False, http=ClienteFalso())
    assert resumo["ceap_gravado"] is True and resumo["ceap_parlamentares"] == 1
    saida = json.loads((tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8"))
    assert saida["S"]["total_gasto"] == 20.0
    # idempotência: segunda execução gera exatamente o mesmo arquivo
    antes = (tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8")
    sync.run(2023, 2024, ceap=True, emendas=False, http=ClienteFalso())
    assert (tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8") == antes


def test_intervalo_invalido():
    with pytest.raises(ValueError):
        sync.run(2025, 2020)


CSV_DUPLICADO = (
    '"Código da Emenda";"Ano da Emenda";"Tipo de Emenda";"Código do Autor da Emenda";"Nome do Autor da Emenda";'
    '"Localidade de aplicação do recurso";"Município";"Nome Função";"Valor Empenhado";"Valor Pago"\n'
    '"202301";"2023";"Individual";"1";"FULANO";"CURITIBA - PR";"CURITIBA";"Saúde";"100,00";"10,00"\n'
    '"202301";"2023";"Individual";"1";"FULANO";"CURITIBA - PR";"CURITIBA";"Saúde";"50,00";"5,00"\n'
    '"202301";"2023";"Individual";"1";"FULANO";"LONDRINA - PR";"LONDRINA";"Saúde";"7,00";"0,00"\n'
    '"Sem informação";"2015";"Individual";"2";"Sem informação";"X";"X";"Saúde";"1,00";"1,00"\n'
    '"Sem informação";"2015";"Individual";"2";"CICRANO";"Y";"Y";"Saúde";"2,00";"0,00"\n'
).encode("latin-1")


def test_csv_real_duplicatas_somadas_codigo_e_autor_sem_informacao_tratados():
    regs = parse_emendas_csv(CSV_DUPLICADO)
    por_local = {r["localidade_destino"]: r for r in regs}
    assert por_local["CURITIBA - PR"]["valor_empenhado"] == 150.0 and por_local["CURITIBA - PR"]["valor_pago"] == 15.0
    assert por_local["LONDRINA - PR"]["valor_empenhado"] == 7.0
    assert por_local["CURITIBA - PR"]["funcao"] == "Saúde"  # coluna real é "Nome Função"
    assert "X" not in por_local  # autor "Sem informação" descartado
    assert por_local["Y"]["codigo_emenda"] is None  # código "Sem informação" vira None
