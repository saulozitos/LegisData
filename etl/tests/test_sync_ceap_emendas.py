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


# ── Cache por ano: a atualização diária só baixa o ano corrente ──────────────────────────────────────────────────────
from datetime import date  # noqa: E402


def _linhas_de(acc, ano, fator=1.0):
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", ano, 1, "COMBUSTÍVEL", "Posto A", "1", 10.0 * fator)
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", ano, 2, "TELEFONIA", "Posto B", None, 5.5 * fator)
    acc.add("SENADOR", 7, "Beto", ano, 3, "PASSAGEM", "Cia", "9", 100.0 * fator)


def test_mesclar_anos_separados_da_o_mesmo_resultado_que_acumular_tudo_de_uma_vez():
    junto = CeapAccumulator()
    for ano in (2023, 2024):
        _linhas_de(junto, ano)
    por_ano = {ano: CeapAccumulator() for ano in (2023, 2024)}
    for ano, acc in por_ano.items():
        _linhas_de(acc, ano)
    mesclado = CeapAccumulator()
    for ano in (2023, 2024):
        mesclado.mesclar(por_ano[ano])
    assert mesclado.finalize(FONTES) == junto.finalize(FONTES)


def test_mesclar_soma_o_fornecedor_entre_anos_antes_de_escolher_os_maiores():
    """O top 15 é do período inteiro: um fornecedor pequeno em cada ano pode ser o maior na soma."""
    um, outro = CeapAccumulator(), CeapAccumulator()
    for i in range(sync.TOP_FORNECEDORES):  # 15 fornecedores de 60 em 2023
        um.add("SENADOR", 7, "Beto", 2023, 1, "T", f"F{i}", None, 60.0)
    um.add("SENADOR", 7, "Beto", 2023, 1, "T", "ZETA", None, 50.0)
    outro.add("SENADOR", 7, "Beto", 2024, 1, "T", "ZETA", None, 50.0)  # 100 no total: passa a todos os de 60
    acc = CeapAccumulator()
    acc.mesclar(um)
    acc.mesclar(outro)
    (reg,) = acc.finalize(FONTES).values()
    assert "ZETA" in reg["fornecedores"] and reg["fornecedores"]["ZETA"]["total"] == 100.0
    assert reg["fornecedores"]["ZETA"]["notas"] == 2 and len(reg["fornecedores"]) == sync.TOP_FORNECEDORES


def test_mesclar_fica_com_o_nome_do_ultimo_ano_mesclado():
    antigo, novo = CeapAccumulator(), CeapAccumulator()
    antigo.add("DEPUTADO_FEDERAL", 1, "Ana Silva", 2023, 1, "T", "F", None, 1.0)
    novo.add("DEPUTADO_FEDERAL", 1, "Ana Souza", 2024, 1, "T", "F", None, 1.0)
    acc = CeapAccumulator()
    acc.mesclar(antigo)
    acc.mesclar(novo)
    assert next(iter(acc.finalize(FONTES))) == "ANA SOUZA"


def test_mesclar_nao_altera_o_acumulador_de_origem():
    origem = CeapAccumulator()
    _linhas_de(origem, 2023)
    antes = json.dumps(origem.para_json(), sort_keys=True)
    destino = CeapAccumulator()
    destino.mesclar(origem)
    destino.mesclar(origem)  # a segunda mescla soma em cima da cópia
    assert json.dumps(origem.para_json(), sort_keys=True) == antes


def test_json_do_acumulador_vai_e_volta_sem_perder_nada():
    acc = CeapAccumulator()
    _linhas_de(acc, 2023)
    acc.add("DEPUTADO_FEDERAL", None, "Sem Id", 2023, 1, "T", "F", None, 3.0)  # identificador ausente: chave pelo nome
    volta = CeapAccumulator.de_json(json.loads(json.dumps(acc.para_json())))
    assert volta.finalize(FONTES) == acc.finalize(FONTES)


@pytest.fixture(autouse=True)
def _sem_pausas(monkeypatch):
    """As esperas entre downloads existem para a rede de verdade; nos testes valem zero, mas ficam registradas."""
    pausas = []
    monkeypatch.setattr(sync.time, "sleep", pausas.append)
    return pausas


class ExtratorContador:
    """Extrator no formato de `extract_*_ceap`: cada chamada baixa os anos pedidos (e registra quais)."""

    def __init__(self, falha_em=(), vazio_em=()):
        self.chamadas = []
        self.falha_em = set(falha_em)
        self.vazio_em = set(vazio_em)

    def __call__(self, http, anos, acc):
        self.chamadas.append(list(anos))
        falhas = [a for a in anos if a in self.falha_em]
        for ano in anos:
            if ano not in self.falha_em and ano not in self.vazio_em:
                _linhas_de(acc, ano)
        return len(anos) - len(falhas), falhas


def test_ano_fechado_vai_para_o_cache_e_nao_e_baixado_de_novo(tmp_path):
    hoje = date(2026, 10, 19)
    extrator, acc = ExtratorContador(), CeapAccumulator()
    total, falhas, do_cache = sync._extrair_com_cache(None, [2023, 2024, 2026], "camara", extrator, acc, tmp_path, hoje)
    assert (total, falhas, do_cache) == (3, [], []) and extrator.chamadas == [[2023], [2024], [2026]]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["camara_2023.json", "camara_2024.json"]  # 2026 não

    segunda, acc2 = ExtratorContador(), CeapAccumulator()
    total, falhas, do_cache = sync._extrair_com_cache(None, [2023, 2024, 2026], "camara", segunda, acc2, tmp_path, hoje)
    assert segunda.chamadas == [[2026]] and do_cache == [2023, 2024] and total == 1  # só o ano corrente vai à rede
    assert acc2.finalize(FONTES) == acc.finalize(FONTES)  # o resultado é o mesmo, com ou sem cache


def test_ano_anterior_so_vira_cache_depois_de_1_de_abril_do_ano_seguinte(tmp_path):
    extrator = ExtratorContador()
    for hoje in (date(2026, 1, 15), date(2026, 3, 31)):  # 2025 já fechou, mas ainda recebe correções
        sync._extrair_com_cache(None, [2025], "senado", extrator, CeapAccumulator(), tmp_path, hoje)
    assert list(tmp_path.iterdir()) == [] and extrator.chamadas == [[2025], [2025]]

    sync._extrair_com_cache(None, [2025], "senado", extrator, CeapAccumulator(), tmp_path, date(2026, 4, 1))
    assert [p.name for p in tmp_path.iterdir()] == ["senado_2025.json"]  # 1º de abril já é definitivo


def test_cache_nao_e_lido_antes_do_ano_ficar_definitivo(tmp_path):
    extrator = ExtratorContador()
    sync._gravar_cache(tmp_path, "camara", 2025, CeapAccumulator.de_json([]))  # um cache velho, de uma execução antiga
    sync._extrair_com_cache(None, [2025], "camara", extrator, CeapAccumulator(), tmp_path, date(2026, 2, 1))
    assert extrator.chamadas == [[2025]]  # ainda dentro da janela de correções: baixa de novo


def test_falha_de_um_ano_aborta_e_nao_cacheia_o_ano_que_falhou(tmp_path):
    extrator, acc = ExtratorContador(falha_em=[2024]), CeapAccumulator()
    total, falhas, _ = sync._extrair_com_cache(None, [2023, 2024], "camara", extrator, acc, tmp_path, date(2026, 10, 1))
    assert falhas == [2024] and total == 1
    assert [p.name for p in tmp_path.iterdir()] == ["camara_2023.json"]


def test_ano_sem_nenhum_registro_nao_vira_cache(tmp_path):
    extrator = ExtratorContador(vazio_em=[2023])
    sync._extrair_com_cache(None, [2023], "camara", extrator, CeapAccumulator(), tmp_path, date(2026, 10, 1))
    assert list(tmp_path.iterdir()) == []  # um download vazio de ano fechado seria erro da fonte, não dado


@pytest.mark.parametrize(
    "conteudo",
    [
        "",
        "não é json",
        "[]",
        '{"versao": 99, "casa": "camara", "ano": 2023, "dados": []}',
        '{"versao": 1, "casa": "senado", "ano": 2023, "dados": []}',
        '{"versao": 1, "casa": "camara", "ano": 2022, "dados": []}',
        '{"versao": 1, "casa": "camara", "ano": 2023, "dados": [{"chave": 1}]}',
    ],
)
def test_cache_corrompido_ou_de_outra_versao_e_ignorado_e_refeito(tmp_path, conteudo):
    (tmp_path / "camara_2023.json").write_text(conteudo, encoding="utf-8")
    extrator = ExtratorContador()
    sync._extrair_com_cache(None, [2023], "camara", extrator, CeapAccumulator(), tmp_path, date(2026, 10, 1))
    assert extrator.chamadas == [[2023]]  # baixou de novo
    assert sync._ler_cache(tmp_path, "camara", 2023) is not None  # e o cache novo é válido


def test_run_com_cache_gera_o_mesmo_arquivo_que_sem_cache(tmp_path, monkeypatch):
    saida_cache, saida_direta = tmp_path / "c", tmp_path / "d"
    saida_cache.mkdir()
    saida_direta.mkdir()
    cache = tmp_path / "cache"

    def extrator_camara(http, anos, acc):
        for ano in anos:
            _linhas_de(acc, ano)
        return len(list(anos)), []

    monkeypatch.setattr(sync, "extract_camara_ceap", extrator_camara)
    monkeypatch.setattr(sync, "extract_senado_ceaps", lambda http, anos, acc: (0, []))
    hoje = date(2026, 10, 19)

    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", saida_direta)
    sync.run(2023, 2026, ceap=True, emendas=False, http=object(), hoje=hoje)
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", saida_cache)
    primeira = sync.run(2023, 2026, ceap=True, emendas=False, http=object(), cache_dir=cache, hoje=hoje)
    segunda = sync.run(2023, 2026, ceap=True, emendas=False, http=object(), cache_dir=cache, hoje=hoje)

    esperado = (saida_direta / sync.CEAP_OUTPUT).read_text(encoding="utf-8")
    assert (saida_cache / sync.CEAP_OUTPUT).read_text(encoding="utf-8") == esperado
    assert primeira["ceap_anos_do_cache"] == {"camara": [], "senado": []}
    assert segunda["ceap_anos_do_cache"]["camara"] == [2023, 2024, 2025]  # só 2026 voltou à rede


def test_entre_dois_downloads_ha_pausa_e_ano_vindo_do_cache_nao_gera_pausa(tmp_path, monkeypatch):
    pausas = []
    monkeypatch.setattr(sync.time, "sleep", pausas.append)
    sync._gravar_cache(tmp_path, "camara", 2023, CeapAccumulator.de_json([]))
    sync._extrair_com_cache(
        None, [2023, 2024, 2025], "camara", ExtratorContador(), CeapAccumulator(), tmp_path, date(2026, 10, 1)
    )
    assert pausas == [
        sync.PAUSA_ENTRE_DOWNLOADS
    ]  # 2023 veio do cache; entre 2024 e 2025 há uma pausa, antes de 2024 não


class ExtratorQueFalhaUmaVez(ExtratorContador):
    """429 na primeira tentativa de cada ano pedido, sucesso na segunda."""

    def __init__(self):
        super().__init__()
        self.vistos = set()

    def __call__(self, http, anos, acc):
        (ano,) = anos
        self.chamadas.append([ano])
        if ano not in self.vistos:
            self.vistos.add(ano)
            return 0, [ano]
        _linhas_de(acc, ano)
        return 1, []


def test_ano_que_falha_ganha_uma_segunda_tentativa_depois_de_uma_pausa(tmp_path, monkeypatch):
    pausas = []
    monkeypatch.setattr(sync.time, "sleep", pausas.append)
    extrator = ExtratorQueFalhaUmaVez()
    total, falhas, _ = sync._extrair_com_cache(
        None, [2023], "camara", extrator, CeapAccumulator(), tmp_path, date(2026, 10, 1)
    )
    assert (total, falhas) == (1, []) and extrator.chamadas == [[2023], [2023]]
    assert pausas == [sync.ESPERA_NOVA_TENTATIVA]


def test_ano_que_falha_duas_vezes_continua_sendo_falha(tmp_path):
    extrator = ExtratorContador(falha_em=[2024])
    _, falhas, _ = sync._extrair_com_cache(
        None, [2024], "camara", extrator, CeapAccumulator(), tmp_path, date(2026, 10, 1)
    )
    assert falhas == [2024] and extrator.chamadas == [[2024], [2024]]
