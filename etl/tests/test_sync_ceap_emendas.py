"""Pipeline unificado de CEAP/emendas: agregação idempotente por id oficial e parsing do CSV do Portal."""

import json
from datetime import date, timedelta

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
    """HttpClient falso: devolve JSON por URL ou levanta erro."""

    def __init__(self, erros_por_ano=(), status=500):
        self.erros = set(erros_por_ano)
        self.status = status

    def get_json(self, url, **_):
        from etl.utils.http_client import HttpError

        ano = int(url.rsplit("/", 1)[1])
        if ano in self.erros:
            raise HttpError(url, self.status, "falhou")
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


@pytest.fixture(autouse=True)
def pausas(monkeypatch):
    """As esperas existem para a rede de verdade; nos testes não dormem, mas ficam registradas na ordem em que ocorrem."""
    registradas = []
    monkeypatch.setattr(sync.time, "sleep", registradas.append)
    return registradas


def _linhas_de(acc, ano, fator=1.0, nome="Ana", casa=None):
    """Lançamentos de um ano; `casa` limita a uma casa (o cache de uma casa só aceita cargos dela), None traz as duas."""
    if casa in (None, "camara"):
        acc.add("DEPUTADO_FEDERAL", 1, nome, ano, 1, "COMBUSTÍVEL", "Posto A", "02558157000162", 10.0 * fator)
        acc.add("DEPUTADO_FEDERAL", 1, nome, ano, 2, "TELEFONIA", "Posto B", None, 5.5 * fator)
    if casa in (None, "senado"):
        acc.add("SENADOR", 7, "Beto", ano, 3, "PASSAGEM", "Cia", "11222333000181", 100.0 * fator)


class Extrator:
    """Extrator no formato de `extract_*_ceap` (aceita `ausentes`): registra as chamadas e simula cada situação."""

    def __init__(self, falha_em=(), vazio_em=(), ausente_em=(), falha_uma_vez=False, nome="Ana", casa=None):
        self.chamadas = []
        self.falha_em, self.vazio_em, self.ausente_em = set(falha_em), set(vazio_em), set(ausente_em)
        self.falha_uma_vez, self.vistos, self.nome = falha_uma_vez, set(), nome
        self.casa = casa  # sem casa traz as duas; `_extrair` completa com a casa que a chamada informa

    def __call__(self, http, anos, acc, ausentes=None):
        self.chamadas.append(list(anos))
        falhas = []
        for ano in anos:
            if ano in self.ausente_em:
                falhas.append(ano)
                if ausentes is not None:
                    ausentes.append(ano)
            elif ano in self.falha_em or (self.falha_uma_vez and ano not in self.vistos):
                self.vistos.add(ano)
                falhas.append(ano)
            elif ano not in self.vazio_em:
                _linhas_de(acc, ano, nome=self.nome, casa=self.casa)
        return len(anos) - len(falhas), falhas


def _extrair(anos, extrator, tmp_path, hoje=date(2026, 10, 1), casa="camara", cache=True, acc=None, publicados=None):
    acc = acc if acc is not None else CeapAccumulator()
    extrator.casa = getattr(extrator, "casa", None) or casa
    r = sync._extrair_anos(None, anos, casa, extrator, acc, tmp_path if cache else None, hoje, publicados)
    return (r.baixados, r.falhas, r.do_cache, r.sem_arquivo), acc


# ── Fonte oficial ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_senado_ceaps_acumula_por_codigo(tmp_path):
    acc = CeapAccumulator()
    total, falhas = sync.extract_senado_ceaps(ClienteFalso(), [2023, 2024], acc)
    assert (total, falhas) == (2, [])
    (reg,) = acc.finalize(FONTES).values()
    assert reg["por_ano"] == {"2023": 10.0, "2024": 10.0} and reg["senado_id"] == 1


def test_senado_registra_o_ano_inexistente_em_ausentes_e_como_falha():
    acc, ausentes = CeapAccumulator(), []
    total, falhas = sync.extract_senado_ceaps(
        ClienteFalso(erros_por_ano=[2027], status=404), [2026, 2027], acc, ausentes
    )
    assert (total, falhas, ausentes) == (1, [2027], [2027])
    _, falhas_500 = sync.extract_senado_ceaps(
        ClienteFalso(erros_por_ano=[2027]), [2027], CeapAccumulator(), ausentes := []
    )
    assert falhas_500 == [2027] and ausentes == []  # erro de servidor não é "ainda não publicado"


class ClienteDaCamara:
    """get_bytes devolve o zip do CSV anual; registra os tetos pedidos."""

    def __init__(self, csv_por_ano, status_por_ano=None):
        self.csv_por_ano, self.status_por_ano, self.pedidos = csv_por_ano, status_por_ano or {}, []

    def get_bytes(self, url, **kw):
        import io
        import zipfile

        from etl.utils.http_client import HttpError

        ano = int(url.rsplit("-", 1)[1].split(".")[0])
        self.pedidos.append((ano, kw.get("max_bytes")))
        if ano in self.status_por_ano:
            raise HttpError(url, self.status_por_ano[ano], "falhou")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(f"Ano-{ano}.csv", self.csv_por_ano[ano])
        return buf.getvalue()


CABECALHO = (
    "txNomeParlamentar;ideCadastro;sgUF;sgPartido;numAno;numMes;txtDescricao;vlrLiquido;txtFornecedor;txtCNPJCPF\n"
)


def _csv(ano, linhas):
    return CABECALHO + "".join(f"{n};{i};SP;PT;{ano};1;{t};{v};{f};{d}\n" for n, i, t, v, f, d in linhas)


def test_extract_camara_ceap_agrega_sem_cpf_e_pede_com_teto(tmp_path):
    csv2023 = _csv(
        2023,
        [
            ("Ana", 100, "TELEFONIA", "10,50", "VIVO", "02.558.157/0001-62"),
            ("Ana", 100, "TELEFONIA", "-0,50", "VIVO", "02.558.157/0001-62"),
            ("Ana", 100, "TAXI", "20,00", "JOSE MEI 09876543200", "098.765.432-00"),
        ],
    )
    cliente, acc = ClienteDaCamara({2023: csv2023}), CeapAccumulator()
    total, falhas = sync.extract_camara_ceap(cliente, [2023], acc)
    assert (total, falhas) == (3, []) and cliente.pedidos == [(2023, sync.TETO_DO_DOWNLOAD)]
    (reg,) = acc.finalize(FONTES).values()
    assert (
        reg["total_gasto"] == 30.0
        and reg["total_notas"] == 2
        and reg["por_ano_tipo"] == {"2023": {"TAXI": 20.0, "TELEFONIA": 10.0}}
    )
    assert {f["nome"]: f["cnpj_cpf"] for f in reg["fornecedores"].values()} == {
        "VIVO": "02558157000162",
        "JOSE MEI": None,
    }
    assert "09876543200" not in json.dumps(acc.para_json())  # nem o CPF do documento nem o do nome chegam ao estado


def test_extract_camara_ceap_marca_404_em_ausentes_e_recusa_zip_gigante(monkeypatch):
    acc, ausentes = CeapAccumulator(), []
    cliente = ClienteDaCamara(
        {2026: _csv(2026, [("Ana", 100, "T", "1,00", "F", None)])}, status_por_ano={2027: 404, 2028: 500}
    )
    total, falhas = sync.extract_camara_ceap(cliente, [2026, 2027, 2028], acc, ausentes)
    assert (total, falhas, ausentes) == (1, [2027, 2028], [2027])  # 500 é falha, mas não "ainda não publicado"
    monkeypatch.setattr(sync, "TETO_DO_CSV", 10)
    _, falhas = sync.extract_camara_ceap(cliente, [2026], CeapAccumulator())
    assert falhas == [2026]  # CSV descomprimido acima do teto: recusado antes do read_csv


def test_ano_com_falha_aborta_gravacao_e_preserva_arquivo_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    anterior = tmp_path / sync.CEAP_OUTPUT
    anterior.write_text(json.dumps({"BOM": {"total_gasto": 1}}), encoding="utf-8")

    monkeypatch.setattr(sync, "extract_camara_ceap", Extrator(casa="camara"))
    resumo = sync.run(
        2023, 2024, ceap=True, emendas=False, http=ClienteFalso(erros_por_ano=[2024]), hoje=date(2026, 10, 1)
    )
    assert resumo["ceap_gravado"] is False and resumo["ceap_falhas"] == {"camara": [], "senado": [2024]}
    assert json.loads(anterior.read_text(encoding="utf-8")) == {"BOM": {"total_gasto": 1}}


def test_run_grava_quando_completo(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "extract_camara_ceap", Extrator(casa="camara"))
    hoje = date(2026, 10, 1)
    resumo = sync.run(2023, 2024, ceap=True, emendas=False, http=ClienteFalso(), hoje=hoje)
    assert resumo["ceap_gravado"] is True and resumo["ceap_parlamentares"] == 2  # Ana (extrator da Câmara) e S (Senado)
    saida = json.loads((tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8"))
    assert saida["S"]["total_gasto"] == 20.0 and saida["ANA"]["total_gasto"] == 31.0
    # idempotência: segunda execução gera exatamente o mesmo arquivo
    antes = (tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8")
    sync.run(2023, 2024, ceap=True, emendas=False, http=ClienteFalso(), hoje=hoje)
    assert (tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8") == antes


def test_intervalo_invalido():
    with pytest.raises(ValueError):
        sync.run(2025, 2020)


def test_fontes_nao_gravadas_diz_quais_falharam():
    assert sync.fontes_nao_gravadas({"ceap_gravado": True, "emendas_gravado": True}) == []
    assert sync.fontes_nao_gravadas({"ceap_gravado": False, "emendas_gravado": True}) == ["ceap"]
    assert sync.fontes_nao_gravadas({"ceap_gravado": False, "emendas_gravado": False}) == ["ceap", "emendas"]
    assert sync.fontes_nao_gravadas({"anos": "2023-2024"}) == ["ceap", "emendas"]  # sem resposta, não gravou


# ── Sem CPF em disco (D3) ────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "documento",
    [
        "098.765.432-00",  # CPF formatado
        "09876543200",  # CPF só dígitos
        "098.765.432/00  -",  # CPF na máscara de CNPJ que a Câmara usa (visto nos dados reais)
        "123.456.789/0001",  # 12 dígitos: truncado, não é CNPJ
        "00052998224725",  # CPF válido com enchimento de zeros à esquerda
        "000000000000",  # enchimento de lançamento sem fornecedor
        "***.456.789-**",  # já mascarado pela fonte
        "",
    ],
)
def test_documento_de_pessoa_fisica_nunca_chega_ao_estado_nem_ao_cache(documento):
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "T", "FULANO 09876543200", documento, 10.0)
    estado = json.dumps(acc.para_json())
    for sequencia in ("09876543200", "098.765.432-00", "098.765.432/00", "52998224725"):
        assert sequencia not in estado
    (reg,) = acc.finalize(FONTES).values()
    (forn,) = reg["fornecedores"].values()
    assert forn["nome"] == "FULANO" and forn["cnpj_cpf"] is None


def test_documento_de_14_digitos_fica_sem_conferir_o_digito_verificador():
    # a fonte traz CNPJ que não fecha o DV; só o que é comprovadamente CPF (com zeros à esquerda) sai
    assert sync.cnpj_do_fornecedor("12.345.678/9000-10") == "12345678900010"
    assert sync.cnpj_do_fornecedor("00052998224725") is None


def test_cnpj_valido_continua_no_estado_so_com_digitos():
    acc = CeapAccumulator()
    acc.add("SENADOR", 7, "Beto", 2023, 1, "T", "VIVO", "02.558.157/0001-62", 10.0)
    (reg,) = acc.finalize(FONTES).values()
    assert reg["fornecedores"]["VIVO"]["cnpj_cpf"] == "02558157000162"


def test_o_loader_recebe_o_mesmo_que_recebia_antes_da_limpeza_na_origem():
    """A limpeza na origem não muda o que o `fin` grava: o loader já aplicava as mesmas regras."""
    from etl.pipelines.loader_helpers import fornecedores_do_parlamentar

    bruto = {
        "fornecedores": {
            "VIVO": {"nome": "VIVO", "cnpj_cpf": "02.558.157/0001-62", "total": 10.0, "notas": 1},
            "MEI 09876543200": {"nome": "MEI 09876543200", "cnpj_cpf": "098.765.432-00", "total": 5.0, "notas": 1},
        }
    }
    acc = CeapAccumulator()
    acc.add("SENADOR", 7, "Beto", 2023, 1, "T", "VIVO", "02.558.157/0001-62", 10.0)
    acc.add("SENADOR", 7, "Beto", 2023, 1, "T", "MEI 09876543200", "098.765.432-00", 5.0)
    (limpo,) = acc.finalize(FONTES).values()
    assert fornecedores_do_parlamentar(bruto) == fornecedores_do_parlamentar(limpo)


# ── Acumulador: mescla, nome, JSON ──────────────────────────────────────────────────────────────────────────────────
def test_mesclar_anos_separados_da_o_mesmo_resultado_que_acumular_tudo_de_uma_vez():
    junto = CeapAccumulator()
    for ano in (2023, 2024):
        _linhas_de(junto, ano)
    por_ano = {ano: CeapAccumulator() for ano in (2023, 2024)}
    for ano, acc in por_ano.items():
        _linhas_de(acc, ano)
    for ordem in ((2023, 2024), (2024, 2023)):  # a ordem da mescla não muda o resultado
        mesclado = CeapAccumulator()
        for ano in ordem:
            mesclado.mesclar(por_ano[ano])
        assert mesclado.finalize(FONTES) == junto.finalize(FONTES), ordem


def test_mesclar_com_valores_que_nao_sao_exatos_em_binario_arredonda_igual():
    """0,1 e 0,7 somados em ordens diferentes diferem na última casa do float; o arredondamento a 0,01 absorve."""
    junto, a, b = CeapAccumulator(), CeapAccumulator(), CeapAccumulator()
    for ano, parte in ((2023, a), (2024, b)):
        for _ in range(7):
            junto.add("SENADOR", 7, "Beto", ano, 1, "T", "F", None, 0.1)
            parte.add("SENADOR", 7, "Beto", ano, 1, "T", "F", None, 0.1)
        junto.add("SENADOR", 7, "Beto", ano, 1, "T", "F", None, 0.7)
        parte.add("SENADOR", 7, "Beto", ano, 1, "T", "F", None, 0.7)
    mesclado = CeapAccumulator()
    mesclado.mesclar(a)
    mesclado.mesclar(b)
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


def test_mesclar_completa_o_cnpj_que_so_um_dos_anos_tinha():
    sem, com = CeapAccumulator(), CeapAccumulator()
    sem.add("SENADOR", 7, "Beto", 2023, 1, "T", "VIVO", None, 1.0)
    com.add("SENADOR", 7, "Beto", 2024, 1, "T", "VIVO", "02558157000162", 1.0)
    for ordem in ((sem, com), (com, sem)):
        acc = CeapAccumulator()
        for parte in ordem:
            acc.mesclar(parte)
        (reg,) = acc.finalize(FONTES).values()
        assert reg["fornecedores"]["VIVO"]["cnpj_cpf"] == "02558157000162"


@pytest.mark.parametrize("ordem", [(2023, 2024), (2024, 2023)])
def test_o_nome_e_o_do_ano_mais_recente_em_qualquer_ordem_de_mescla_e_de_acumulo(ordem):
    nomes = {2023: "Ana Silva", 2024: "Ana Souza"}
    partes = {}
    for ano, nome in nomes.items():
        partes[ano] = CeapAccumulator()
        partes[ano].add("DEPUTADO_FEDERAL", 1, nome, ano, 1, "T", "F", None, 1.0)
    mesclado, direto = CeapAccumulator(), CeapAccumulator()
    for ano in ordem:
        mesclado.mesclar(partes[ano])
        direto.add("DEPUTADO_FEDERAL", 1, nomes[ano], ano, 1, "T", "F", None, 1.0)
    assert list(mesclado.finalize(FONTES)) == ["ANA SOUZA"] == list(direto.finalize(FONTES))


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


def test_formato_do_cache_esta_travado_suba_a_versao_se_precisar_mudar():
    """
    Este teste falha quando a forma do estado serializado muda. Se a mudança é de propósito, SUBA `VERSAO_DO_CACHE`
    (os anos fechados em cache carregariam a regra antiga) e atualize o esperado abaixo.
    """
    acc = CeapAccumulator()
    acc.add("DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "TELEFONIA", "VIVO", "02558157000162", 10.0)
    assert sync.VERSAO_DO_CACHE == 3
    assert acc.para_json() == [
        {
            "chave": ["DEPUTADO_FEDERAL", 1],
            "reg": {
                "nome": "ANA",
                "nome_ano": 2023,
                "cargo": "DEPUTADO_FEDERAL",
                "camara_id": 1,
                "senado_id": None,
                "total_gasto": 10.0,
                "total_notas": 1,
                "por_ano": {"2023": 10.0},
                "por_tipo": {"TELEFONIA": 10.0},
                "por_ano_tipo": {"2023": {"TELEFONIA": 10.0}},
                "fornecedores": {"VIVO": {"nome": "VIVO", "cnpj_cpf": "02558157000162", "total": 10.0, "notas": 1}},
            },
        }
    ]


def _reg_valido():
    acc = CeapAccumulator()
    _linhas_de(acc, 2023)
    return json.loads(json.dumps(acc.para_json()))


@pytest.mark.parametrize(
    "estraga",
    [
        lambda itens: itens[0].__setitem__("reg", None),
        lambda itens: itens[0].__setitem__("reg", {}),
        lambda itens: itens[0]["reg"].pop("total_gasto"),
        lambda itens: itens[0]["reg"].pop("fornecedores"),
        lambda itens: itens[0]["reg"].pop("nome_ano"),
        lambda itens: itens[0]["reg"].__setitem__("total_notas", -1),
        lambda itens: itens[0]["reg"].__setitem__("total_gasto", "10"),
        lambda itens: itens[0]["reg"].__setitem__("total_gasto", float("inf")),
        lambda itens: itens[0]["reg"].__setitem__("total_gasto", True),
        lambda itens: itens[0]["reg"].__setitem__("por_ano", {"2023": "x"}),
        lambda itens: itens[0]["reg"].__setitem__("por_ano_tipo", {"2023": 1}),
        lambda itens: itens[0]["reg"].__setitem__("cargo", "OUTRO"),
        lambda itens: itens[0]["reg"]["fornecedores"]["Posto A"].pop("total"),
        lambda itens: itens[0]["reg"]["fornecedores"]["Posto A"].pop("notas"),
        lambda itens: itens[0]["reg"]["fornecedores"]["Posto A"].__setitem__("cnpj_cpf", 123),
        lambda itens: itens[0].__setitem__("chave", ["PRESIDENTE", 1]),
        lambda itens: itens[0].__setitem__("chave", "AB"),
        lambda itens: itens[0].__setitem__("chave", ["SENADOR"]),
        lambda itens: itens[0].__setitem__("chave", ["SENADOR", None]),
        lambda itens: itens[0].pop("reg"),
        lambda itens: itens.append("x"),
    ],
)
def test_de_json_recusa_qualquer_forma_invalida(estraga):
    itens = _reg_valido()
    estraga(itens)
    with pytest.raises(ValueError):
        CeapAccumulator.de_json(itens)


def test_de_json_recusa_o_que_nao_e_lista():
    for invalido in (None, {}, "x", 3):
        with pytest.raises(ValueError):
            CeapAccumulator.de_json(invalido)


# ── Cache por ano ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ano_fechado_vai_para_o_cache_e_nao_e_baixado_de_novo(tmp_path):
    hoje = date(2026, 10, 19)
    extrator = Extrator()
    (baixados, falhas, do_cache, sem_arquivo), acc = _extrair([2023, 2024, 2026], extrator, tmp_path, hoje)
    assert (baixados, falhas, do_cache, sem_arquivo) == (3, [], [], []) and extrator.chamadas == [
        [2023],
        [2024],
        [2026],
    ]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["camara_2023.json", "camara_2024.json"]  # 2026 não é cacheado

    segunda = Extrator()
    (baixados, falhas, do_cache, _), acc2 = _extrair([2023, 2024, 2026], segunda, tmp_path, hoje)
    assert segunda.chamadas == [[2026]] and do_cache == [2023, 2024] and baixados == 1  # só o ano corrente vai à rede
    assert acc2.finalize(FONTES) == acc.finalize(FONTES)  # o resultado é o mesmo, com ou sem cache


def test_sem_cache_dir_nada_e_lido_nem_gravado_mas_a_politica_de_rede_vale(tmp_path, pausas):
    extrator = Extrator()
    (baixados, falhas, do_cache, _), _ = _extrair([2022, 2023], extrator, tmp_path, cache=False)
    assert (baixados, falhas, do_cache) == (2, [], []) and list(tmp_path.iterdir()) == []
    assert pausas == [sync.PAUSA_POR_CASA["camara"]]  # a pausa entre downloads não depende do cache


def test_ano_anterior_so_vira_cache_depois_de_1_de_abril_do_ano_seguinte(tmp_path):
    extrator = Extrator()
    for hoje in (date(2026, 2, 15), date(2026, 3, 31)):  # 2025 já fechou, mas ainda recebe correções
        _extrair([2025], extrator, tmp_path, hoje, casa="senado")
    assert list(tmp_path.iterdir()) == [] and extrator.chamadas == [[2025], [2025]]

    _extrair([2025], extrator, tmp_path, date(2026, 4, 1), casa="senado")
    assert [p.name for p in tmp_path.iterdir()] == ["senado_2025.json"]  # 1º de abril já é definitivo


def test_cache_nasce_com_a_data_e_vence_depois_da_validade(tmp_path):
    _extrair([2023], Extrator(), tmp_path, date(2026, 10, 1))
    conteudo = json.loads((tmp_path / "camara_2023.json").read_text(encoding="utf-8"))
    assert conteudo["gerado_em"] == "2026-10-01" and conteudo["versao"] == sync.VERSAO_DO_CACHE
    ultimo_dia_bom = date(2026, 10, 1) + timedelta(days=sync.VALIDADE_DO_CACHE_DIAS)
    assert sync._ler_cache(tmp_path, "camara", 2023, ultimo_dia_bom) is not None
    assert sync._ler_cache(tmp_path, "camara", 2023, ultimo_dia_bom + timedelta(days=1)) is None
    refeito = Extrator()
    _extrair([2023], refeito, tmp_path, ultimo_dia_bom + timedelta(days=1))
    assert refeito.chamadas == [[2023]]  # cache vencido: baixa de novo e grava com a data nova
    assert json.loads((tmp_path / "camara_2023.json").read_text(encoding="utf-8"))["gerado_em"] != "2026-10-01"


def test_cache_gerado_antes_de_o_ano_fechar_nao_vale(tmp_path):
    """Defesa contra um cache escrito por engano com o ano ainda aberto (relógio errado, cópia manual)."""
    acc = CeapAccumulator()
    _linhas_de(acc, 2025)
    sync._gravar_cache(tmp_path, "camara", 2025, acc, date(2026, 2, 1))
    assert sync._ler_cache(tmp_path, "camara", 2025, date(2026, 6, 1)) is None


def test_falha_de_um_ano_aborta_e_nao_cacheia_o_ano_que_falhou(tmp_path):
    extrator = Extrator(falha_em=[2024])
    (baixados, falhas, _, _), _ = _extrair([2023, 2024], extrator, tmp_path, date(2026, 10, 1))
    assert falhas == [2024] and baixados == 1
    assert [p.name for p in tmp_path.iterdir()] == ["camara_2023.json"]


@pytest.mark.parametrize("ano_corrente", [False, True])
def test_ano_que_volta_vazio_e_falha_fora_do_comeco_do_ano_e_nunca_vira_cache(tmp_path, ano_corrente):
    hoje = date(2026, 10, 1)
    ano = 2026 if ano_corrente else 2023
    (_, falhas, _, sem_arquivo), acc = _extrair([ano], Extrator(vazio_em=[ano]), tmp_path, hoje)
    assert falhas == [ano] and sem_arquivo == [] and acc.vazio and list(tmp_path.iterdir()) == []


def test_ano_corrente_vazio_em_janeiro_ainda_nao_e_falha(tmp_path):
    (_, falhas, _, sem_arquivo), acc = _extrair([2027], Extrator(vazio_em=[2027]), tmp_path, date(2027, 1, 10))
    assert (falhas, sem_arquivo) == ([], [2027]) and acc.vazio  # ainda sem despesa lançada: nada de zero fabricado


def test_arquivo_do_ano_novo_ainda_nao_publicado_em_janeiro_nao_derruba_a_cea(tmp_path):
    hoje = date(2027, 1, 5)
    extrator = Extrator(ausente_em=[2027])
    (baixados, falhas, _, sem_arquivo), acc = _extrair([2026, 2027], extrator, tmp_path, hoje)
    assert (falhas, sem_arquivo, baixados) == ([], [2027], 1) and not acc.vazio
    assert extrator.chamadas == [[2026], [2027]]  # 404 não ganha segunda tentativa


def test_arquivo_ausente_fora_de_janeiro_ou_de_outro_ano_e_falha_sem_nova_tentativa(tmp_path):
    for hoje, ano in ((date(2027, 4, 1), 2027), (date(2027, 1, 5), 2026)):
        extrator = Extrator(ausente_em=[ano])
        (_, falhas, _, sem_arquivo), _ = _extrair([ano], extrator, tmp_path / str(hoje), hoje)
        assert (falhas, sem_arquivo) == ([ano], []) and extrator.chamadas == [[ano]], (hoje, ano)


@pytest.mark.parametrize(
    "conteudo",
    [
        "",
        "não é json",
        "[]",
        '{"versao": 99, "casa": "camara", "ano": 2023, "gerado_em": "2026-10-01", "dados": []}',
        '{"versao": 2, "casa": "senado", "ano": 2023, "gerado_em": "2026-10-01", "dados": []}',
        '{"versao": 2, "casa": "camara", "ano": 2022, "gerado_em": "2026-10-01", "dados": []}',
        '{"versao": 2, "casa": "camara", "ano": 2023, "gerado_em": "ontem", "dados": []}',
        '{"versao": 2, "casa": "camara", "ano": 2023, "dados": []}',
        '{"versao": 2, "casa": "camara", "ano": 2023, "gerado_em": "2026-10-01", "dados": []}',  # vazio: erro da fonte
        '{"versao": 2, "casa": "camara", "ano": 2023, "gerado_em": "2026-10-01", "dados": [{"chave": 1}]}',
        '{"versao": 2, "casa": "camara", "ano": 2023, "gerado_em": "2026-10-01", "dados": [{"chave": ["DEPUTADO_FEDERAL", 1], "reg": {}}]}',
        '{"versao": 2, "casa": "camara", "ano": 2023, "gerado_em": "2026-10-01", "dados": [{"chave": ["SENADOR", 1], "reg": null}]}',
    ],
)
def test_cache_corrompido_ou_de_outra_versao_e_ignorado_e_refeito(tmp_path, conteudo):
    (tmp_path / "camara_2023.json").write_text(conteudo, encoding="utf-8")
    extrator = Extrator()
    _extrair([2023], extrator, tmp_path, date(2026, 10, 2))
    assert extrator.chamadas == [[2023]]  # baixou de novo
    assert sync._ler_cache(tmp_path, "camara", 2023, date(2026, 10, 2)) is not None  # e o cache novo é válido


def test_cache_de_uma_casa_nao_serve_a_outra(tmp_path):
    _extrair([2023], Extrator(), tmp_path, casa="camara")
    senado = Extrator()
    _extrair([2023], senado, tmp_path, casa="senado")
    assert senado.chamadas == [[2023]]


# ── Política de rede: pausa, segunda tentativa, ordem ───────────────────────────────────────────────────────────────
def test_entre_dois_downloads_ha_pausa_e_ano_vindo_do_cache_nao_gera_pausa(tmp_path, pausas):
    acc = CeapAccumulator()
    _linhas_de(acc, 2023, casa="camara")
    sync._gravar_cache(tmp_path, "camara", 2023, acc, date(2026, 10, 1))
    _extrair([2023, 2024, 2025], Extrator(), tmp_path, date(2026, 10, 1))
    assert pausas == [
        sync.PAUSA_POR_CASA["camara"]
    ]  # 2023 veio do cache; antes de 2024 não há pausa, entre 2024 e 2025 há


def test_a_pausa_do_senado_e_a_do_senado_e_a_da_camara_e_a_da_camara(tmp_path, pausas):
    _extrair([2023, 2024], Extrator(), tmp_path, casa="senado", cache=False)
    assert pausas == [sync.PAUSA_POR_CASA["senado"]]


def test_ano_que_falha_ganha_uma_segunda_tentativa_depois_de_uma_pausa(tmp_path, pausas):
    extrator = Extrator(falha_uma_vez=True)
    (baixados, falhas, _, _), _ = _extrair([2023], extrator, tmp_path)
    assert (baixados, falhas) == (1, []) and extrator.chamadas == [[2023], [2023]]
    assert pausas == [sync.ESPERA_NOVA_TENTATIVA]


def test_pausas_em_sequencia_com_uma_falha_no_meio(tmp_path, pausas):
    """2023 falha duas vezes (espera da nova tentativa), e a pausa entre downloads continua valendo para o 2025."""
    extrator = Extrator(falha_em=[2024])
    (_, falhas, _, _), _ = _extrair([2023, 2024, 2025], extrator, tmp_path)
    p = sync.PAUSA_POR_CASA["camara"]
    assert falhas == [2024] and pausas == [p, sync.ESPERA_NOVA_TENTATIVA, p]


def test_ano_que_falha_duas_vezes_continua_sendo_falha(tmp_path):
    extrator = Extrator(falha_em=[2024])
    (_, falhas, _, _), _ = _extrair([2024], extrator, tmp_path)
    assert falhas == [2024] and extrator.chamadas == [[2024], [2024]]


def test_a_segunda_tentativa_descarta_o_que_a_primeira_acumulou_antes_de_falhar(tmp_path):
    """Um extrator que acumula linhas e depois falha não pode deixar essas linhas contarem duas vezes."""

    class Parcial:
        def __init__(self):
            self.chamadas = 0

        def __call__(self, http, anos, acc, ausentes=None):
            self.chamadas += 1
            _linhas_de(acc, anos[0])
            return 1, ([anos[0]] if self.chamadas == 1 else [])

    (_, falhas, _, _), acc = _extrair([2023], Parcial(), tmp_path)
    (reg,) = [r for k, r in acc.finalize(FONTES).items() if k == "ANA"]
    assert falhas == [] and reg["total_gasto"] == 15.5  # 10 + 5,5 uma vez só


def test_anos_fora_de_ordem_sao_processados_em_ordem_crescente(tmp_path):
    extrator = Extrator()
    _extrair([2025, 2023, 2024], extrator, tmp_path)
    assert extrator.chamadas == [[2023], [2024], [2025]]


def test_o_nome_do_ano_mais_recente_vence_no_caminho_com_cache(tmp_path):
    acc = CeapAccumulator()
    _extrair([2023], Extrator(nome="Ana Silva"), tmp_path, acc=acc)
    _extrair([2024], Extrator(nome="Ana Souza"), tmp_path, acc=acc)
    assert "ANA SOUZA" in acc.finalize(FONTES)


def test_run_com_cache_gera_o_mesmo_arquivo_que_sem_cache(tmp_path, monkeypatch):
    saida_cache, saida_direta = tmp_path / "c", tmp_path / "d"
    saida_cache.mkdir()
    saida_direta.mkdir()
    cache = tmp_path / "cache"
    monkeypatch.setattr(sync, "extract_camara_ceap", Extrator(casa="camara"))
    monkeypatch.setattr(sync, "extract_senado_ceaps", Extrator(nome="Beto", casa="senado"))
    hoje = date(2026, 10, 19)

    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", saida_direta)
    sync.run(2023, 2026, ceap=True, emendas=False, http=object(), hoje=hoje)
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", saida_cache)
    primeira = sync.run(2023, 2026, ceap=True, emendas=False, http=object(), cache_dir=cache, hoje=hoje)
    segunda = sync.run(2023, 2026, ceap=True, emendas=False, http=object(), cache_dir=cache, hoje=hoje)

    esperado = (saida_direta / sync.CEAP_OUTPUT).read_text(encoding="utf-8")
    assert (saida_cache / sync.CEAP_OUTPUT).read_text(encoding="utf-8") == esperado
    assert primeira["ceap_anos_do_cache"] == {"camara": [], "senado": []}
    assert segunda["ceap_anos_do_cache"] == {
        "camara": [2023, 2024, 2025],
        "senado": [2023, 2024, 2025],
    }  # só 2026 voltou à rede
    assert segunda["ceap_anos_baixados"] == {"camara": 1, "senado": 1}


def test_run_informa_o_ano_novo_ainda_sem_arquivo_sem_gravar_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "extract_camara_ceap", Extrator(ausente_em=[2027], casa="camara"))
    monkeypatch.setattr(sync, "extract_senado_ceaps", Extrator(ausente_em=[2027], nome="Beto", casa="senado"))
    resumo = sync.run(2026, 2027, ceap=True, emendas=False, http=object(), hoje=date(2027, 1, 3))
    assert resumo["ceap_gravado"] is True and resumo["ceap_anos_sem_arquivo"] == {"camara": [2027], "senado": [2027]}
    saida = json.loads((tmp_path / sync.CEAP_OUTPUT).read_text(encoding="utf-8"))
    assert all("2027" not in reg["por_ano"] for reg in saida.values())


# ── Emendas ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _emendas(n):
    return [{"ano": 2024, "codigo_emenda": str(i)} for i in range(n)]


@pytest.mark.parametrize("novas, truncada", [(100, False), (80, False), (79, True), (10, True), (200, False)])
def test_lista_de_emendas_muito_menor_que_a_anterior_e_tratada_como_truncada(tmp_path, novas, truncada):
    anterior = tmp_path / sync.EMENDAS_OUTPUT
    anterior.write_text(json.dumps(_emendas(100)), encoding="utf-8")
    assert sync._emendas_truncadas(_emendas(novas), anterior) is truncada


def test_sem_arquivo_anterior_ou_ilegivel_a_lista_de_emendas_nao_e_truncada(tmp_path):
    assert sync._emendas_truncadas(_emendas(5), tmp_path / "nao_existe.json") is False
    ruim = tmp_path / "ruim.json"
    ruim.write_text("{", encoding="utf-8")
    assert sync._emendas_truncadas(_emendas(5), ruim) is False


def test_run_preserva_o_arquivo_de_emendas_quando_o_portal_devolve_lista_truncada(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    anterior = tmp_path / sync.EMENDAS_OUTPUT
    anterior.write_text(json.dumps(_emendas(100)), encoding="utf-8")
    monkeypatch.setattr(sync.EmendasExtractor, "fetch_portal", lambda self: _emendas(10))
    resumo = sync.run(2024, 2024, ceap=False, emendas=True, http=object(), hoje=date(2026, 10, 1))
    assert resumo["emendas_gravado"] is False and len(json.loads(anterior.read_text(encoding="utf-8"))) == 100


def test_a_falha_de_uma_fonte_nao_impede_a_gravacao_da_outra(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "PROCESSED_DATA_DIR", tmp_path)
    monkeypatch.setattr(sync, "extract_camara_ceap", Extrator(casa="camara"))
    monkeypatch.setattr(sync, "extract_senado_ceaps", Extrator(falha_em=[2024], nome="Beto", casa="senado"))
    monkeypatch.setattr(sync.EmendasExtractor, "fetch_portal", lambda self: _emendas(3))
    resumo = sync.run(2024, 2024, ceap=True, emendas=True, http=object(), hoje=date(2026, 10, 1))
    assert (resumo["ceap_gravado"], resumo["emendas_gravado"]) == (False, True)
    assert sync.fontes_nao_gravadas(resumo) == ["ceap"] and (tmp_path / sync.EMENDAS_OUTPUT).exists()


# ── Data e módulo ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_numero_de_12_digitos_colado_ao_nome_do_fornecedor_nao_chega_ao_estado_nem_ao_cache():
    acc = CeapAccumulator()
    acc.add(
        "DEPUTADO_FEDERAL", 1, "Ana", 2023, 1, "TAXI", "FULANO SINTETICO DA SILVA 100200300400", "11222333000181", 10.0
    )
    assert "100200300400" not in json.dumps(acc.para_json())
    (reg,) = acc.finalize(FONTES).values()
    assert list(reg["fornecedores"]) == ["FULANO SINTETICO DA SILVA"]
    assert reg["fornecedores"]["FULANO SINTETICO DA SILVA"]["cnpj_cpf"] == "11222333000181"  # o CNPJ do MEI fica
