"""Carga do schema `fin`: funções puras, resolução de pessoas e as seis cargas contra Postgres real."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import text

from etl.pipelines import financas_loader as fin
from etl.pipelines.loader_helpers import (
    LIMITE_REMUNERACAO,
    cnpj_do_fornecedor,
    decimal_de,
    documento_do_doador,
    ler_certidao,
    ler_doacoes,
    nome_do_fornecedor,
    nome_sem_cpf,
    resumos_completos,
    somar_linhas,
    texto_sem_cpf,
    tipo_do_autor,
    uf_da_localidade,
)
from etl.pipelines.pessoa_resolver import Resolucao, ResolvedorDePessoas
from etl.tests.sinteticos import CPF_A, DOZE_DIGITOS_SEM_CPF

# ── funções puras ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_cnpj_do_fornecedor_so_aceita_14_digitos_e_nunca_cpf():
    assert cnpj_do_fornecedor("27.456.163/0001-30") == "27456163000130"
    assert cnpj_do_fornecedor("274.561.630/0013-0") == "27456163000130"  # formatação torta da fonte
    assert cnpj_do_fornecedor("098.765.432-00") is None  # CPF: D3
    assert cnpj_do_fornecedor("000.000.000/0000-1") is None  # enchimento de "CELULAR FUNCIONAL"
    assert cnpj_do_fornecedor("123") is None and cnpj_do_fornecedor(None) is None


def test_nome_do_fornecedor_tira_cpf_embutido_e_nunca_devolve_vazio():
    assert nome_do_fornecedor("BRUNO DE SOUZA 09876543200") == "BRUNO DE SOUZA"
    assert nome_do_fornecedor("EMPRESA 123 LTDA") == "EMPRESA 123 LTDA"  # número curto não é CPF
    assert nome_do_fornecedor("09876543200") == "Fornecedor não identificado"
    # CPF com pontuação ou espaços também sai (decisão D3)
    assert nome_do_fornecedor("JOAO 012.345.678-00") == "JOAO"
    assert nome_do_fornecedor("MEI 012 345 678 00") == "MEI"
    assert nome_do_fornecedor("MEI 012.345.67800 ME") == "MEI ME"
    assert nome_do_fornecedor("EMPRESA 12.345.678/0001-95") == "EMPRESA 12.345.678/0001-95"  # CNPJ não é CPF
    assert nome_do_fornecedor(None) == "Fornecedor não identificado"


@pytest.mark.parametrize(
    "nome",
    [
        "MEI 9876543200",  # CPF que perdeu o zero à esquerda
        "MEI 098-765-432-00",
        "MEI 098/765/432-00",
        "MEI 098_765_432_00",
        "MEI 098,765,432-00",
    ],
)
def test_nome_do_fornecedor_tira_cpf_com_qualquer_separador(nome):
    limpo = nome_do_fornecedor(nome)
    assert limpo == "MEI"


def test_nome_do_fornecedor_preserva_cnpj_e_anos_no_nome():
    assert nome_do_fornecedor("LOJA 2020 2021 2022") == "LOJA 2020 2021 2022"
    assert nome_do_fornecedor("X 12345678901234") == "X 12345678901234"
    assert nome_do_fornecedor("A 12.345.678/0001-95 MEI 098.765.432-00") == "A 12.345.678/0001-95 MEI"


def test_nome_sem_cpf_devolve_none_quando_so_havia_cpf():
    assert nome_sem_cpf("098.765.432-00") is None and nome_sem_cpf("Maria 09876543200") == "Maria"
    assert nome_sem_cpf(None) is None


def test_documento_do_doador_mascara_cpf_completo_e_preserva_cnpj_e_mascara_da_fonte():
    assert documento_do_doador("123.456.789-01") == "***.456.789-**"
    assert documento_do_doador("12345678901") == "***.456.789-**"
    assert documento_do_doador("***.060.603-**") == "***.060.603-**"
    assert documento_do_doador("00.887.169/0001-05") == "00.887.169/0001-05"
    assert documento_do_doador("  ") is None
    # formatos fora do padrão nunca passam crus: CPF que perdeu o zero é mascarado, máscara parcial e lixo viram None
    assert documento_do_doador("9876543200") == "***.765.432-**"
    assert documento_do_doador("123456789**") is None
    assert documento_do_doador("***.060.603-12") is None
    assert documento_do_doador("12345") is None
    assert documento_do_doador("12345678000195") == "12345678000195"
    # 14 dígitos que não são um CNPJ no formato canônico nunca passam crus (podem ser CPF com lixo)
    for estranho in (
        "123.456.789-01 123",
        "12345678/0001-95",
        "12.345.678/000195",
        "00 887 169/0001-05",
        "٠٩٨٧٦٥٤٣٢٠٠",
    ):
        assert documento_do_doador(estranho) is None


def test_tipo_do_autor_distingue_bancada_relator_comissao_e_individual():
    assert tipo_do_autor("BANCADA DA BAHIA", "Emenda de Bancada") == "BANCADA_ESTADUAL"
    assert tipo_do_autor("RELATOR GERAL", "Emenda de Relator") == "RELATOR_GERAL"
    assert tipo_do_autor("COM. DE SAUDE", "Emenda de Comissão") == "COMISSAO_INSTITUCIONAL"
    assert tipo_do_autor("BOHN GASS", "Emenda Individual - Transferências Especiais") == "INDIVIDUAL"
    assert tipo_do_autor(None, None) == "INDIVIDUAL"


def test_uf_da_localidade_le_estado_e_municipio_e_ignora_regiao():
    assert uf_da_localidade("SÃO PAULO (UF)") == "SP"
    assert uf_da_localidade("MATO GROSSO DO SUL (UF)") == "MS"
    assert uf_da_localidade("CAMPINAS - SP") == "SP"
    for sem_uf in ("Nacional", "MÚLTIPLO", "Nordeste", "Exterior", "CIDADE - XX", "", None):
        assert uf_da_localidade(sem_uf) is None


# ── Postgres ──────────────────────────────────────────────────────────────────────────────────────────────────────


def _limpar(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE core.pessoa, core.mandato, fin.despesa_cota, fin.despesa_cota_fornecedor, "
                "fin.despesa_cota_resumo, fin.emenda, fin.remuneracao, fin.declaracao_patrimonio, "
                "fin.doacao_campanha, fin.certidao RESTART IDENTITY CASCADE"
            )
        )


def _pessoa(conn, nome, camara_id=None, senado_id=None, mandato=None):
    pid = conn.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": nome}).scalar()
    for tipo, valor in (("CAMARA_ID", camara_id), ("SENADO_ID", senado_id)):
        if valor:
            conn.execute(
                text(
                    "INSERT INTO core.pessoa_identificador (pessoa_id, fonte_id, tipo, valor) VALUES (:p, "
                    "(SELECT id FROM etl.fonte WHERE codigo = 'CAMARA_API'), :t, :v)"
                ),
                {"p": pid, "t": tipo, "v": str(valor)},
            )
    if mandato:
        conn.execute(
            text(
                "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio, fim) VALUES (:p, "
                "(SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL'), "
                "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i, :f)"
            ),
            {"p": pid, "i": mandato[0], "f": mandato[1]},
        )
    return pid


@pytest.fixture()
def banco(pg_engine):
    _limpar(pg_engine)
    with pg_engine.begin() as conn:
        pessoas = {
            "ana": _pessoa(conn, "Ana Souza", camara_id=100),
            "beto": _pessoa(conn, "Beto Lima", senado_id=200),
            "pai": _pessoa(conn, "Atila Lira", mandato=("2007-02-01", "2022-12-31")),
            "filho": _pessoa(conn, "Atila Lira", mandato=("2023-02-01", None)),
            "joao1": _pessoa(conn, "Joao Dias"),
            "joao2": _pessoa(conn, "Joao Dias"),
            "padre": _pessoa(conn, "Padre Joao", camara_id=300, mandato=("2019-02-01", None)),
            "doutor": _pessoa(conn, "Dr. Joao", camara_id=301, mandato=("2015-02-01", "2016-12-31")),
            "dupla": _pessoa(conn, "Dupla Id", camara_id=500, senado_id=501),
            "senador_sem_mandato": _pessoa(conn, "Rui Alves", senado_id=400),
            "ex_deputado": _pessoa(conn, "Rui Alves", camara_id=401, mandato=("2011-02-01", "2015-01-31")),
            "ex_com_mandato_antigo": _pessoa(conn, "Marta Reis", camara_id=402, mandato=("2011-02-01", "2015-01-31")),
            "senadora_com_mandato_antigo": _pessoa(
                conn, "Marta Reis", senado_id=403, mandato=("2023-02-01", "2031-01-31")
            ),
        }
    yield pessoas
    _limpar(pg_engine)


def _gravar(pasta, nome, conteudo):
    (pasta / nome).write_text(json.dumps(conteudo), encoding="utf-8")


def _oficial(**campos):
    return {"is_synthetic": False, "fonte": "Fonte oficial", **campos}


def _contar(engine, tabela):
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT count(*) FROM fin.{tabela}")).scalar()


def test_resolvedor_usa_id_depois_nome_unico_e_desfaz_homonimo_pelo_mandato(pg_engine, banco):
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert resolvedor.resolver({"camara_id": 100}).pessoa_id == banco["ana"]
        assert resolvedor.resolver({"senado_id": "200", "nome": "outro"}).pessoa_id == banco["beto"]
        assert resolvedor.resolver({"camara_id": 999, "nome": "ANA SOUZA"}).pessoa_id == banco["ana"]
        assert resolvedor.por_nome(["Atila Lira"], 2019).pessoa_id == banco["pai"]
        assert resolvedor.por_nome(["Atila Lira"], 2024).pessoa_id == banco["filho"]
        assert resolvedor.por_nome(["Atila Lira"], None).situacao == "HOMONIMO_NAO_DESAMBIGUADO"
        assert resolvedor.por_nome(["Joao Dias"], 2024).situacao == "HOMONIMO_NAO_DESAMBIGUADO"  # ninguém com mandato
        assert resolvedor.por_nome(["Ninguem"], 2024).situacao == "NAO_CADASTRADO"


def test_resolvedor_compara_o_nome_com_o_titulo_e_so_depois_sem_ele(pg_engine, banco):
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert resolvedor.por_nome(["PADRE JOAO"], 2024).pessoa_id == banco["padre"]  # não confunde com "Dr. João"
        assert resolvedor.por_nome(["Dr. Joao"], 2016).pessoa_id == banco["doutor"]
        assert resolvedor.por_nome(["Joao"]).situacao == "HOMONIMO_NAO_DESAMBIGUADO"  # sem título, os dois casam


def test_resolvedor_descarta_quem_so_teve_mandato_em_outros_anos_mas_nao_o_desconhecido(pg_engine, banco):
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        # o ex-deputado só teve mandato de 2011 a 2015; o senador não tem mandato cadastrado (desconhecido)
        assert resolvedor.por_nome(["Rui Alves"], 2020).pessoa_id == banco["senador_sem_mandato"]
        # as duas têm mandato cadastrado e nenhum cobre 2020: não há como escolher
        assert resolvedor.por_nome(["Marta Reis"], 2020).situacao == "HOMONIMO_NAO_DESAMBIGUADO"
        assert resolvedor.por_nome(["Marta Reis"], 2024).pessoa_id == banco["senadora_com_mandato_antigo"]


def _ceap(**mudancas):
    base = _oficial(
        nome="ANA SOUZA",
        camara_id=100,
        senado_id=None,
        total_notas=5,
        por_ano_tipo={"2023": {"TELEFONIA": 100.5, "PASSAGEM": 200.0}, "2024": {"TELEFONIA": 50.0}},
        fornecedores={
            "VIVO": {"nome": "VIVO", "cnpj_cpf": "02.558.157/0001-62", "total": 150.5, "notas": 3},
            "MEI 09876543200": {"nome": "MEI 09876543200", "cnpj_cpf": "098.765.432-00", "total": 10.0, "notas": 1},
        },
    )
    return {**base, **mudancas}


def test_ceap_grava_totais_fornecedores_sem_cpf_e_resumo_e_e_idempotente(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap(), "SEM PESSOA": _ceap(camara_id=555, nome="NINGUEM")})
    for _ in range(2):
        with pg_engine.begin() as conn:
            resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["parlamentares"] == 1 and resultado["sem_pessoa"] == 1
    assert _contar(pg_engine, "despesa_cota") == 3
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT sum(valor_liquido) FROM fin.despesa_cota")).scalar() == Decimal("350.50")
        forn = conn.execute(text("SELECT nome, cnpj FROM fin.despesa_cota_fornecedor ORDER BY nome")).all()
        assert forn == [("MEI", None), ("VIVO", "02558157000162")]
        assert conn.execute(text("SELECT total_notas FROM fin.despesa_cota_resumo")).scalar() == 5


def test_ceap_ignora_registro_sem_proveniencia_ou_sem_detalhe_por_ano(pg_engine, banco, tmp_path):
    sintetico = _ceap(is_synthetic=True)
    antigo = _ceap(por_ano_tipo=None)
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": sintetico, "B": antigo})
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["despesas"] == 0 and _contar(pg_engine, "despesa_cota") == 0
    assert resultado["sem_proveniencia"] == 1 and resultado["sem_detalhe_por_ano"] == 1


def test_arquivo_sem_registro_utilizavel_nao_apaga_o_que_ja_esta_no_banco(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"X": _ceap(is_synthetic=True)})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    assert _contar(pg_engine, "despesa_cota") == 3


def _emenda(codigo, autor, **mudancas):
    base = _oficial(
        politician_name=autor,
        autor_codigo="1",
        ano=2024,
        codigo_emenda=codigo,
        tipo_emenda="Emenda Individual - Transferências Especiais",
        valor_empenhado=1000.0,
        valor_pago=400.0,
        localidade_destino="SÃO PAULO (UF)",
        funcao="Saúde",
    )
    return {**base, **mudancas}


def test_emendas_classificam_autor_e_resolvem_homonimo_pelo_ano(pg_engine, banco, tmp_path):
    emendas = [
        _emenda("1", "Ana Souza"),
        _emenda("2", "Atila Lira", ano=2019),
        _emenda("3", "Atila Lira", ano=2024),
        _emenda("4", "Joao Dias"),
        _emenda("5", "Fulano Antigo"),
        _emenda("6", "BANCADA DA BAHIA", tipo_emenda="Emenda de Bancada", localidade_destino="Salvador - BA"),
        _emenda("7", "RELATOR GERAL", tipo_emenda="Emenda de Relator", localidade_destino="Nacional", funcao=None),
    ]
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, emendas)
    with pg_engine.begin() as conn:
        resultado = fin.carregar_emendas(conn, tmp_path)
    assert resultado["emendas"] == 7 and resultado["IDENTIFICADO"] == 3 and resultado["INSTITUCIONAL"] == 2
    with pg_engine.connect() as conn:
        linhas = {
            r.codigo_emenda: r
            for r in conn.execute(
                text("SELECT codigo_emenda, pessoa_id, autor_situacao, tipo_autor, uf FROM fin.emenda")
            )
        }
    assert linhas["1"].pessoa_id == banco["ana"] and linhas["1"].uf == "SP"
    assert linhas["2"].pessoa_id == banco["pai"] and linhas["3"].pessoa_id == banco["filho"]
    assert linhas["4"].autor_situacao == "HOMONIMO_NAO_DESAMBIGUADO" and linhas["4"].pessoa_id is None
    assert linhas["5"].autor_situacao == "NAO_CADASTRADO" and linhas["5"].pessoa_id is None
    assert linhas["6"].tipo_autor == "BANCADA_ESTADUAL" and linhas["6"].uf == "BA"
    assert linhas["7"].tipo_autor == "RELATOR_GERAL" and linhas["7"].uf is None


def test_emendas_recarga_mantem_uid_atualiza_valor_e_remove_o_que_saiu_da_fonte(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza", funcao=None), _emenda("2", "Ana Souza")])
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        uid = conn.execute(text("SELECT uid FROM fin.emenda WHERE codigo_emenda = '1'")).scalar()
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza", funcao=None, valor_pago=900.0)])
    with pg_engine.begin() as conn:
        resultado = fin.carregar_emendas(conn, tmp_path)
    assert resultado["removidas"] == 1 and _contar(pg_engine, "emenda") == 1
    with pg_engine.connect() as conn:
        linha = conn.execute(text("SELECT uid, valor_pago FROM fin.emenda WHERE codigo_emenda = '1'")).one()
    assert linha.uid == uid and linha.valor_pago == Decimal("900.00")  # funcao nula também casa na chave natural


def test_emendas_invalidas_ou_sem_proveniencia_sao_contadas_e_nao_gravadas(pg_engine, banco, tmp_path):
    ruins = [
        _emenda("1", "Ana Souza", is_synthetic=True),
        _emenda("2", "Ana Souza", ano=1990),
        _emenda("3", "Ana Souza", valor_empenhado=None),
        _emenda("4", ""),
    ]
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, ruins + [_emenda("5", "Ana Souza")])
    with pg_engine.begin() as conn:
        resultado = fin.carregar_emendas(conn, tmp_path)
    assert resultado["sem_proveniencia"] == 1 and resultado["invalidas"] == 3 and resultado["emendas"] == 1


def test_remuneracao_patrimonio_doacoes_e_certidoes(pg_engine, banco, tmp_path):
    _gravar(
        tmp_path,
        fin.REMUNERACAO_ARQUIVO,
        _oficial(
            registros=[
                {"camara_id": 100, "ano": 2024, "mes": 1, "salario_bruto": 44008.52, "salario_liquido": None},
                {"camara_id": 100, "ano": 2024, "mes": 13, "salario_bruto": 1, "salario_liquido": None},
                {"camara_id": 999, "ano": 2024, "mes": 1, "salario_bruto": 1, "salario_liquido": None},
            ]
        ),
    )
    _gravar(
        tmp_path,
        fin.PATRIMONIO_ARQUIVO,
        [
            _oficial(
                nome_civil="Ana Souza", camara_id=100, ano_eleicao=2022, valor_declarado_brl=1500.5, quantidade_bens=2
            )
        ],
    )
    _gravar(
        tmp_path,
        fin.DOACOES_ARQUIVO,
        [
            _oficial(
                nome_civil="Ana Souza",
                camara_id=100,
                ano_eleicao=2022,
                doadores=[
                    {
                        "nome_doador": "Partido",
                        "cpf_cnpj_doador": "00.887.169/0001-05",
                        "valor_doado": 10,
                        "tipo_receita": "x",
                    },
                    {"nome_doador": "Pessoa", "cpf_cnpj_doador": "12345678901", "valor_doado": 5},
                    {"nome_doador": "Sem valor", "valor_doado": None},
                ],
            )
        ],
    )
    _gravar(
        tmp_path,
        fin.CERTIDOES_ARQUIVO,
        [
            _oficial(
                nome_civil="Ana Souza",
                camara_id=100,
                orgao="TSE",
                tipo_certidao="Registro 2018",
                status_ficha="Declarada: indeferido",
                detalhes="d",
                numero_processo="123",
            )
        ],
    )
    with pg_engine.begin() as conn:
        assert fin.carregar_remuneracao(conn, tmp_path)["meses"] == 1
        assert fin.carregar_patrimonio(conn, tmp_path)["declaracoes"] == 1
        assert fin.carregar_doacoes(conn, tmp_path)["linhas"] == 2
        assert fin.carregar_certidoes(conn, tmp_path)["certidoes"] == 1
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT salario_liquido FROM fin.remuneracao")).scalar() is None  # nunca zero
        docs = sorted(conn.execute(text("SELECT doador_documento FROM fin.doacao_campanha")).scalars())
        assert docs == ["***.456.789-**", "00.887.169/0001-05"]


def test_carregar_isola_falhas_e_relata_todas(pg_engine, banco, tmp_path, monkeypatch):
    chamadas = []

    def ok(chave):
        return lambda conn, pasta: chamadas.append(chave) or {"ok": chave}

    def quebra(conn, pasta):
        raise ValueError("arquivo corrompido")

    monkeypatch.setattr(fin, "CARGAS", (("ceap", quebra), ("emendas", ok("emendas")), ("doacoes", quebra)))
    with pytest.raises(RuntimeError) as erro:
        fin.carregar(pg_engine, tmp_path)
    assert chamadas == ["emendas"]
    assert "ceap: arquivo corrompido" in str(erro.value) and "doacoes: arquivo corrompido" in str(erro.value)


# ── reconciliação arquivo × banco ─────────────────────────────────────────────────────────────────────────────────


def test_reconciliacao_zera_nas_emendas_e_explica_a_diferenca_de_quem_nao_tem_pessoa(pg_engine, banco, tmp_path):
    from etl.scripts import reconciliar_financas as rec

    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza"), _emenda("2", "Fulano Antigo", valor_pago=10.0)])
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap(), "SEM PESSOA": _ceap(camara_id=555, nome="NINGUEM")})
    _gravar(tmp_path, fin.REMUNERACAO_ARQUIVO, _oficial(registros=[]))
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [])
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        relatorio = rec.reconciliar(conn, tmp_path)
    assert relatorio["emendas_empenhado"] and relatorio["emendas_pago"]
    assert all(not linha["diferenca"] for linha in relatorio["emendas_empenhado"] + relatorio["emendas_pago"])
    assert relatorio["emendas_empenhado"][0]["arquivo"] == Decimal("2000.00")
    ceap = {linha["ano"]: linha for linha in relatorio["ceap"]}
    assert ceap[2023]["arquivo"] == Decimal("601.00") and ceap[2023]["banco"] == Decimal("300.50")
    assert relatorio["emendas_sem_pessoa"] == {"IDENTIFICADO": 1, "NAO_CADASTRADO": 1}
    assert rec.divergencias(relatorio) == []  # banco abaixo do arquivo é esperado; emendas batem


def test_reconciliacao_acusa_emenda_diferente_e_banco_acima_do_arquivo():
    from etl.scripts import reconciliar_financas as rec

    relatorio = {
        "emendas_empenhado": rec.comparar({2024: Decimal(100)}, {2024: Decimal(90)}),
        "emendas_pago": [],
        "ceap": rec.comparar({2024: Decimal(100)}, {2024: Decimal(150)}),
        "remuneracao_bruta": [],
        "doacoes": [],
    }
    problemas = rec.divergencias(relatorio)
    assert len(problemas) == 2 and "emendas_empenhado 2024" in problemas[0] and "ceap 2024" in problemas[1]


# ── proteções da carga ────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "invalido", ["NaN", "Infinity", "-Infinity", "sNaN", float("inf"), None, "", "abc", "1e15", "1E+999999", "-1e13"]
)
def test_decimal_de_rejeita_nao_finito_e_fora_da_faixa_do_banco(invalido):
    assert decimal_de(invalido) is None


def test_decimal_de_aceita_zero_e_valores_normais():
    assert decimal_de("0") == Decimal(0) and decimal_de("12.5") == Decimal("12.5") and decimal_de(-5) == Decimal(-5)


def test_resolvedor_tolera_identificador_absurdo(pg_engine, banco):
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert resolvedor.por_identificador(camara_id=float("inf")) is None
        assert resolvedor.por_identificador(camara_id="abc") is None
        assert resolvedor.por_identificador(camara_id=100) == banco["ana"]


def _carga_com_dado_bom(pasta):
    """Um arquivo bom por carga, para depois recarregar um arquivo ruim e conferir que o banco ficou intacto."""
    _gravar(pasta, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})
    _gravar(pasta, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza")])
    _gravar(
        pasta,
        fin.REMUNERACAO_ARQUIVO,
        _oficial(registros=[{"camara_id": 100, "ano": 2024, "mes": 1, "salario_bruto": 1}]),
    )
    _gravar(pasta, fin.PATRIMONIO_ARQUIVO, [_oficial(camara_id=100, ano_eleicao=2022, valor_declarado_brl=10)])
    _gravar(
        pasta,
        fin.DOACOES_ARQUIVO,
        [_oficial(camara_id=100, ano_eleicao=2022, doadores=[{"nome_doador": "D", "valor_doado": 5}])],
    )
    _gravar(
        pasta,
        fin.CERTIDOES_ARQUIVO,
        [_oficial(camara_id=100, orgao="TSE", tipo_certidao="Registro", status_ficha="Deferido")],
    )


TABELAS_POR_CARGA = {
    "ceap": ("despesa_cota", "despesa_cota_fornecedor", "despesa_cota_resumo"),
    "emendas": ("emenda",),
    "remuneracao": ("remuneracao",),
    "patrimonio": ("declaracao_patrimonio",),
    "doacoes": ("doacao_campanha",),
    "certidoes": ("certidao",),
}
ARQUIVO_DA_CARGA = {
    "ceap": fin.CEAP_ARQUIVO,
    "emendas": fin.EMENDAS_ARQUIVO,
    "remuneracao": fin.REMUNERACAO_ARQUIVO,
    "patrimonio": fin.PATRIMONIO_ARQUIVO,
    "doacoes": fin.DOACOES_ARQUIVO,
    "certidoes": fin.CERTIDOES_ARQUIVO,
}
FUNCAO_DA_CARGA = dict(fin.CARGAS)


def _fotografia(engine, carga):
    with engine.connect() as conn:
        return {t: sorted(map(tuple, conn.execute(text(f"SELECT * FROM fin.{t}")))) for t in TABELAS_POR_CARGA[carga]}


def _marcar_sintetico(carga, corpo):
    def marcar(x):
        return {**x, "is_synthetic": True} if isinstance(x, dict) else x

    if carga == "ceap":
        return {k: marcar(v) for k, v in corpo.items()}
    if carga == "remuneracao":
        return marcar(corpo)
    return [marcar(x) for x in corpo]


def _vazio_valido(carga):
    """Arquivo bem formado, com proveniência, mas sem nenhum registro."""
    if carga == "ceap":
        return {}
    if carga == "remuneracao":
        return _oficial(registros=[])
    return []


@pytest.mark.parametrize("carga", list(TABELAS_POR_CARGA))
@pytest.mark.parametrize("ruim", ["ausente", "vazio", "vazio_com_proveniencia", "sintetico", "tipo_errado"])
def test_arquivo_ruim_nunca_apaga_nenhuma_das_seis_tabelas(pg_engine, banco, tmp_path, carga, ruim):
    _carga_com_dado_bom(tmp_path)
    with pg_engine.begin() as conn:
        FUNCAO_DA_CARGA[carga](conn, tmp_path)
    antes = _fotografia(pg_engine, carga)
    assert all(antes.values())  # a carga boa gravou em todas as tabelas dela

    arquivo = tmp_path / ARQUIVO_DA_CARGA[carga]
    if ruim == "ausente":
        arquivo.unlink()
    elif ruim == "vazio":
        _gravar(tmp_path, arquivo.name, {} if carga in ("ceap", "remuneracao") else [])
    elif ruim == "vazio_com_proveniencia":
        _gravar(tmp_path, arquivo.name, _vazio_valido(carga))
    elif ruim == "sintetico":
        _gravar(tmp_path, arquivo.name, _marcar_sintetico(carga, json.loads(arquivo.read_text(encoding="utf-8"))))
    else:
        _gravar(tmp_path, arquivo.name, "texto" if carga != "ceap" else [1, 2])

    with pg_engine.begin() as conn:
        resultado = FUNCAO_DA_CARGA[carga](conn, tmp_path)
    assert _fotografia(pg_engine, carga) == antes
    # a carga relatou POR QUE não gravou: arquivo que não existe é uma coisa, arquivo que existe e não serve é outra
    sem_proveniencia_no_arquivo = carga == "remuneracao" and ruim in (
        "vazio",
        "sintetico",
    )  # o arquivo inteiro é recusado
    if ruim == "ausente":
        assert resultado == {"arquivo_ausente": 1}
    elif ruim == "tipo_errado" or sem_proveniencia_no_arquivo:
        assert resultado == {"formato_invalido": 1}
    elif ruim == "sintetico":
        assert resultado["sem_proveniencia"] == 1  # o registro marcado como sintético é contado e descartado
    else:  # vazio ou vazio com proveniência: o arquivo serve, mas não tem nenhum registro utilizável
        assert resultado.get("sem_proveniencia", 0) == 0 and "formato_invalido" not in resultado
    assert not _gravou(resultado)


def _gravou(resultado):
    """True se a carga relatou alguma linha gravada em alguma tabela."""
    return any(resultado.get(chave) for chave in ("despesas", "emendas", "meses", "declaracoes", "linhas", "certidoes"))


def test_doacoes_so_com_prestacoes_sem_linhas_utilizaveis_nao_apagam_o_banco(pg_engine, banco, tmp_path):
    _carga_com_dado_bom(tmp_path)
    with pg_engine.begin() as conn:
        fin.carregar_doacoes(conn, tmp_path)
    antes = _fotografia(pg_engine, "doacoes")
    for doadores in ([], [{"nome_doador": "D", "valor_doado": None}], [{"nome_doador": "D", "valor_doado": "abc"}]):
        _gravar(tmp_path, fin.DOACOES_ARQUIVO, [_oficial(camara_id=100, ano_eleicao=2022, doadores=doadores)])
        with pg_engine.begin() as conn:
            assert fin.carregar_doacoes(conn, tmp_path)["linhas"] == 0
        assert _fotografia(pg_engine, "doacoes") == antes


@pytest.mark.parametrize("ordem", ["cheia_primeiro", "vazia_primeiro"])
def test_doacoes_a_prestacao_mais_completa_vale_qualquer_que_seja_a_ordem(pg_engine, banco, tmp_path, ordem):
    cheia = _oficial(camara_id=100, ano_eleicao=2022, doadores=[{"nome_doador": "A", "valor_doado": 1}] * 2)
    vazia = _oficial(camara_id=100, ano_eleicao=2022, doadores=[])
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [cheia, vazia] if ordem == "cheia_primeiro" else [vazia, cheia])
    for _ in range(2):  # recarregar não duplica
        with pg_engine.begin() as conn:
            resultado = fin.carregar_doacoes(conn, tmp_path)
    assert resultado["linhas"] == 2 and resultado["prestacao_descartada"] == 1
    assert _contar(pg_engine, "doacao_campanha") == 2


def test_doacoes_no_empate_de_linhas_vale_a_prestacao_de_maior_valor(pg_engine, banco, tmp_path):
    pequena = _oficial(camara_id=100, ano_eleicao=2022, doadores=[{"nome_doador": "P", "valor_doado": 1}])
    grande = _oficial(camara_id=100, ano_eleicao=2022, doadores=[{"nome_doador": "G", "valor_doado": 99}])
    for ordem in ([pequena, grande], [grande, pequena]):
        _gravar(tmp_path, fin.DOACOES_ARQUIVO, ordem)
        with pg_engine.begin() as conn:
            fin.carregar_doacoes(conn, tmp_path)
        with pg_engine.connect() as conn:
            assert conn.execute(text("SELECT doador_nome FROM fin.doacao_campanha")).scalars().all() == ["G"]


def test_doador_com_cpf_no_nome_nao_grava_o_cpf(pg_engine, banco, tmp_path):
    doadores = [{"nome_doador": "MEI JOAO 012.345.678-00", "cpf_cnpj_doador": "123456789**", "valor_doado": 5}]
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [_oficial(camara_id=100, ano_eleicao=2022, doadores=doadores)])
    with pg_engine.begin() as conn:
        fin.carregar_doacoes(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert tuple(conn.execute(text("SELECT doador_nome, doador_documento FROM fin.doacao_campanha")).one()) == (
            "MEI JOAO",
            None,
        )


@pytest.mark.parametrize("carga", ["remuneracao", "patrimonio", "doacoes", "certidoes"])
def test_recarregar_as_cargas_do_tse_e_da_remuneracao_e_idempotente(pg_engine, banco, tmp_path, carga):
    _carga_com_dado_bom(tmp_path)
    for _ in range(2):
        with pg_engine.begin() as conn:
            FUNCAO_DA_CARGA[carga](conn, tmp_path)
    assert all(len(linhas) == 1 for linhas in _fotografia(pg_engine, carga).values())


def test_patrimonio_e_certidoes_gravam_as_colunas_certas(pg_engine, banco, tmp_path):
    _gravar(
        tmp_path,
        fin.PATRIMONIO_ARQUIVO,
        [
            _oficial(
                camara_id=100, ano_eleicao=2022, valor_declarado_brl=1500.5, quantidade_bens=2, detalhes_bens="casa"
            )
        ],
    )
    _gravar(
        tmp_path,
        fin.CERTIDOES_ARQUIVO,
        [
            _oficial(
                camara_id=100,
                orgao="TSE",
                tipo_certidao="Registro 2018",
                status_ficha="Indeferido",
                detalhes="d",
                numero_processo="123",
            )
        ],
    )
    with pg_engine.begin() as conn:
        fin.carregar_patrimonio(conn, tmp_path)
        fin.carregar_certidoes(conn, tmp_path)
    with pg_engine.connect() as conn:
        pat = conn.execute(
            text("SELECT ano_eleicao, valor_declarado, quantidade_bens, detalhes FROM fin.declaracao_patrimonio")
        ).one()
        cert = conn.execute(text("SELECT orgao, tipo, situacao, detalhes, numero_processo FROM fin.certidao")).one()
    assert tuple(pat) == (2022, Decimal("1500.50"), 2, "casa")
    assert tuple(cert) == ("TSE", "Registro 2018", "Indeferido", "d", "123")


def test_remuneracao_item_malformado_nao_derruba_a_carga(pg_engine, banco, tmp_path):
    registros = [None, "x", {"camara_id": 100, "ano": 2024, "mes": 1, "salario_bruto": 10}]
    _gravar(tmp_path, fin.REMUNERACAO_ARQUIVO, _oficial(registros=registros))
    with pg_engine.begin() as conn:
        resultado = fin.carregar_remuneracao(conn, tmp_path)
    assert resultado["meses"] == 1 and resultado["invalidas"] == 2


def test_ceap_item_de_fornecedor_malformado_nao_derruba_a_carga(pg_engine, banco, tmp_path):
    _gravar(
        tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(fornecedores={"x": "10", "y": None, "z": {"nome": "OK", "total": 1}})}
    )
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    assert _contar(pg_engine, "despesa_cota_fornecedor") == 1
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"B": _ceap(fornecedores=[{"total": 10}])})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)  # lista no lugar do dicionário: ignorada, sem exceção
    assert _contar(pg_engine, "despesa_cota_fornecedor") == 0


def test_ceap_sem_total_de_notas_nao_inventa_zero(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(total_notas=None)})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    assert _contar(pg_engine, "despesa_cota") == 3 and _contar(pg_engine, "despesa_cota_resumo") == 0


def test_ceap_mesma_fonte_repetida_nao_dobra_mas_fontes_diferentes_somam(pg_engine, banco, tmp_path):
    def entrada(**campos):
        base = {
            "nome": "X",
            "camara_id": None,
            "senado_id": None,
            "por_ano_tipo": {"2023": {"T": 100.0}},
            "total_notas": 4,
            "fornecedores": {"V": {"nome": "V", "cnpj_cpf": "02.558.157/0001-62", "total": 100.0, "notas": 4}},
        }
        return _ceap(**{**base, **campos})

    ceap = {
        "DUPLA (Câmara)": entrada(camara_id=500),
        "DUPLA (Senado)": entrada(senado_id=501, por_ano_tipo={"2023": {"T": 30.0}}, total_notas=1),
        "DUPLA A. (Câmara, outra grafia)": entrada(camara_id=500),  # mesma fonte e mesmo dado: não dobra
    }
    _gravar(tmp_path, fin.CEAP_ARQUIVO, ceap)
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["mesma_fonte_repetida"] == 1  # a grafia repetida da Câmara (contada nas despesas)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT valor_liquido FROM fin.despesa_cota")).scalars().all() == [Decimal("130.00")]
        assert tuple(conn.execute(text("SELECT valor_total, notas FROM fin.despesa_cota_fornecedor")).one()) == (
            Decimal("200.00"),
            8,
        )
        assert conn.execute(text("SELECT total_notas FROM fin.despesa_cota_resumo")).scalar() == 5


def test_ceap_tres_entradas_agrupam_por_fonte_antes_de_somar(pg_engine, banco, tmp_path):
    base = {"por_ano_tipo": {"2023": {"T": 100.0}}, "fornecedores": {}, "total_notas": 1}
    ceap = {
        "A": _ceap(camara_id=500, **base),
        "C": _ceap(camara_id=None, senado_id=501, **{**base, "por_ano_tipo": {"2023": {"T": 40.0}}}),
        "B": _ceap(camara_id=500, **base),  # mesma fonte de A: não pode ser comparada com a soma A+C
    }
    _gravar(tmp_path, fin.CEAP_ARQUIVO, ceap)
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT valor_liquido FROM fin.despesa_cota")).scalars().all() == [Decimal("140.00")]


def test_emenda_sem_valor_pago_fica_de_fora_em_vez_de_virar_zero(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza", valor_pago=None), _emenda("2", "Ana Souza")])
    with pg_engine.begin() as conn:
        resultado = fin.carregar_emendas(conn, tmp_path)
    assert resultado["invalidas"] == 1 and resultado["emendas"] == 1


def test_emendas_com_a_mesma_chave_somam_e_o_total_bate_com_o_arquivo(pg_engine, banco, tmp_path):
    repetidas = [
        _emenda(None, "COM. DE SAUDE", tipo_emenda="Emenda de Comissão", valor_empenhado=1000.0, valor_pago=100.0),
        _emenda(None, "COM. DE SAUDE", tipo_emenda="Emenda de Comissão", valor_empenhado=2000.0, valor_pago=200.0),
    ]
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, repetidas)
    with pg_engine.begin() as conn:
        resultado = fin.carregar_emendas(conn, tmp_path)
    assert resultado["emendas"] == 1 and resultado["chave_repetida"] == 1
    with pg_engine.connect() as conn:
        assert tuple(conn.execute(text("SELECT valor_empenhado, valor_pago FROM fin.emenda")).one()) == (
            Decimal("3000.00"),
            Decimal("300.00"),
        )


def test_emenda_de_autor_nao_cadastrado_passa_a_identificada_quando_a_pessoa_aparece(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Zeca Novo")])
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT autor_situacao FROM fin.emenda")).scalar() == "NAO_CADASTRADO"
    with pg_engine.begin() as conn:
        novo = _pessoa(conn, "Zeca Novo", camara_id=777)
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert tuple(conn.execute(text("SELECT autor_situacao, pessoa_id FROM fin.emenda")).one()) == (
            "IDENTIFICADO",
            novo,
        )


def _arquivo_com(carga, n):
    """Conteúdo válido do arquivo da carga com `n` linhas (uma pessoa, chaves diferentes)."""
    if carga == "ceap":
        return {"ANA SOUZA": _ceap(por_ano_tipo={"2023": {f"T{i}": 1.0 for i in range(n)}}, fornecedores={})}
    if carga == "emendas":
        return [_emenda(str(i), "Ana Souza") for i in range(n)]
    if carga == "remuneracao":
        meses = [(2000 + i // 12, i % 12 + 1) for i in range(n)]
        return _oficial(registros=[{"camara_id": 100, "ano": a, "mes": m, "salario_bruto": 1} for a, m in meses])
    if carga == "patrimonio":
        return [_oficial(camara_id=100, ano_eleicao=2000 + i, valor_declarado_brl=1) for i in range(n)]
    if carga == "doacoes":
        return [
            _oficial(
                camara_id=100,
                ano_eleicao=2022,
                doadores=[{"nome_doador": f"D{i}", "valor_doado": 1} for i in range(n)],
            )
        ]
    return [_oficial(camara_id=100, orgao="TSE", tipo_certidao=f"T{i}", status_ficha="ok") for i in range(n)]


def _linhas_da_tabela_principal(engine, carga):
    return sum(_contar(engine, t) for t in TABELAS_POR_CARGA[carga][:1])


def _rodar(engine, carga, pasta, conteudo):
    _gravar(pasta, ARQUIVO_DA_CARGA[carga], conteudo)
    with engine.begin() as conn:
        FUNCAO_DA_CARGA[carga](conn, pasta)


def test_diaria_desde_2019_nao_apaga_o_ano_de_2018_de_uma_carga_manual_mesmo_com_reducao_pequena(
    pg_engine, banco, tmp_path, monkeypatch
):
    """Regressão do PR #46: a guarda por quantidade de linhas (50%) deixava passar a perda de um ano inteiro de gasto."""
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    tipos = [f"TIPO{i}" for i in range(11)]
    desde_2018 = {"2018": {"TELEFONIA": 10.0}, "2019": {t: 5.0 for t in tipos}}
    desde_2019 = {"2019": {t: 5.0 for t in tipos}}

    def carregar(por_ano_tipo):
        _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap(por_ano_tipo=por_ano_tipo)})
        with pg_engine.begin() as conn:
            return fin.carregar_ceap(conn, tmp_path)

    carregar(desde_2018)
    assert _contar(pg_engine, "despesa_cota") == 12
    with pytest.raises(RuntimeError, match="anos que o banco já tem.*camara.*2018.*nada foi alterado"):
        carregar(desde_2019)  # 12 -> 11 linhas: bem acima de 50%, mas o ano de 2018 sumiria
    assert _contar(pg_engine, "despesa_cota") == 12  # tabela inteira intacta (a recusa vem antes de qualquer DELETE)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fin.despesa_cota WHERE ano = 2018")).scalar() == 1

    carregar(desde_2018)  # a mesma janela de antes continua passando (idempotente)
    monkeypatch.setenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, "1")  # remoção legítima, liberada de propósito
    carregar(desde_2019)
    assert _contar(pg_engine, "despesa_cota") == 11


def test_carga_que_acrescenta_anos_ou_mantem_os_mesmos_passa_sem_a_variavel(pg_engine, banco, tmp_path, monkeypatch):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    for por_ano_tipo in (
        {"2023": {"T": 1.0}},
        {"2023": {"T": 2.0}, "2024": {"T": 1.0}},
        {"2023": {"T": 3.0}, "2024": {"T": 1.0}},
    ):
        _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap(por_ano_tipo=por_ano_tipo)})
        with pg_engine.begin() as conn:
            fin.carregar_ceap(conn, tmp_path)


@pytest.mark.parametrize("carga", list(TABELAS_POR_CARGA))
def test_carga_que_encolheria_a_tabela_para_menos_da_metade_aborta_sem_alterar_o_banco(
    pg_engine, banco, tmp_path, monkeypatch, carga
):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 20))
    assert _linhas_da_tabela_principal(pg_engine, carga) == 20
    antes = _fotografia(pg_engine, carga)

    with pytest.raises(RuntimeError, match="nada foi alterado"):
        _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 3))
    assert _fotografia(pg_engine, carga) == antes

    monkeypatch.setenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, "1")  # redução legítima, liberada de propósito
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 3))
    assert _linhas_da_tabela_principal(pg_engine, carga) == 3


@pytest.mark.parametrize("carga", list(TABELAS_POR_CARGA))
def test_limite_exato_da_protecao_metade_passa_e_menos_que_a_metade_aborta(
    pg_engine, banco, tmp_path, monkeypatch, carga
):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 20))
    with pytest.raises(RuntimeError, match="nada foi alterado"):
        _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 9))
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 10))  # exatamente 50%
    assert _linhas_da_tabela_principal(pg_engine, carga) == 10


def test_tabela_com_menos_linhas_que_o_minimo_nao_dispara_a_protecao(pg_engine, banco, tmp_path, monkeypatch):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", fin.MINIMO_PARA_GUARDA - 1))
    _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", 1))
    assert _contar(pg_engine, "emenda") == 1


def test_o_minimo_exato_ja_dispara_a_protecao(pg_engine, banco, tmp_path, monkeypatch):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", fin.MINIMO_PARA_GUARDA))
    with pytest.raises(RuntimeError, match="nada foi alterado"):
        _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", 1))


def test_a_protecao_so_libera_com_o_valor_exato_1(pg_engine, banco, tmp_path, monkeypatch):
    _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", 20))
    monkeypatch.setenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, "true")
    with pytest.raises(RuntimeError, match="nada foi alterado"):
        _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", 2))


def test_carga_que_falha_no_meio_desfaz_o_proprio_delete(pg_engine, banco, tmp_path, monkeypatch):
    _carga_com_dado_bom(tmp_path)
    with pg_engine.begin() as conn:
        fin.carregar_remuneracao(conn, tmp_path)
    antes = _fotografia(pg_engine, "remuneracao")

    def quebra(conn, sql, linhas):
        raise ValueError("falha ao inserir")

    monkeypatch.setattr(fin, "_inserir", quebra)
    with pytest.raises(ValueError):
        with pg_engine.begin() as conn:
            fin.carregar_remuneracao(conn, tmp_path)
    assert _fotografia(pg_engine, "remuneracao") == antes


def test_carregar_com_as_seis_cargas_reais_devolve_um_resultado_por_carga(pg_engine, banco, tmp_path):
    _carga_com_dado_bom(tmp_path)
    resultados = fin.carregar(pg_engine, tmp_path)
    assert set(resultados) == set(TABELAS_POR_CARGA)
    assert resultados["emendas"]["emendas"] == 1 and resultados["doacoes"]["linhas"] == 1


# ── script de reconciliação: código de saída ──────────────────────────────────────────────────────────────────────


def _roda_reconciliacao(monkeypatch, capsys, pg_engine, pasta, argv):
    import app.core.database as banco_da_api

    from etl.scripts import reconciliar_financas as rec

    monkeypatch.setattr(banco_da_api, "engine", pg_engine)
    monkeypatch.setattr(rec, "PROCESSED_DATA_DIR", pasta)
    return rec.main(argv), capsys.readouterr().out


def test_reconciliacao_sai_com_zero_quando_bate_e_um_quando_a_emenda_diverge(
    pg_engine, banco, tmp_path, monkeypatch, capsys
):
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza")])
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {})
    _gravar(tmp_path, fin.REMUNERACAO_ARQUIVO, _oficial(registros=[]))
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [])
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)

    codigo, saida = _roda_reconciliacao(monkeypatch, capsys, pg_engine, tmp_path, ["--json"])
    corpo = json.loads(saida)
    assert codigo == 0 and corpo["problemas"] == [] and corpo["emendas_empenhado"][0]["arquivo"] == "1000.00"

    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza", valor_empenhado=5000.0)])
    codigo, saida = _roda_reconciliacao(monkeypatch, capsys, pg_engine, tmp_path, [])
    assert codigo == 1 and "DIVERGÊNCIAS" in saida and "emendas_empenhado 2024" in saida


def test_reconciliacao_acusa_pago_remuneracao_e_doacoes_com_banco_acima_do_arquivo():
    from etl.scripts import reconciliar_financas as rec

    acima = rec.comparar({2024: Decimal(1)}, {2024: Decimal(2)})
    relatorio = {
        "emendas_empenhado": [],
        "emendas_pago": rec.comparar({2024: Decimal(5)}, {2024: Decimal(4)}),
        "ceap": [],
        "remuneracao_bruta": acima,
        "doacoes": acima,
    }
    problemas = rec.divergencias(relatorio)
    assert len(problemas) == 3
    assert any("emendas_pago" in p for p in problemas) and any("remuneracao_bruta" in p for p in problemas)
    assert any("doacoes" in p for p in problemas)


def test_reconciliacao_nao_quebra_com_itens_malformados():
    from etl.scripts import reconciliar_financas as rec

    assert rec.totais_ceap_do_arquivo({"A": _oficial(por_ano_tipo=[1])}) == {}
    assert rec.totais_remuneracao_do_arquivo(_oficial(registros=[None, 3])) == {}
    assert rec.totais_doacoes_do_arquivo([_oficial(ano_eleicao=2022, doadores=5)]) == {}


def test_valor_pago_zero_e_total_de_notas_zero_sao_dados_validos_e_entram(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza", valor_pago=0)])
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(total_notas=0)})
    with pg_engine.begin() as conn:
        assert fin.carregar_emendas(conn, tmp_path)["emendas"] == 1
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT valor_pago FROM fin.emenda")).scalar() == Decimal(0)
        assert conn.execute(text("SELECT total_notas FROM fin.despesa_cota_resumo")).scalar() == 0


# ── revisão final: CPF, faixas das colunas, resolvedor e reconciliação ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "nome",
    [
        "JOAO 012.345.678 - 00",  # separador com espaços dos dois lados
        "JOAO 012 . 345 . 678 - 00",
        "JOAO ٠٩٨٧٦٥٤٣٢٠٠",  # dígitos árabes-índicos
        "JOAO ０９８７６５４３２００",  # largura total
        "JOAO 9876543200",
    ],
)
def test_cpf_nao_sobrevive_em_nenhuma_grafia_do_nome(nome):
    assert nome_do_fornecedor(nome) == "JOAO" and nome_sem_cpf(nome) == "JOAO"


def test_texto_nao_grava_a_repr_de_dict_ou_lista_e_inteiro_nao_trunca_nem_aceita_bool():
    from etl.pipelines.loader_helpers import inteiro, texto

    assert texto({"a": 1}) is None and texto([1]) is None and texto(float("nan")) is None and texto(" x ") == "x"
    assert inteiro(True) is None and inteiro(2019.9) is None and inteiro(2019.0) == 2019 and inteiro("12") == 12


def test_decimal_de_respeita_o_limite_de_cada_coluna():
    assert decimal_de("999999999.99", LIMITE_REMUNERACAO) == Decimal("999999999.99")
    assert decimal_de("10000000000", LIMITE_REMUNERACAO) is None  # 10**10 já não cabe em numeric(12,2)
    assert decimal_de("10000000000") == Decimal(10) ** 10  # mas cabe nas colunas de 14 dígitos


def test_remuneracao_com_salario_que_estoura_a_coluna_e_contada_e_nao_derruba_a_carga(pg_engine, banco, tmp_path):
    registros = [
        {"camara_id": 100, "ano": 2024, "mes": 1, "salario_bruto": 5e10},
        {"camara_id": 100, "ano": 2024, "mes": 2, "salario_bruto": 100, "salario_liquido": 5e10},
        {"camara_id": 100, "ano": 2024, "mes": 3, "salario_bruto": 100},
    ]
    _gravar(tmp_path, fin.REMUNERACAO_ARQUIVO, _oficial(registros=registros))
    with pg_engine.begin() as conn:
        resultado = fin.carregar_remuneracao(conn, tmp_path)
    assert resultado["invalidas"] == 1 and resultado["meses"] == 2
    with pg_engine.connect() as conn:
        # o líquido fora da faixa vira desconhecido (nulo), nunca zero nem erro
        assert conn.execute(text("SELECT salario_liquido FROM fin.remuneracao WHERE mes = 2")).scalar() is None


def test_resolvedor_aceita_nome_unico_mesmo_com_mandatos_so_em_outros_anos(pg_engine, banco):
    # o cadastro de mandatos do Senado anterior a 2023 é incompleto: senador real com mandato cadastrado só depois
    with pg_engine.begin() as conn:
        senador = _pessoa(conn, "Otto Alencar Teste", mandato=("2023-02-01", None))
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert resolvedor.por_nome(["Otto Alencar Teste"], 2020).pessoa_id == senador
        assert resolvedor.por_nome(["Otto Alencar Teste"]).pessoa_id == senador


def test_resolvedor_nao_escolhe_quando_dois_homonimos_tinham_mandato_no_mesmo_ano(pg_engine, banco):
    with pg_engine.begin() as conn:
        _pessoa(conn, "Dario Pai", mandato=("2019-02-01", "2023-01-31"))
        _pessoa(conn, "Dario Pai", mandato=("2023-02-01", None))
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert (
            resolvedor.por_nome(["Dario Pai"], 2023).situacao == "HOMONIMO_NAO_DESAMBIGUADO"
        )  # transição de legislatura
        assert resolvedor.por_nome(["Dario Pai"], 2022).situacao == "IDENTIFICADO"
        assert resolvedor.por_nome(["Dario Pai"], 2024).situacao == "IDENTIFICADO"


def test_fronteiras_do_mandato_dentro_do_ano(pg_engine, banco):
    with pg_engine.begin() as conn:
        a = _pessoa(conn, "Eva Fim", mandato=("2010-01-01", "2020-12-31"))
        b = _pessoa(conn, "Eva Fim", mandato=("2021-01-01", "2022-06-30"))
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert resolvedor.por_nome(["Eva Fim"], 2020).pessoa_id == a  # termina em 31/12: ainda conta
        assert resolvedor.por_nome(["Eva Fim"], 2021).pessoa_id == b  # começa em 01/01 do outro


def test_resolvedor_junta_o_cadastro_do_legado_ao_que_tem_identificador(pg_engine, banco):
    with pg_engine.begin() as conn:
        legado = _pessoa(conn, "Gemeo Legado")
        canonica = _pessoa(conn, "Gemeo Legado", camara_id=600, mandato=("2023-02-01", None))
        uid = conn.execute(text("SELECT uid FROM core.pessoa WHERE id = :p"), {"p": legado}).scalar()
        conn.execute(
            text(
                'INSERT INTO public.politicos (id, "nomeCivil", "nomeEleitoral", "camaraId") '
                "VALUES (:u, 'Gemeo Legado', 'Gemeo Legado', 600)"
            ),
            {"u": uid},
        )
    try:
        with pg_engine.connect() as conn:
            resolvedor = ResolvedorDePessoas(conn)
            # os dois cadastros contam como uma pessoa: sem homônimo, e o dado vai para o que tem identificador
            assert resolvedor.por_nome(["Gemeo Legado"], 2024).pessoa_id == canonica
            assert resolvedor.por_nome(["Gemeo Legado"]).situacao == "IDENTIFICADO"
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM public.politicos WHERE id = :u"), {"u": uid})


def test_cada_carga_grava_a_fonte_certa(pg_engine, banco, tmp_path):
    _carga_com_dado_bom(tmp_path)
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(), "S": _ceap(camara_id=None, senado_id=200, nome="BETO")})
    with pg_engine.begin() as conn:
        for funcao in FUNCAO_DA_CARGA.values():
            funcao(conn, tmp_path)
    esperado = {
        "despesa_cota": {"CAMARA_CSV", "SENADO_API"},
        "emenda": {"PORTAL_TRANSPARENCIA"},
        "remuneracao": {"CAMARA_PORTAL"},
        "declaracao_patrimonio": {"TSE"},
        "doacao_campanha": {"TSE"},
        "certidao": {"TSE"},
    }
    with pg_engine.connect() as conn:
        for tabela, fontes in esperado.items():
            achadas = set(
                conn.execute(
                    text(f"SELECT DISTINCT f.codigo FROM fin.{tabela} t JOIN etl.fonte f ON f.id = t.fonte_id")
                ).scalars()
            )
            assert achadas == fontes, tabela


def test_ceap_sem_nenhum_identificador_e_contada_e_nao_grava(pg_engine, banco, tmp_path):
    _gravar(
        tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(), "LIDERANCA": _ceap(camara_id=None, senado_id=None, nome="ANA SOUZA")}
    )
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["sem_identificador"] == 1 and resultado["parlamentares"] == 1


def test_fornecedor_com_o_mesmo_cnpj_e_grafias_diferentes_vira_um_so(pg_engine, banco, tmp_path):
    forn = {
        "A": {"nome": "POSTO SOL LTDA", "cnpj_cpf": "02.558.157/0001-62", "total": 100.0, "notas": 2},
        "B": {"nome": "POSTO SOL", "cnpj_cpf": "02.558.157/0001-62", "total": 30.0, "notas": 1},
    }
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(fornecedores=forn)})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert [
            tuple(r) for r in conn.execute(text("SELECT nome, valor_total, notas FROM fin.despesa_cota_fornecedor"))
        ] == [("POSTO SOL LTDA", Decimal("130.00"), 3)]


def test_recarga_de_emenda_sem_codigo_e_sem_funcao_nao_duplica_e_mantem_o_uid(pg_engine, banco, tmp_path):
    relator = _emenda(
        None, "RELATOR GERAL", tipo_emenda="Emenda de Relator", localidade_destino="Nacional", funcao=None
    )
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [relator])
    uids = []
    for _ in range(2):
        with pg_engine.begin() as conn:
            fin.carregar_emendas(conn, tmp_path)
        with pg_engine.connect() as conn:
            uids.append(conn.execute(text("SELECT uid FROM fin.emenda")).scalars().all())
    assert len(uids[0]) == 1 and uids[0] == uids[1]


def test_emenda_identificada_vira_homonimo_na_recarga_sem_violar_o_check(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Zeca Dois", ano=2024)])
    with pg_engine.begin() as conn:
        unico = _pessoa(conn, "Zeca Dois")
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert tuple(conn.execute(text("SELECT autor_situacao, pessoa_id FROM fin.emenda")).one()) == (
            "IDENTIFICADO",
            unico,
        )
    with pg_engine.begin() as conn:
        _pessoa(conn, "Zeca Dois")  # aparece um homônimo, sem mandato: ninguém se distingue
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert tuple(conn.execute(text("SELECT autor_situacao, pessoa_id FROM fin.emenda")).one()) == (
            "HOMONIMO_NAO_DESAMBIGUADO",
            None,
        )


def test_reconciliacao_usa_a_mesma_elegibilidade_do_loader(pg_engine, banco, tmp_path):
    from etl.scripts import reconciliar_financas as rec

    sem_tipo = _emenda("9", "Ana Souza", tipo_emenda=None)  # o loader descarta; a reconciliação não pode contar
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza"), sem_tipo])
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {})
    _gravar(tmp_path, fin.REMUNERACAO_ARQUIVO, _oficial(registros=[]))
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [])
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        relatorio = rec.reconciliar(conn, tmp_path)
    assert rec.divergencias(relatorio) == []
    assert relatorio["emendas_empenhado"][0]["arquivo"] == Decimal("1000.00")


def test_toda_uf_do_etl_existe_em_ref_uf(pg_engine):
    from etl.pipelines.loader_helpers import UF_POR_NOME

    with pg_engine.connect() as conn:
        siglas = set(conn.execute(text("SELECT sigla FROM ref.uf")).scalars())
    assert set(UF_POR_NOME.values()) <= siglas


# ── revisão final: texto livre sem CPF, resumo parcial, repetidas, guarda nas tabelas-irmãs da CEAP ─────────────────


class _SempreAPessoa:
    """Resolvedor sem banco: todo registro é da pessoa 1."""

    def resolver(self, item, ano=None):
        return Resolucao(1, "IDENTIFICADO")

    def por_nome(self, nomes, ano=None):
        return Resolucao(1, "IDENTIFICADO")

    def por_identificador(self, camara_id=None, senado_id=None):
        return 1


def test_texto_livre_perde_o_cpf_mas_mantem_valores_em_reais_e_cnpj():
    assert texto_sem_cpf("Credito a Fulano 012.345.678-00 de R$ 5.000,00") == "Credito a Fulano de R$ 5.000,00"
    assert texto_sem_cpf("CPF 09876543200 ok") == "CPF ok"
    assert texto_sem_cpf("Casa avaliada em R$ 1.234.567,89") == "Casa avaliada em R$ 1.234.567,89"
    assert texto_sem_cpf("Apartamento R$ 12345678900") == "Apartamento R$ 12345678900"  # valor, não documento
    assert texto_sem_cpf("Empresa 12.345.678/0001-95") == "Empresa 12.345.678/0001-95"
    assert texto_sem_cpf("٠١٢٣٤٥٦٧٨٠٠ fim") == "fim"  # dígitos árabe-índicos
    assert texto_sem_cpf("   ") is None and texto_sem_cpf(None) is None and texto_sem_cpf("09876543200") is None


def test_detalhes_de_patrimonio_e_certidao_nao_levam_cpf_para_o_banco():
    patrimonio, _ = fin.linhas_do_patrimonio(
        [_oficial(camara_id=1, ano_eleicao=2022, valor_declarado_brl=10, detalhes_bens="Credito de 012.345.678-00")],
        _SempreAPessoa(),
        1,
    )
    certidoes, _ = fin.linhas_das_certidoes(
        [_oficial(camara_id=1, orgao="TSE", tipo_certidao="T", status_ficha="ok", detalhes="Réu 09876543200")],
        _SempreAPessoa(),
        1,
    )
    assert patrimonio[0]["det"] == "Credito de" and certidoes[0]["det"] == "Réu"


def test_ceap_com_quantidade_de_notas_desconhecida_em_uma_das_fontes_fica_sem_resumo():
    entradas = {
        "CAMARA": _ceap(camara_id=100, total_notas=500),
        "SENADO": _ceap(camara_id=None, senado_id=7, total_notas=None),
    }
    _despesas, _fornecedores, resumos, _contagem = fin.linhas_da_ceap(
        entradas, _SempreAPessoa(), {"CAMARA_CSV": 1, "SENADO_API": 2}
    )
    completos, incompletas = resumos_completos(resumos)
    assert completos == [] and incompletas == 1  # a contagem parcial (500) não aparece ao lado do gasto completo
    # as duas conhecidas continuam somando
    entradas["SENADO"]["total_notas"] = 20
    _d, _f, resumos, _c = fin.linhas_da_ceap(entradas, _SempreAPessoa(), {"CAMARA_CSV": 1, "SENADO_API": 2})
    completos, incompletas = resumos_completos(resumos)
    assert incompletas == 0 and somar_linhas(completos, ("p",), ("notas",))[0][0]["notas"] == 520


def test_remuneracao_repetida_no_mesmo_mes_fica_com_o_maior_bruto_e_e_contada():
    corpo = _oficial(
        registros=[
            {"camara_id": 1, "ano": 2024, "mes": 1, "salario_bruto": 100},
            {"camara_id": 1, "ano": 2024, "mes": 1, "salario_bruto": 300},
            {"camara_id": 1, "ano": 2024, "mes": 1, "salario_bruto": 200},
            {"camara_id": 1, "ano": 2024, "mes": 13, "salario_bruto": 5},
        ]
    )
    linhas, contagem = fin.linhas_da_remuneracao(corpo, _SempreAPessoa(), 1)
    assert [x["bruto"] for x in linhas] == [300] and contagem["repetidas"] == 2 and contagem["invalidas"] == 1


def test_patrimonio_e_certidao_repetidos_seguem_um_criterio_fixo_e_sao_contados():
    declaracoes = [
        _oficial(camara_id=1, ano_eleicao=2022, valor_declarado_brl=v) for v in (500, 900, 100)
    ]  # a última do arquivo NÃO é a escolhida
    linhas, contagem = fin.linhas_do_patrimonio(declaracoes, _SempreAPessoa(), 1)
    assert [x["valor"] for x in linhas] == [900] and contagem["repetidas"] == 2
    ocorrencias = [
        _oficial(camara_id=1, orgao="TSE", tipo_certidao="T", status_ficha=s)
        for s in ("deferido", "indeferido", "apto")
    ]
    certidoes, contagem = fin.linhas_das_certidoes(ocorrencias, _SempreAPessoa(), 1)
    assert [c["situacao"] for c in certidoes] == ["indeferido"] and contagem["repetidas"] == 2
    ocorrencias.reverse()  # a ordem do arquivo não muda o resultado
    assert [c["situacao"] for c in fin.linhas_das_certidoes(ocorrencias, _SempreAPessoa(), 1)[0]] == ["indeferido"]


def test_remuneracao_sem_pessoa_e_contada():
    corpo = _oficial(registros=[{"camara_id": 1, "ano": 2024, "mes": 1, "salario_bruto": 10}])

    class _Ninguem(_SempreAPessoa):
        def por_identificador(self, camara_id=None, senado_id=None):
            return None

    linhas, contagem = fin.linhas_da_remuneracao(corpo, _Ninguem(), 1)
    assert linhas == [] and contagem["sem_pessoa"] == 1


def test_reconciliacao_usa_as_mesmas_regras_do_loader_para_remuneracao_ceap_e_doacoes():
    from etl.scripts import reconciliar_financas as rec

    corpo = _oficial(
        registros=[
            {"camara_id": 1, "ano": 2024, "mes": 1, "salario_bruto": 100},
            {"camara_id": 1, "ano": 2024, "mes": 13, "salario_bruto": 999},  # mês inválido: o loader descarta
        ]
    )
    assert dict(rec.totais_remuneracao_do_arquivo(corpo)) == {2024: Decimal(100)}
    assert dict(rec.totais_remuneracao_do_arquivo({**corpo, "is_synthetic": True})) == {}  # sem proveniência
    ceap = {"A": _ceap(por_ano_tipo={"2024": {"": 7.0, "TELEFONIA": 3.0}})}  # tipo vazio: o loader descarta
    assert dict(rec.totais_ceap_do_arquivo(ceap)) == {2024: Decimal(3)}
    prestacoes = [_oficial(ano_eleicao=2022, doadores=[{"nome_doador": "A", "valor_doado": 5}, "lixo"])]
    assert dict(rec.totais_doacoes_do_arquivo(prestacoes)) == {2022: Decimal(5)}


@pytest.mark.parametrize("tabela", ["despesa_cota_fornecedor", "despesa_cota_resumo"])
def test_ceap_que_esvaziaria_fornecedores_ou_resumo_aborta_sem_alterar_o_banco(
    pg_engine, banco, tmp_path, monkeypatch, tabela
):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)

    def arquivo(n_fornecedores, com_resumo, valor=1.0):
        entradas = {}
        for i in range(12):
            entradas[f"P{i}"] = _ceap(
                nome=f"P{i}",
                camara_id=1000 + i,
                total_notas=3 if com_resumo else None,
                por_ano_tipo={"2023": {"T": valor}},
                fornecedores={
                    f"F{j}": {"nome": f"F{i}-{j}", "cnpj_cpf": None, "total": 1.0, "notas": 1}
                    for j in range(n_fornecedores)
                },
            )
        return entradas

    with pg_engine.begin() as conn:
        for i in range(12):
            _pessoa(conn, f"P{i}", camara_id=1000 + i)
    _gravar(tmp_path, fin.CEAP_ARQUIVO, arquivo(2, True))
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    antes = _contar(pg_engine, tabela)
    assert antes == (24 if tabela == "despesa_cota_fornecedor" else 12)
    fotografia = _fotografia(pg_engine, "ceap")

    # as despesas continuam 12 (agora com outro valor, para que reescrevê-las apareça), mas a fonte deixou de trazer
    # fornecedores (ou o total de notas)
    _gravar(
        tmp_path,
        fin.CEAP_ARQUIVO,
        arquivo(0 if tabela == "despesa_cota_fornecedor" else 2, tabela != "despesa_cota_resumo", valor=2.0),
    )
    with pytest.raises(RuntimeError, match=f"fin.{tabela}.*nada foi alterado"):
        with pg_engine.begin() as conn:
            fin.carregar_ceap(conn, tmp_path)
    assert _contar(pg_engine, tabela) == antes
    assert _fotografia(pg_engine, "ceap") == fotografia  # as três tabelas ficaram como estavam


def test_substituir_roda_todas_as_guardas_antes_do_primeiro_delete(pg_engine, banco, tmp_path, monkeypatch):
    """Dentro da MESMA transação (sem o rollback do `begin()`): se a guarda da 2ª tabela aborta, a 1ª não foi apagada."""
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    with pg_engine.begin() as conn:
        for i in range(12):
            _pessoa(conn, f"P{i}", camara_id=1000 + i)
    entradas = {
        f"P{i}": _ceap(
            nome=f"P{i}",
            camara_id=1000 + i,
            por_ano_tipo={"2023": {"T": 1.0}},
            fornecedores={"F": {"nome": f"F{i}", "cnpj_cpf": None, "total": 1.0, "notas": 1}},
        )
        for i in range(12)
    }
    _gravar(tmp_path, fin.CEAP_ARQUIVO, entradas)
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        with conn.begin():
            despesas = int(conn.execute(text("SELECT count(*) FROM fin.despesa_cota")).scalar())
            linhas_despesa = [{"p": 1, "ano": 2023, "tipo": "T", "valor": Decimal(1), "f": 1} for _ in range(despesas)]
            with pytest.raises(RuntimeError, match="fin.despesa_cota_fornecedor"):
                fin._substituir(
                    conn,
                    [
                        ("fin.despesa_cota", "INSERT INTO fin.despesa_cota DEFAULT VALUES", linhas_despesa),
                        ("fin.despesa_cota_fornecedor", "INSERT INTO fin.despesa_cota_fornecedor DEFAULT VALUES", []),
                    ],
                )
            # nada foi apagado: a guarda da 2ª tabela abortou antes do DELETE da 1ª
            assert int(conn.execute(text("SELECT count(*) FROM fin.despesa_cota")).scalar()) == despesas


def test_a_tabela_de_emendas_nao_tem_delete_total_porque_faz_upsert():
    """O DELETE total trocaria o `uid` público de todas as emendas: só as tabelas substituídas por inteiro o têm."""
    assert "fin.emenda" in fin._SQL_CONTAGEM and "fin.emenda" not in fin._SQL_DELETE
    assert set(fin._SQL_DELETE) == set(fin._SQL_CONTAGEM) - {"fin.emenda"}


# ── 5ª revisão: CPF em qualquer grafia, desempate fixo, fornecedor canônico, quantidade desconhecida ──────────────────


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("CPF 123456789-00", "CPF"),
        ("CPF-123.456.789-00", "CPF-"),  # hífen de rótulo colado
        ("nº.12345678900", "no."),
        ("Réu,012.345.678-00", "Réu,"),
        ("SÓCIO-012.345.678-00", "SÓCIO-"),
        ("CPF 123 456 789 00", "CPF"),
        ("CPF 123.456.789.00", "CPF"),
        ("CPF 123,456,789-00", "CPF"),
        ("Réu 9876543200", "Réu"),  # CPF que perdeu o zero à esquerda
        ("CPF: 012.345.678–00.", "CPF: ."),  # travessão
        ("CPF 012.345.678\u201000", "CPF"),  # hífen Unicode U+2010
        ("CPF 012.345.678\u221200", "CPF"),  # sinal de menos U+2212
        ("CPF 012.345.678:00", "CPF"),
        ("012\u00a0345\u00a0678\u00a000 fim", "fim"),  # espaço sem quebra
    ],
)
def test_texto_livre_tira_o_cpf_em_qualquer_grafia(bruto, esperado):
    assert texto_sem_cpf(bruto) == esperado


@pytest.mark.parametrize(
    "texto_livre",
    [
        "R$ 1.234.567,89",
        "valor 12.345.678.901,00",  # número maior com casas decimais
        "R$ 12345678900",
        "Empresa 12.345.678/0001-95",
        "Processo 0001234-56.2020.8.26.0100",
        "Casa de 120 m2, 3 quartos, ano 2015",
    ],
)
def test_texto_livre_preserva_valores_cnpj_e_numeros_que_nao_sao_cpf(texto_livre):
    assert texto_sem_cpf(texto_livre) == texto_livre


@pytest.mark.parametrize(
    "nome", ["JOAO 012.345.678\u201000", "JOAO 012.345.678\u221200", "JOAO 012.345.678–00", "JOAO 012.345.678:00"]
)
def test_nome_sem_cpf_tira_cpf_com_hifen_unicode_travessao_e_dois_pontos(nome):
    assert nome_sem_cpf(nome) == "JOAO" and nome_do_fornecedor(nome) == "JOAO"


def test_nome_nunca_grava_a_repr_de_dict_ou_lista():
    assert nome_sem_cpf({"a": 1}) is None and nome_sem_cpf(["x"]) is None
    assert nome_do_fornecedor({"a": 1}) == "Fornecedor não identificado"


def test_documento_do_doador_aceita_a_mascara_com_digitos_de_outro_alfabeto_como_ascii():
    assert documento_do_doador("***.١٢٣.٤٥٦-**") == "***.123.456-**"


def _remuneracao(*brutos_e_liquidos):
    return _oficial(
        registros=[
            {"camara_id": 1, "ano": 2024, "mes": 1, "salario_bruto": b, "salario_liquido": liq}
            for b, liq in brutos_e_liquidos
        ]
    )


@pytest.mark.parametrize("inverter", [False, True])
def test_remuneracao_com_o_mesmo_bruto_desempata_pelo_liquido_em_qualquer_ordem(inverter):
    pares = [(100, 40), (100, 70), (100, None)]
    if inverter:
        pares.reverse()
    linhas, _ = fin.linhas_da_remuneracao(_remuneracao(*pares), _SempreAPessoa(), 1)
    assert [x["liquido"] for x in linhas] == [70]


@pytest.mark.parametrize("inverter", [False, True])
def test_patrimonio_e_certidao_empatados_desempatam_pelo_conteudo_em_qualquer_ordem(inverter):
    declaracoes = [
        _oficial(camara_id=1, ano_eleicao=2022, valor_declarado_brl=10, quantidade_bens=q, detalhes_bens=d)
        for q, d in ((1, "b"), (3, "a"), (3, "c"))
    ]
    ocorrencias = [
        _oficial(camara_id=1, orgao="TSE", tipo_certidao="T", status_ficha="ok", detalhes=d, numero_processo=n)
        for d, n in (("x", "1"), ("x", "9"), ("w", "5"))
    ]
    if inverter:
        declaracoes.reverse()
        ocorrencias.reverse()
    patrimonio, _ = fin.linhas_do_patrimonio(declaracoes, _SempreAPessoa(), 1)
    certidoes, _ = fin.linhas_das_certidoes(ocorrencias, _SempreAPessoa(), 1)
    assert [(x["qtd"], x["det"]) for x in patrimonio] == [(3, "c")]
    assert [(x["det"], x["proc"]) for x in certidoes] == [("x", "9")]


@pytest.mark.parametrize("inverter", [False, True])
def test_doacoes_com_prestacoes_identicas_em_tamanho_e_soma_desempatam_pelo_conteudo(inverter):
    def prestacao(nome):
        return _oficial(
            camara_id=1, ano_eleicao=2022, doadores=[{"nome_doador": nome, "valor_doado": 10, "tipo_receita": "r"}]
        )

    prestacoes = [prestacao("Ana"), prestacao("Beto")]
    if inverter:
        prestacoes.reverse()
    linhas, _ = fin.linhas_das_doacoes(prestacoes, _SempreAPessoa(), 1)
    assert [x["nome"] for x in linhas] == ["Beto"]


def test_somar_empatado_decide_pelo_conteudo_e_soma_desconhecido_como_desconhecido():
    a = {"p": 1, "grupo": "g", "nome": "AAA", "valor": Decimal(10), "notas": 2, "f": 1}
    b = {**a, "nome": "BBB"}
    assert somar_linhas([a, b], ("p", "grupo"), ("valor", "notas"))[0][0]["nome"] == "BBB"
    assert somar_linhas([b, a], ("p", "grupo"), ("valor", "notas"))[0][0]["nome"] == "BBB"
    camara, senado = {**a, "f": 1}, {**a, "f": 2, "notas": None}
    somado = somar_linhas([camara, senado], ("p", "grupo"), ("valor", "notas"))[0][0]
    assert somado["valor"] == Decimal(20) and somado["notas"] is None  # parcial não vale como total


def test_ler_ceap_e_a_regra_unica_de_elegibilidade_e_tira_do_resumo_a_entrada_sem_gasto():
    assert fin.ler_ceap("x") == (None, "sem_proveniencia")
    assert fin.ler_ceap({"camara_id": 1, "por_ano_tipo": {"2023": {"T": 1}}}) == (None, "sem_proveniencia")
    assert fin.ler_ceap(_ceap(camara_id=None)) == (None, "sem_identificador")
    assert fin.ler_ceap(_ceap(por_ano_tipo={})) == (None, "sem_detalhe_por_ano")
    valores, motivo = fin.ler_ceap(_ceap())
    assert motivo is None and valores[(2023, "TELEFONIA")] == Decimal("100.5")
    # entrada cujos anos estão fora da janela não soma gasto: a quantidade de notas dela não entra no resumo
    fora = _ceap(por_ano_tipo={"1800": {"T": 5}}, total_notas=999)
    _d, _f, resumos, _c = fin.linhas_da_ceap({"A": fora}, _SempreAPessoa(), {"CAMARA_CSV": 1, "SENADO_API": 2})
    assert resumos == []


def test_ceap_fornecedor_com_quantidade_desconhecida_grava_notas_nulas_e_nao_zero(pg_engine, banco, tmp_path):
    forn = {
        "A": {"nome": "POSTO SOL", "cnpj_cpf": "02.558.157/0001-62", "total": 100.0},
        "B": {"nome": "OUTRO", "cnpj_cpf": "27.456.163/0001-30", "total": 5.0, "notas": 2},
        "C": {"nome": "NEGATIVO", "cnpj_cpf": "11.222.333/0001-81", "total": 5.0, "notas": -4},
    }
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(fornecedores=forn)})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        linhas = {r[0]: r[1] for r in conn.execute(text("SELECT nome, notas FROM fin.despesa_cota_fornecedor"))}
    assert linhas == {"POSTO SOL": None, "OUTRO": 2, "NEGATIVO": None}


def test_ceap_mesmo_cnpj_com_nomes_diferentes_em_entradas_repetidas_da_mesma_fonte_nao_dobra(
    pg_engine, banco, tmp_path
):
    def entrada(nome):
        forn = {"V": {"nome": nome, "cnpj_cpf": "02.558.157/0001-62", "total": 100.0, "notas": 4}}
        return _ceap(camara_id=500, por_ano_tipo={"2023": {"T": 100.0}}, total_notas=4, fornecedores=forn)

    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": entrada("POSTO SOL LTDA"), "B": entrada("POSTO SOL")})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        linhas = [
            tuple(r) for r in conn.execute(text("SELECT nome, valor_total, notas FROM fin.despesa_cota_fornecedor"))
        ]
    assert linhas == [("POSTO SOL LTDA", Decimal("100.00"), 4)]  # a mesma fonte repetida não soma duas vezes


def test_ceap_resumo_parcial_nao_e_gravado_e_e_contado(pg_engine, banco, tmp_path):
    base = {"por_ano_tipo": {"2023": {"T": 100.0}}, "fornecedores": {}}
    ceap = {
        "CAMARA": _ceap(camara_id=500, total_notas=500, **base),
        "SENADO": _ceap(camara_id=None, senado_id=501, total_notas=None, **base),
    }
    _gravar(tmp_path, fin.CEAP_ARQUIVO, ceap)
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["resumo_incompleto"] == 1 and _contar(pg_engine, "despesa_cota_resumo") == 0
    assert _contar(pg_engine, "despesa_cota") == 1  # o gasto das duas fontes continua gravado


# ── 6ª revisão: forma do CPF, texto legítimo intacto, consolidação independente da ordem ─────────────────────────────


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("Sócios: 111.222.333-44,555.666.777-88", "Sócios: ,"),  # dois CPFs separados por vírgula sem espaço
        ("2020-111.222.333-44", "2020-"),  # número e hífen antes
        ("1-111.222.333-44", "1-"),
        ("111.222.333-44,5", ",5"),
        ("CPF 111 222 333 44 ok", "CPF ok"),
        ("111​222​333​44 fim", "fim"),  # caractere de largura zero entre os dígitos
        ("111·222·333-44 fim", "fim"),  # ponto médio no lugar do ponto
    ],
)
def test_texto_livre_tira_o_cpf_em_mais_vizinhancas(bruto, esperado):
    assert texto_sem_cpf(bruto) == esperado


@pytest.mark.parametrize(
    "texto_livre",
    [
        "validade 01/01/2024 - 30/06/2024",
        "Emitida em 01/02/2020 10:30",
        "emitida 12/03/2024 10:15:22",
        "lotes 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 e 11",
        "Tel 61 3215-5000",
        "tel 61 99999-8888",
        "valor 12.345.678,90 fim",
        "valor 123.456.789,00 fim",  # centavos depois de um CPF-shaped: é valor em reais
        "valor 12345678900,50",
        "R$ 12345678900",
    ],
)
def test_texto_livre_preserva_datas_horas_telefones_listas_e_valores_em_reais(texto_livre):
    assert texto_sem_cpf(texto_livre) == texto_livre


def test_nome_sem_cpf_nao_deixa_digitos_do_cpf_depois_de_numero_e_hifen():
    assert nome_sem_cpf("2020-111.222.333-44 ME") == "2020- ME"
    assert nome_do_fornecedor("LOJA 2020 2021 2022") == "LOJA 2020 2021 2022"


def test_regex_de_cpf_nao_tem_backtracking_catastrofico():
    """
    Mede só as regex (o texto já normalizado) em textos longos (centenas de milhares de caracteres) que repetem a mesma forma.
    Linear termina em milissegundos; mesmo um backtracking quadrático levaria minutos nesse tamanho (o teste ficaria preso muito além do teto), então o teto
    absoluto de 5 s separa os dois sem depender de razão entre tempos (que o ruído do relógio entorta).
    """
    import time

    from etl.pipelines.loader_helpers import _CPF_EM_TEXTO, _SEQUENCIA_CPF

    for unidade in ("1 ", "1.", "1", "123 - ", "123,", "R$ 1 ", "1~", "12 3 "):
        texto_longo = unidade * 30_000
        inicio = time.perf_counter()
        _CPF_EM_TEXTO.sub(" ", texto_longo)
        _SEQUENCIA_CPF.sub(" ", texto_longo)
        assert time.perf_counter() - inicio < 5, unidade


def test_so_digitos_nao_le_a_repr_de_dict_como_cnpj():
    assert cnpj_do_fornecedor({"x": "12.345.678/0001-90"}) is None
    assert cnpj_do_fornecedor(27456163000130) == "27456163000130"


def test_fornecedor_e_doador_compartilham_a_limpeza_de_nome():
    assert nome_do_fornecedor("MEI 012.345.678-00") == nome_sem_cpf("MEI 012.345.678-00") == "MEI"
    assert nome_do_fornecedor("012.345.678-00") == "Fornecedor não identificado"


@pytest.mark.parametrize("inverter", [False, True])
def test_somar_entre_fontes_escolhe_nome_e_fonte_pelo_conteudo_e_nao_pela_ordem(inverter):
    camara = {"p": 1, "grupo": "g", "nome": "ZETA", "valor": Decimal(30), "notas": 1, "f": 1}
    senado = {"p": 1, "grupo": "g", "nome": "ALFA", "valor": Decimal(30), "notas": 2, "f": 2}
    linhas = [camara, senado]
    if inverter:
        linhas.reverse()
    somado, repetidas = somar_linhas(linhas, ("p", "grupo"), ("valor", "notas"))
    assert repetidas == 0 and len(somado) == 1
    assert somado[0]["valor"] == Decimal(60) and somado[0]["notas"] == 3
    # empatado o valor, vence a linha com mais notas (depois os demais campos): a mesma nas duas ordens
    assert (somado[0]["nome"], somado[0]["f"]) == ("ALFA", 2)


def test_entrada_da_ceap_sem_gasto_valido_nao_leva_fornecedores_nem_resumo():
    fora = _ceap(por_ano_tipo={"1800": {"T": 5}}, total_notas=9)
    despesas, fornecedores, resumos, _ = fin.linhas_da_ceap(
        {"A": fora}, _SempreAPessoa(), {"CAMARA_CSV": 1, "SENADO_API": 2}
    )
    assert despesas == [] and fornecedores == [] and resumos == []


def test_todos_os_ler_seguem_o_contrato_campos_ou_motivo():
    from etl.pipelines.loader_helpers import ler_certidao, ler_patrimonio, ler_registros_da_remuneracao

    assert ler_patrimonio("x") == (None, "sem_proveniencia")
    assert ler_patrimonio({"ano_eleicao": 2022, "valor_declarado_brl": 1}) == (None, "sem_proveniencia")
    assert ler_patrimonio(_oficial(ano_eleicao=1800, valor_declarado_brl=1)) == (None, "invalidas")
    lido, _ = ler_patrimonio(_oficial(ano_eleicao=2022, valor_declarado_brl=10, quantidade_bens=-1, detalhes_bens="x"))
    assert lido == {"ano": 2022, "valor": Decimal(10), "qtd": None, "det": "x"}
    assert ler_certidao(_oficial(orgao="TSE", tipo_certidao="T")) == (None, "invalidas")
    lido, _ = ler_certidao(_oficial(orgao="TSE", tipo_certidao="T", status_ficha="ok", numero_processo="1"))
    assert lido["proc"] == "1" and lido["det"] is None
    assert ler_registros_da_remuneracao([]) == (None, "sem_proveniencia")
    assert ler_registros_da_remuneracao({"registros": []}) == (None, "sem_proveniencia")
    assert ler_registros_da_remuneracao(_oficial(registros="x")) == ([], None)
    assert ler_registros_da_remuneracao(_oficial(registros=[1, 2])) == ([1, 2], None)
    assert ler_doacoes("x") == (None, "sem_proveniencia")
    assert ler_doacoes(_oficial(ano_eleicao=1800, doadores=[])) == (None, "invalidas")
    assert ler_doacoes(_oficial(ano_eleicao=2022, doadores=[])) == ({"ano": 2022, "linhas": []}, None)


def test_doacoes_sem_nome_viram_o_rotulo_padrao_e_nao_se_fundem_no_banco(pg_engine, banco, tmp_path):
    doadores = [
        {"nome_doador": "012.345.678-00", "cpf_cnpj_doador": None, "valor_doado": 10, "tipo_receita": "a"},
        {"nome_doador": None, "cpf_cnpj_doador": "abc", "valor_doado": 20, "tipo_receita": "b"},
    ]
    prestacao = _oficial(camara_id=100, ano_eleicao=2022, doadores=doadores)
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [prestacao])
    with pg_engine.begin() as conn:
        fin.carregar_doacoes(conn, tmp_path)
    with pg_engine.connect() as conn:
        linhas = conn.execute(text("SELECT doador_nome, doador_documento FROM fin.doacao_campanha")).all()
    assert sorted(tuple(r) for r in linhas) == [("Doador não identificado", None)] * 2


# ── 7ª revisão: "R$" não protege CPF canônico, lista de CPFs, separadores, nomes, grupo, rótulo anônimo ───────────────


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("R$ 111.222.333-44", "R$"),  # a moeda não protege a forma canônica
        ("R$111.222.333-44", "R$"),
        ("Sócios: 11122233344,55566677788,99988877766", "Sócios: , ,"),  # CPFs corridos separados por vírgula
        ("111.222.333-44,55566677788", ","),
        ("111 222 333 44,555 666 777 88", ","),
        ("(111) 222-333-44", "("),
        ("111|222|333|44", None),
        ("111;222;333;44", None),
    ],
)
def test_texto_livre_tira_cpf_depois_de_moeda_em_lista_e_com_mais_separadores(bruto, esperado):
    assert texto_sem_cpf(bruto) == esperado


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("MEI 111.222.333,44", "MEI"),  # em nome não há valor em reais: a vírgula antes do fim vale
        ("MEI 111.222.333, 44", "MEI"),
        ("MEI (111) 222-333-44", "MEI ("),
        ("MEI 111;222;333;44", "MEI"),
    ],
)
def test_nome_sem_cpf_tira_cpf_com_virgula_final_e_separadores_extras(nome, esperado):
    assert nome_sem_cpf(nome) == esperado


def test_fornecedor_empatado_em_valor_decide_o_nome_pelo_conteudo_e_nao_pela_ordem():
    def fornecedores(*nomes):
        return {
            str(i): {"nome": n, "cnpj_cpf": "02.558.157/0001-62", "total": 100, "notas": 1} for i, n in enumerate(nomes)
        }

    from etl.pipelines.loader_helpers import fornecedores_do_parlamentar

    ida = fornecedores_do_parlamentar({"fornecedores": fornecedores("ALFA LTDA", "ALFA LIMITADA")})
    volta = fornecedores_do_parlamentar({"fornecedores": fornecedores("ALFA LIMITADA", "ALFA LTDA")})
    assert ida[0]["nome"] == volta[0]["nome"] == "ALFA LTDA"
    assert ida[0]["valor"] == Decimal(200) and ida[0]["notas"] == 2


def test_manter_a_melhor_guarda_a_de_maior_ordem_e_diz_se_a_chave_repetiu():
    from etl.pipelines.loader_helpers import manter_a_melhor

    unicas = {}
    assert manter_a_melhor(unicas, "k", {"a": 1, "b": None}, ("a", "b")) is False
    assert manter_a_melhor(unicas, "k", {"a": 1, "b": 5}, ("a", "b")) is True
    assert manter_a_melhor(unicas, "k", {"a": 0, "b": 9}, ("a", "b")) is True
    assert unicas["k"] == {"a": 1, "b": 5}


def test_grupo_do_fornecedor_do_etl_e_igual_a_coluna_gerada_do_banco(pg_engine, banco, tmp_path):
    from etl.pipelines.loader_helpers import grupo_do_fornecedor

    forn = {
        "A": {"nome": "POSTO SOL", "cnpj_cpf": "02.558.157/0001-62", "total": 10.0, "notas": 1},
        "B": {"nome": "MEI 098.765.432-00", "cnpj_cpf": "098.765.432-00", "total": 5.0, "notas": 1},
        "C": {"nome": "MEI 012.345.678-00", "cnpj_cpf": None, "total": 7.0, "notas": 2},
        "D": {"nome": "nome:POSTO SOL", "cnpj_cpf": None, "total": 1.0, "notas": 1},
    }
    camara = _ceap(camara_id=500, fornecedores=forn)
    senado = _ceap(camara_id=None, senado_id=501, fornecedores={"E": forn["C"]})
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": camara, "B": senado})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        linhas = conn.execute(
            text("SELECT nome, cnpj, grupo, valor_total, notas FROM fin.despesa_cota_fornecedor")
        ).all()
    assert linhas and all(grupo == grupo_do_fornecedor(cnpj, nome) for nome, cnpj, grupo, _v, _n in linhas)
    mei = [tuple(r) for r in linhas if r[0] == "MEI"]
    assert len(mei) == 1 and mei[0][3] == Decimal("19.00") and mei[0][4] == 5  # 5 + 7 + 7, cadastros irmãos somados


def test_rotulo_de_doador_anonimo_do_etl_e_o_mesmo_do_backend():
    from app.services import financas_service

    from etl.utils.rotulos import DOADOR_NAO_IDENTIFICADO

    assert financas_service.DOADOR_ANONIMO == DOADOR_NAO_IDENTIFICADO == "Doador não identificado"


# ── 8ª revisão: DF, casa decimal só em dígitos corridos, separadores genéricos, CPF em nome depois de "R$" ───────────


def test_toda_uf_por_extenso_vira_a_sigla_e_o_distrito_federal_nao_perde_a_palavra_federal():
    from etl.pipelines.loader_helpers import UF_POR_NOME

    assert uf_da_localidade("DISTRITO FEDERAL (UF)") == "DF"
    assert uf_da_localidade("Distrito Federal (UF)") == "DF"
    assert uf_da_localidade("BRASÍLIA - DF") == "DF"
    assert all(uf_da_localidade(f"{nome} (UF)") == sigla for nome, sigla in UF_POR_NOME.items())
    assert uf_da_localidade("ESPÍRITO SANTO (UF)") == "ES" and uf_da_localidade("Nacional") is None


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("111 222 333 44,50", ",50"),  # com separadores entre os grupos não é valor em reais
        ("CPF 111.222.333.44,5", "CPF ,5"),
        ("CPF 111-222-333-44,1º outorgante", "CPF ,1o outorgante"),  # o "º" vira "o" na normalização
        ("11122233344,555", ",555"),  # três casas depois da vírgula não são centavos
        ("ref 2020111.222.333-44", "ref 2020"),  # forma canônica colada a dígito anterior
        ("111~222~333~44", None),  # separadores fora da lista antiga
        ("111∙222∙333∙44", None),  # U+2219
    ],
)
def test_texto_livre_tira_cpf_em_mais_grafias_e_so_poupa_centavos_de_digitos_corridos(bruto, esperado):
    assert texto_sem_cpf(bruto) == esperado


@pytest.mark.parametrize(
    "texto_livre",
    [
        "R$ 123 456 789 00",  # exemplo da decisão 6: depois de "R$" fora da forma canônica
        "12345678900,5",  # 11 corridos e uma casa decimal
        "1234567890,50",  # 10 corridos e centavos
        "123456789012",  # 12 e 13 dígitos corridos não são CPF
        "1234567890123",
        "Casa 1.234.567.890,12",
    ],
)
def test_texto_livre_preserva_formas_da_decisao_6_e_numeros_maiores(texto_livre):
    assert texto_sem_cpf(texto_livre) == texto_livre


def test_nome_depois_de_r_cifrao_perde_o_cpf_porque_nome_nao_tem_valor_em_reais():
    assert nome_sem_cpf("LOJA R$ 11122233344") == "LOJA R$"
    assert nome_sem_cpf("MEI 111~222~333~44") == "MEI"


@pytest.mark.parametrize("ordem", ["direta", "invertida"])
def test_ceap_fornecedor_sem_cnpj_e_com_nome_igual_a_um_cnpj_ficam_em_grupos_distintos(
    pg_engine, banco, tmp_path, ordem
):
    forn = {
        "A": {"nome": "POSTO SOL", "cnpj_cpf": "11.222.333/0001-81", "total": 10.0, "notas": 1},
        "B": {"nome": "nome:POSTO SOL", "cnpj_cpf": None, "total": 5.0, "notas": 1},
        "C": {
            "nome": "11222333000181",
            "cnpj_cpf": None,
            "total": 3.0,
            "notas": 1,
        },  # nome com 14 dígitos (sem CPF dentro)
    }
    if ordem == "invertida":
        forn = dict(reversed(list(forn.items())))
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"A": _ceap(fornecedores=forn)})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    with pg_engine.connect() as conn:
        linhas = conn.execute(text("SELECT nome, cnpj, grupo FROM fin.despesa_cota_fornecedor ORDER BY grupo")).all()
    assert len(linhas) == 3 and len({r[2] for r in linhas}) == 3
    assert {r[2] for r in linhas} == {"11222333000181", "nome:nome:POSTO SOL", "nome:11222333000181"}


# ── 9ª revisão: letras Hangul invisíveis, quebra de linha, documento no legado, UF por extenso, caudas conhecidas ─────


@pytest.mark.parametrize("invisivel", ["\u3164", "\uffa0", "\u115f", "\u1160"])
def test_letras_hangul_invisiveis_nao_escondem_o_separador_do_cpf(invisivel):
    cpf = invisivel.join(["111", "222", "333", "44"])
    assert texto_sem_cpf(f"CPF {cpf} fim") == "CPF fim"
    assert nome_sem_cpf(f"MEI {cpf}") == "MEI"


@pytest.mark.parametrize(
    "bruto, esperado",
    [
        ("111\n222\n333\n44", None),  # quebra de linha como separador
        ("Bens:\n111\t222\t333\t44\nfim", "Bens: fim"),
        ("Casa\nCarro", "Casa Carro"),  # o texto livre é sempre achatado em uma linha, com ou sem CPF
        ("Casa  de   praia\t2 quartos", "Casa de praia 2 quartos"),
    ],
)
def test_texto_livre_trata_quebra_de_linha_como_separador_e_achata_o_texto(bruto, esperado):
    assert texto_sem_cpf(bruto) == esperado


def test_nome_com_quebra_de_linha_perde_o_cpf():
    assert nome_sem_cpf("MEI\n111.222.333-44") == "MEI"


@pytest.mark.parametrize(
    "texto_livre",
    ["Placa ABC 123 456 78 90", "lote 123 456 789 0", "Apto 123, bloco 456, rua 78 90"],
)
def test_desenho_3_3_3_2_nao_pega_numeros_com_outra_forma(texto_livre):
    assert texto_sem_cpf(texto_livre) == texto_livre


def test_caudas_conhecidas_da_decisao_6_ainda_escapam_do_filtro():
    """Limitação aceita (docs/DECISOES_E_DUVIDAS_PENDENTES.md, decisão 6): 4 ou mais caracteres entre os grupos."""
    assert texto_sem_cpf("111 .. 222 .. 333 .. 44") == "111 .. 222 .. 333 .. 44"


def test_toda_uf_tem_nome_por_extenso_com_e_sem_acento():
    from etl.pipelines.loader_helpers import UF_POR_NOME

    assert len(UF_POR_NOME) == 27
    for nome, sigla in (("SÃO PAULO", "SP"), ("PARÁ", "PA"), ("RONDÔNIA", "RO"), ("AMAPÁ", "AP"), ("GOIÁS", "GO")):
        assert uf_da_localidade(f"{nome} (UF)") == sigla


def test_rotulo_de_fornecedor_sem_nome_vem_da_constante_compartilhada():
    from etl.utils.rotulos import FORNECEDOR_NAO_IDENTIFICADO

    assert nome_do_fornecedor("") == FORNECEDOR_NAO_IDENTIFICADO == "Fornecedor não identificado"


# ── 10ª revisão: linha agregada de doadores, marcas combinantes, motivo novo, identificador malformado ────────────────


def _prestacao_com_agregada():
    return _oficial(
        camara_id=100,
        ano_eleicao=2022,
        doadores=[
            {
                "nome_doador": "Ana Doadora",
                "cpf_cnpj_doador": "***.123.456-**",
                "valor_doado": 100,
                "tipo_receita": "PF",
            },
            {
                "nome_doador": "Demais doadores (26)",
                "cpf_cnpj_doador": None,
                "valor_doado": 24804,
                "tipo_receita": "Agregado",
            },
            {"nome_doador": "Demais doadores", "cpf_cnpj_doador": None, "valor_doado": 5, "tipo_receita": "agregado"},
            {
                "nome_doador": "Demais doadores (0)",
                "cpf_cnpj_doador": None,
                "valor_doado": 5,
                "tipo_receita": "Agregado",
            },
        ],
    )


def test_ler_doacoes_marca_a_linha_agregada_e_le_quantos_doadores_ela_vale():
    lida, motivo = ler_doacoes(_prestacao_com_agregada())
    assert motivo is None and lida["ano"] == 2022
    resumo = [(x["nome"], x["agregado"], x["qtd"]) for x in lida["linhas"]]
    assert resumo == [
        ("Ana Doadora", False, 1),
        ("Demais doadores (26)", True, 26),
        ("Demais doadores", True, None),  # tipo Agregado sem N no texto: quantidade desconhecida, nunca um palpite
        ("Demais doadores (0)", True, None),  # N inválido (menor que 1) também é desconhecido
    ]


def test_doacoes_gravam_a_linha_agregada_com_a_quantidade_de_doadores(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.DOACOES_ARQUIVO, [_prestacao_com_agregada()])
    with pg_engine.begin() as conn:
        fin.carregar_doacoes(conn, tmp_path)
    with pg_engine.connect() as conn:
        linhas = conn.execute(
            text("SELECT doador_nome, agregado, quantidade_doadores FROM fin.doacao_campanha ORDER BY valor DESC")
        ).all()
    assert [tuple(r) for r in linhas] == [
        ("Demais doadores (26)", True, 26),
        ("Ana Doadora", False, 1),
        ("Demais doadores", True, None),
        ("Demais doadores (0)", True, None),
    ]


@pytest.mark.parametrize("marca", ["\u034f", "\ufe0f", "\u0301", "\u180b", "\u200d"])
def test_marca_combinante_invisivel_dentro_do_cpf_nao_o_esconde(marca):
    cpf = "11" + marca + "1.222.333-44"
    assert texto_sem_cpf(f"CPF {cpf} fim") == "CPF fim"
    assert nome_sem_cpf(f"MEI {cpf}") == "MEI"
    assert nome_sem_cpf("João da Conceição") == "João da Conceição"  # acento composto pelo NFKC não é perdido


def test_numero_do_processo_da_certidao_tambem_passa_pelo_filtro_de_cpf():
    lido, _ = ler_certidao(
        _oficial(orgao="TSE", tipo_certidao="T", status_ficha="ok", numero_processo="111.222.333-44")
    )
    assert lido["proc"] is None
    lido, _ = ler_certidao(
        _oficial(orgao="TSE", tipo_certidao="T", status_ficha="ok", numero_processo="0001234-56.2020.8.26.0100")
    )
    assert lido["proc"] == "0001234-56.2020.8.26.0100"


def test_motivo_novo_de_um_ler_nao_derruba_a_carga_com_keyerror(monkeypatch):
    monkeypatch.setattr(fin, "ler_remuneracao", lambda registro: (None, "motivo_inedito"))
    linhas, contagem = fin.linhas_da_remuneracao(_oficial(registros=[{"camara_id": 1}]), _SempreAPessoa(), 1)
    assert linhas == [] and contagem["motivo_inedito"] == 1 and contagem["invalidas"] == 0


def test_identificador_malformado_nao_casa_com_outra_pessoa(pg_engine, banco):
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        ana = resolvedor.por_identificador(camara_id=100)
        assert ana is not None
        assert resolvedor.por_identificador(camara_id=True) is None  # True não é 1
        assert resolvedor.por_identificador(camara_id=100.9) is None  # fração não é 100
        assert (
            resolvedor.por_identificador(camara_id="100") == ana
            and resolvedor.por_identificador(camara_id=100.0) == ana
        )


# ── 10ª revisão (2): somas dentro da faixa da coluna, interface comum dos ler_* ──────────────────────────────────────


def test_soma_na_faixa_arredonda_em_centavos_e_barra_o_que_estoura_a_coluna():
    from etl.pipelines.loader_helpers import LIMITE_CEAP, soma_na_faixa

    assert soma_na_faixa(Decimal("10.004"), LIMITE_CEAP) == Decimal("10.00")
    assert soma_na_faixa(Decimal("999999999999.99"), LIMITE_CEAP) == Decimal("999999999999.99")
    assert soma_na_faixa(Decimal("1000000000000.00"), LIMITE_CEAP) is None
    assert soma_na_faixa(Decimal("999999999999.999"), LIMITE_CEAP) is None  # arredonda para o limite: estoura
    assert soma_na_faixa(Decimal("-1000000000000.00"), LIMITE_CEAP) is None


def test_total_de_ano_e_tipo_da_ceap_que_estoura_a_coluna_fica_de_fora():
    from etl.pipelines.loader_helpers import valores_da_ceap

    parcela = 600_000_000_000.0  # cada parcela cabe em numeric(14,2); a soma das duas não
    valores = valores_da_ceap({"por_ano_tipo": {"2023": {"T": parcela, " T": parcela, "U": 1.0}}})
    assert valores == {(2023, "U"): Decimal("1.00")}


def test_soma_entre_fontes_que_estoura_a_coluna_e_contada_e_nao_derruba_a_carga(pg_engine, banco, tmp_path):
    grande = 600_000_000_000.0
    camara = _ceap(camara_id=500, por_ano_tipo={"2023": {"T": grande}}, fornecedores={})
    senado = _ceap(camara_id=None, senado_id=501, por_ano_tipo={"2023": {"T": grande}}, fornecedores={})
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"C": camara, "S": senado, "OUTRA": _ceap()})
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["soma_fora_da_faixa"] == 1  # Câmara + Senado dão 1,2 trilhão: não cabe em numeric(14,2)
    assert _contar(pg_engine, "despesa_cota") == 3  # só as despesas da "OUTRA" (Ana) entraram


def test_emendas_repetidas_cuja_soma_estoura_a_coluna_ficam_de_fora_e_sao_contadas():
    metade = 60_000_000_000_000.0  # 6e13 cada; juntas passam de 1e14
    emendas = [_emenda("E1", "ANA", valor_empenhado=metade, valor_pago=metade) for _ in range(2)]
    linhas, contagem = fin.linhas_das_emendas(emendas, _SempreAPessoa(), 1)
    assert linhas == [] and contagem["soma_fora_da_faixa"] == 1 and contagem["chave_repetida"] == 1


@pytest.mark.parametrize(
    "nome, esperado",
    [
        ("ler_ceap", "sem_proveniencia"),
        ("ler_emenda", "sem_proveniencia"),
        ("ler_remuneracao", "invalidas"),  # o mês não tem proveniência própria: ela vem do arquivo
        ("ler_patrimonio", "sem_proveniencia"),
        ("ler_certidao", "sem_proveniencia"),
        ("ler_doacoes", "sem_proveniencia"),
    ],
)
def test_todo_ler_devolve_campos_ou_motivo_nunca_os_dois(nome, esperado):
    from etl.pipelines import loader_helpers

    campos, motivo = getattr(loader_helpers, nome)("x")
    assert campos is None and motivo == esperado


# ── Contagens que cabem numa coluna `integer` ────────────────────────────────────────────────────────────────────────
def test_quantidade_de_doadores_acima_do_teto_de_integer_ou_gigante_vira_desconhecida():
    from etl.pipelines.loader_helpers import LIMITE_INT4

    def quantidade(nome):
        prestacao = _oficial(
            ano_eleicao=2022, doadores=[{"nome_doador": nome, "valor_doado": 10, "tipo_receita": "Agregado"}]
        )
        return ler_doacoes(prestacao)[0]["linhas"][0]["qtd"]

    assert quantidade(f"Demais doadores ({LIMITE_INT4})") == LIMITE_INT4
    assert quantidade(f"Demais doadores ({LIMITE_INT4 + 1})") is None  # estouraria a coluna e derrubaria a carga
    assert quantidade("Demais doadores (" + "9" * 5000 + ")") is None  # 5000 dígitos: sem ValueError do `int()`


def test_contagens_acima_do_teto_de_integer_ficam_desconhecidas():
    from etl.pipelines.loader_helpers import LIMITE_INT4, contagem_int4, fornecedores_do_parlamentar, ler_patrimonio

    assert contagem_int4(LIMITE_INT4) == LIMITE_INT4 and contagem_int4(LIMITE_INT4 + 1) is None
    assert contagem_int4(-1) is None and contagem_int4(1.5) is None and contagem_int4("x") is None
    assert contagem_int4(0) == 0 and contagem_int4("12") == 12
    declaracao = _oficial(ano_eleicao=2022, valor_declarado_brl=10)
    assert ler_patrimonio({**declaracao, "quantidade_bens": 3_000_000_000})[0]["qtd"] is None
    assert ler_patrimonio({**declaracao, "quantidade_bens": 4})[0]["qtd"] == 4
    vivo = {"nome": "VIVO", "cnpj_cpf": "02.558.157/0001-62", "total": 10.0}
    assert fornecedores_do_parlamentar({"fornecedores": {"a": {**vivo, "notas": 3_000_000_000}}})[0]["notas"] is None
    assert fornecedores_do_parlamentar({"fornecedores": {"a": {**vivo, "notas": 3}}})[0]["notas"] == 3


def test_soma_de_contagens_que_estoura_o_integer_vira_desconhecida():
    from etl.pipelines.loader_helpers import LIMITE_INT4, soma_ou_desconhecido

    assert soma_ou_desconhecido(LIMITE_INT4 - 1, 1) == LIMITE_INT4
    assert soma_ou_desconhecido(LIMITE_INT4, 1) is None
    assert soma_ou_desconhecido(Decimal("1.50"), Decimal("2")) == Decimal("3.50")  # valores monetários não são cortados
    linhas = [
        {"p": 1, "grupo": "g", "valor": Decimal(5), "notas": 2_000_000_000, "f": 1},
        {"p": 1, "grupo": "g", "valor": Decimal(5), "notas": 2_000_000_000, "f": 2},  # outra fonte: as notas se somam
    ]
    unicas, _ = somar_linhas(linhas, ("p", "grupo"), ("valor", "notas"))
    assert unicas[0]["valor"] == Decimal(10) and unicas[0]["notas"] is None


def test_total_de_notas_gigante_na_ceap_nao_derruba_a_carga_e_deixa_a_pessoa_sem_resumo(pg_engine, banco, tmp_path):
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap(total_notas=3_000_000_000)})
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)  # antes: "integer out of range" e rollback de tudo
    assert resultado["despesas"] == 3 and _contar(pg_engine, "despesa_cota") == 3
    assert _contar(pg_engine, "despesa_cota_resumo") == 0  # quantidade desconhecida: sem resumo, nunca um palpite


# ── Texto do erro que vai para o log e para o deploy ─────────────────────────────────────────────────────────────────
def test_erro_do_banco_so_leva_a_mensagem_principal_e_a_restricao_para_o_log(pg_engine, banco):
    from etl.pipelines.carga_economica import descricao_do_erro

    sigilo = "Fulano-De-Tal-12345"
    with pytest.raises(Exception) as erro:
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO fin.doacao_campanha (pessoa_id, ano_eleicao, doador_nome, doador_documento, valor, "
                    "fonte_id) VALUES (:p, 2022, :n, 'sem-mascara', 1, (SELECT min(id) FROM etl.fonte))"
                ),
                {"p": banco["ana"], "n": sigilo},
            )
    assert sigilo in str(erro.value)  # a mensagem crua do Postgres traz a linha inteira: é isso que não pode ir ao log
    texto_do_erro = descricao_do_erro(erro.value)
    assert sigilo not in texto_do_erro and "DETAIL" not in texto_do_erro and "Failing row" not in texto_do_erro
    assert "IntegrityError" in texto_do_erro and "doacao_campanha_doador_documento_check" in texto_do_erro
    assert descricao_do_erro(RuntimeError("tabela encolheria")) == "tabela encolheria"  # mensagens da carga seguem


def _doacao_com_documento_sem_mascara(conn, _pasta, sigilo="Fulano-De-Tal-12345"):
    conn.execute(
        text(
            "INSERT INTO fin.doacao_campanha (pessoa_id, ano_eleicao, doador_nome, doador_documento, valor, fonte_id) "
            "VALUES ((SELECT min(id) FROM core.pessoa), 2022, :n, 'sem-mascara', 1, (SELECT min(id) FROM etl.fonte))"
        ),
        {"n": sigilo},
    )


def test_carregar_nao_deixa_o_detail_do_banco_chegar_ao_log_nem_ao_erro_final(
    pg_engine, banco, tmp_path, monkeypatch, caplog
):
    """O wrapper `carregar` é quem captura a falha de cada carga: é ali que o DETAIL com a linha inteira vazaria."""
    monkeypatch.setattr(fin, "CARGAS", (("doacoes", _doacao_com_documento_sem_mascara),))
    with caplog.at_level("ERROR", logger="FinancasLoader"):
        with pytest.raises(RuntimeError) as erro:
            fin.carregar(pg_engine, tmp_path)
    sigilo = "Fulano-De-Tal-12345"
    assert sigilo not in str(erro.value) and sigilo not in caplog.text
    assert "Failing row" not in str(erro.value) and "Failing row" not in caplog.text
    assert "doacao_campanha_doador_documento_check" in str(erro.value)  # a restrição segue no texto
    assert len(caplog.records) == 1 and not caplog.records[0].exc_info  # a pilha repetiria a linha inteira


def test_erro_de_dado_do_banco_real_sai_so_com_o_tipo_o_sqlstate_e_sem_o_valor(pg_engine):
    from etl.pipelines.loader_helpers import descricao_do_erro

    with pytest.raises(Exception) as erro:
        with pg_engine.begin() as conn:
            conn.execute(text("SELECT CAST(:v AS integer)"), {"v": 3_000_000_000})
    descricao = descricao_do_erro(erro.value)
    assert descricao.startswith("DataError: erro de dado (SQLSTATE 22003)") and "3000000000" not in descricao


def test_emendas_com_resolvedor_degradado_nao_desligam_as_emendas_ja_ligadas_a_uma_pessoa(
    pg_engine, banco, tmp_path, monkeypatch
):
    from etl.pipelines.pessoa_resolver import Resolucao

    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda(str(i), "Ana Souza") for i in range(12)])
    with pg_engine.begin() as conn:
        fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fin.emenda WHERE pessoa_id IS NOT NULL")).scalar() == 12
    # o resolvedor passa a não achar ninguém: as 12 linhas continuam na fonte (a contagem de linhas não encolhe)
    monkeypatch.setattr(
        fin.ResolvedorDePessoas, "por_nome", lambda self, nomes, ano=None: Resolucao(None, "NAO_CADASTRADO")
    )
    with pytest.raises(RuntimeError, match="autor identificado"):
        with pg_engine.begin() as conn:
            fin.carregar_emendas(conn, tmp_path)
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fin.emenda WHERE pessoa_id IS NOT NULL")).scalar() == 12


def test_ceap_com_total_de_ano_e_tipo_fora_da_faixa_deixa_a_pessoa_inteira_de_fora(pg_engine, banco, tmp_path):
    grande = 600_000_000_000.0  # cada parcela cabe; o total do ano e tipo (1,2 trilhão) não cabe em numeric(14,2)
    estoura = _ceap(por_ano_tipo={"2023": {"T": grande, " T": grande, "U": 1.0}}, fornecedores={})
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": estoura, "BETO LIMA": _ceap(camara_id=None, senado_id=200)})
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    # gasto parcial não vale como total: a Ana não fica nem com o tipo "U" que cabia
    assert resultado["total_fora_da_faixa"] == 1
    with pg_engine.connect() as conn:
        pessoas = {r[0] for r in conn.execute(text("SELECT DISTINCT pessoa_id FROM fin.despesa_cota"))}
    assert pessoas == {banco["beto"]}


def test_cap_de_soma_entre_fontes_tambem_tira_a_pessoa_inteira(pg_engine, banco, tmp_path):
    grande = 600_000_000_000.0
    camara = _ceap(camara_id=500, por_ano_tipo={"2023": {"T": grande, "U": 1.0}}, fornecedores={})
    senado = _ceap(camara_id=None, senado_id=501, por_ano_tipo={"2023": {"T": grande}}, fornecedores={})
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"C": camara, "S": senado, "OUTRA": _ceap()})
    with pg_engine.begin() as conn:
        resultado = fin.carregar_ceap(conn, tmp_path)
    assert resultado["soma_fora_da_faixa"] == 1 and resultado["pessoas_sem_gasto_completo"] == 1
    with pg_engine.connect() as conn:
        tipos = [r[0] for r in conn.execute(text("SELECT tipo_despesa FROM fin.despesa_cota"))]
    assert "U" not in tipos  # o tipo que cabia também sai: o gasto da pessoa ficaria parcial


def test_a_tabela_de_nomes_de_estado_do_backend_e_a_do_etl_sao_iguais():
    from app.services import emendas_service

    from etl.pipelines import loader_helpers

    assert emendas_service._ESTADOS_MAP == loader_helpers.UF_POR_NOME
    assert set(emendas_service._UFS) == set(loader_helpers._UFS)


def test_rotulo_de_fornecedor_nao_identificado_e_igual_no_backend_e_no_etl():
    from app.services import financas_service

    from etl.utils.rotulos import FORNECEDOR_NAO_IDENTIFICADO

    assert financas_service.FORNECEDOR_NAO_IDENTIFICADO == FORNECEDOR_NAO_IDENTIFICADO == "Fornecedor não identificado"


# ── 14ª revisão: fonte pela casa de origem, cargas por chave, total fora da faixa ────────────────────────────────────
def _despesas_da_fonte(entrada):
    despesas, _f, _r, _c = fin.linhas_da_ceap({"X": entrada}, _SempreAPessoa(), {"CAMARA_CSV": 1, "SENADO_API": 2})
    return {d["f"] for d in despesas}


@pytest.mark.parametrize(
    "mudancas, fonte",
    [
        ({"cargo": "DEPUTADO_FEDERAL", "camara_id": None, "senado_id": None}, None),  # sem id: nem entra (liderança)
        ({"cargo": "SENADOR", "camara_id": None, "senado_id": 7}, 2),
        ({"cargo": "SENADOR", "camara_id": 7, "senado_id": None}, 2),  # o cargo vale mais que o identificador
        ({"cargo": "DEPUTADO_FEDERAL", "camara_id": None, "senado_id": 7}, 1),
        ({"cargo": None, "camara_id": 100, "senado_id": None}, 1),  # sem cargo, vale o identificador (arquivos antigos)
        ({"cargo": None, "camara_id": None, "senado_id": 7}, 2),
    ],
)
def test_a_fonte_da_ceap_e_a_casa_do_cargo_e_nao_a_presenca_do_camara_id(mudancas, fonte):
    entrada = _ceap(**mudancas)
    if entrada["cargo"] is None:
        entrada.pop("cargo")
    assert _despesas_da_fonte(entrada) == ({fonte} if fonte else set())


def test_carregar_com_chaves_roda_so_as_pedidas_na_ordem_do_loader(pg_engine, banco, tmp_path, monkeypatch):
    rodadas = []
    monkeypatch.setattr(
        fin, "CARGAS", tuple((c, lambda conn, pasta, c=c: rodadas.append(c) or {"ok": 1}) for c, _ in fin.CARGAS)
    )
    resultados = fin.carregar(pg_engine, tmp_path, chaves=("certidoes", "ceap"))
    assert rodadas == ["ceap", "certidoes"] and set(resultados) == {"ceap", "certidoes"}
    rodadas.clear()
    assert set(fin.carregar(pg_engine, tmp_path)) == {c for c, _ in fin.CARGAS}  # sem chaves: todas


def test_chave_desconhecida_falha_antes_de_executar_qualquer_carga(pg_engine, banco, tmp_path, monkeypatch):
    rodadas = []
    monkeypatch.setattr(fin, "CARGAS", tuple((c, lambda conn, pasta, c=c: rodadas.append(c)) for c, _ in fin.CARGAS))
    with pytest.raises(ValueError, match="desconhecidas"):
        fin.carregar(pg_engine, tmp_path, chaves=("ceap", "cep"))
    assert rodadas == []


def test_carga_estatica_nao_apaga_ceap_nem_emendas_ja_no_banco(pg_engine, banco, tmp_path):
    """O `fin` tem CEAP e emendas mais novas que o git: a carga estática não pode tocá-las."""
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza")])
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
        fin.carregar_emendas(conn, tmp_path)
    antes = (_contar(pg_engine, "despesa_cota"), _contar(pg_engine, "emenda"))
    (tmp_path / fin.CEAP_ARQUIVO).unlink()  # os arquivos do git, desatualizados ou ausentes, não importam
    (tmp_path / fin.EMENDAS_ARQUIVO).unlink()
    _gravar(
        tmp_path,
        fin.REMUNERACAO_ARQUIVO,
        _oficial(registros=[{"camara_id": 100, "ano": 2024, "mes": 1, "salario_bruto": 1}]),
    )
    resultados = fin.carregar(pg_engine, tmp_path, chaves=fin.CHAVES_ESTATICAS)
    assert (_contar(pg_engine, "despesa_cota"), _contar(pg_engine, "emenda")) == antes and antes[0] > 0 and antes[1] > 0
    assert resultados["remuneracao"]["meses"] == 1 and "ceap" not in resultados


@pytest.mark.parametrize(
    "nome, esperado",
    [
        (
            "FULANO SINTETICO DA SILVA 100200300400",
            "FULANO SINTETICO DA SILVA",
        ),  # 12 dígitos colados ao nome (dados reais)
        ("Beltrana Exemplo Souza 500600700800", "Beltrana Exemplo Souza"),
        (f"{DOZE_DIGITOS_SEM_CPF}Eletrobrás Energiza", "Eletrobrás Energiza"),
        (
            "RESTAURANTE SANTA CLARA LTDA:18477203000139",
            "RESTAURANTE SANTA CLARA LTDA:18477203000139",
        ),  # CNPJ de 14: empresa
        ("CAFE DO CHEF LTDA.:1838408800015", "CAFE DO CHEF LTDA.:1838408800015"),  # 13 dígitos: CNPJ sem o zero inicial
        ("LOJA 2020 2021 2022", "LOJA 2020 2021 2022"),
        ("PEDIDO 12345678901", "PEDIDO"),  # 11 dígitos continua sendo CPF
        ("NOTA 1234567890123456", "NOTA 1234567890123456"),  # 16 dígitos: não é 12
        ("ONLY 500600700800", "ONLY"),
        ("FULANO 12.345.678.901", "FULANO"),  # 11 dígitos agrupados fora do desenho 3-3-3-2
        ("FULANO 12345-678901", "FULANO"),
        ("FULANO 1234.5678.9012", "FULANO"),  # 12 dígitos em grupos de quatro que não são anos
        ("CONVENIO 2019-2020-2021", "CONVENIO 2019-2020-2021"),  # lista de anos
        ("PEDIDO 2019-10-19", "PEDIDO 2019-10-19"),  # data
        ("TEL 61-3215-1234", "TEL 61-3215-1234"),
        (f"FULANO 000{CPF_A}", "FULANO"),  # CPF válido com enchimento de zeros à esquerda (14 e 13 dígitos)
        (f"FULANO 00{CPF_A}", "FULANO"),
        (
            f"FULANO {CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]}",
            "FULANO",
        ),  # CPF válido em grupos 4-4-3 e 2-3-3-3, separados por espaço
        (f"FULANO {CPF_A[:2]} {CPF_A[2:5]} {CPF_A[5:8]} {CPF_A[8:]}", "FULANO"),
        (f"FULANO {CPF_A[:3]}    {CPF_A[3:]}", "FULANO"),  # separador de vários espaços
        ("LOJA 2020 2021 2022", "LOJA 2020 2021 2022"),
        ("TEL 61 3215 1234", "TEL 61 3215 1234"),
        ("VALOR 1.234,56", "VALOR 1.234,56"),
        ("LOJA 00001974000190", "LOJA 00001974000190"),  # CNPJ com zeros à esquerda que não fecha como CPF
    ],
)
def test_numero_de_12_digitos_de_pessoa_fisica_sai_do_nome_e_cnpj_fica(nome, esperado):
    assert nome_sem_cpf(nome) == esperado


def test_so_um_numero_de_12_digitos_nao_deixa_nome_vazio_no_fornecedor():
    assert nome_do_fornecedor("500600700800") == "Fornecedor não identificado"


def test_anos_publicados_da_ceap_vem_do_fin_por_casa_e_ignora_o_ano_zerado(pg_engine, banco, tmp_path):
    senador = _ceap(nome="BETO LIMA", camara_id=None, senado_id=200, cargo="SENADOR")
    senador["por_ano_tipo"] = {"2024": {"PASSAGEM": 30.0}, "2022": {"PASSAGEM": 0.0}}  # 2022 sem gasto
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap(), "BETO LIMA": senador})
    with pg_engine.begin() as conn:
        fin.carregar_ceap(conn, tmp_path)
    publicados = fin.anos_publicados_da_ceap(pg_engine)
    assert publicados["camara"] == {2023, 2024}
    assert publicados["senado"] == {2024}  # o ano sem gasto não conta como publicado


# ── Quem é dono da fonte: sinal gravado no banco, na transação da carga ─────────────────────────────────────────────
@pytest.fixture()
def sem_execucoes_de_carga(pg_engine):
    def limpar():
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM etl.execucao WHERE parametros->>'carga' IS NOT NULL "
                    "OR parametros->>'fonte' IS NOT NULL OR parametros->>'teste' = 'posse'"
                )
            )

    limpar()
    yield
    limpar()


def test_carga_fresca_registra_a_fonte_na_mesma_transacao_da_carga(pg_engine, banco, tmp_path, sem_execucoes_de_carga):
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})
    assert fin.fontes_do_timer(pg_engine) == set()
    fin.carregar(pg_engine, tmp_path, chaves=("ceap",), ao_confirmar=fin.registrar_carga_fresca)
    assert fin.fontes_do_timer(pg_engine) == {"ceap"}
    with pg_engine.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT estagio, status, linhas_gravadas, parametros FROM etl.execucao WHERE parametros->>'carga' = 'ceap'"
            )
        ).one()
    assert linha.estagio == "CARREGAR" and linha.status == "OK" and linha.linhas_gravadas == 3
    assert linha.parametros == {"fresca": "true", "carga": "ceap", "origem": "financas_atualizacao"}


def test_sem_o_hook_a_carga_nao_registra_nada(pg_engine, banco, tmp_path, sem_execucoes_de_carga):
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})
    fin.carregar(pg_engine, tmp_path, chaves=("ceap",))
    assert fin.fontes_do_timer(pg_engine) == set()


def test_se_o_registro_grava_e_depois_falha_a_carga_da_fonte_volta_junto(
    pg_engine, banco, tmp_path, sem_execucoes_de_carga
):
    """O hook grava a linha E levanta: o `ROLLBACK` leva os dados da carga e o sinal juntos (atomicidade de verdade)."""
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})

    def grava_e_quebra(conn, chave, resultado):
        fin.registrar_carga_fresca(conn, chave, resultado)
        raise RuntimeError("falhou depois de registrar")

    with pytest.raises(RuntimeError, match="falhou depois de registrar"):
        fin.carregar(pg_engine, tmp_path, chaves=("ceap",), ao_confirmar=grava_e_quebra)
    assert _contar(pg_engine, "despesa_cota") == 0 and fin.fontes_do_timer(pg_engine) == set()


def test_so_a_fonte_que_carregou_ganha_o_registro_quando_a_outra_falha(
    pg_engine, banco, tmp_path, monkeypatch, sem_execucoes_de_carga
):
    """Uma transação por fonte: a CEAP entra e fica registrada mesmo que as emendas falhem depois."""
    _gravar(tmp_path, fin.CEAP_ARQUIVO, {"ANA SOUZA": _ceap()})
    _gravar(tmp_path, fin.EMENDAS_ARQUIVO, [_emenda("1", "Ana Souza")])

    def emendas_quebram(conn, pasta):
        raise RuntimeError("emendas fora do ar")

    originais = dict(fin.CARGAS)
    monkeypatch.setattr(
        fin, "CARGAS", tuple((c, emendas_quebram if c == "emendas" else f) for c, f in originais.items())
    )
    with pytest.raises(RuntimeError, match="emendas fora do ar"):
        fin.carregar(pg_engine, tmp_path, chaves=("ceap", "emendas"), ao_confirmar=fin.registrar_carga_fresca)
    assert fin.fontes_do_timer(pg_engine) == {"ceap"} and _contar(pg_engine, "despesa_cota") == 3


@pytest.mark.parametrize(
    "chave, resultado",
    [
        ("ceap", {"despesas": 0}),  # carga que não gravou linha nenhuma
        ("ceap", {"arquivo_ausente": 1}),
        ("emendas", {"emendas": True}),  # bool não é contagem
        ("emendas", {"emendas": -3}),
        ("remuneracao", {"meses": 5}),  # fonte que não é do timer
        ("inexistente", {"despesas": 5}),
        ("ceap", "texto"),
        ("ceap", None),
    ],
)
def test_so_conta_a_carga_que_gravou_linhas_de_uma_fonte_do_timer(pg_engine, chave, resultado, sem_execucoes_de_carga):
    with pg_engine.begin() as conn:
        fin.registrar_carga_fresca(conn, chave, resultado)
        fin.registrar_carga_do_git(conn, chave, resultado)
    with pg_engine.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM etl.execucao WHERE parametros->>'carga' IS NOT NULL")).scalar() == 0
        )


def test_carga_do_git_revoga_a_posse_e_a_ultima_linha_de_cada_fonte_vale(pg_engine, sem_execucoes_de_carga):
    with pg_engine.begin() as conn:
        fin.registrar_carga_fresca(conn, "ceap", {"despesas": 3})
        fin.registrar_carga_fresca(conn, "emendas", {"emendas": 3})
    assert fin.fontes_do_timer(pg_engine) == {"ceap", "emendas"}
    with pg_engine.begin() as conn:
        fin.registrar_carga_do_git(conn, "emendas", {"emendas": 3})  # semeadura do git: a posse das emendas acaba
    assert fin.fontes_do_timer(pg_engine) == {"ceap"}
    with pg_engine.begin() as conn:
        fin.registrar_carga_fresca(conn, "emendas", {"emendas": 3}, origem="run_etl")  # e volta com nova extração
        fin.registrar_carga_fresca(conn, "emendas", {"emendas": 3})  # linhas repetidas não duplicam a fonte
    assert fin.fontes_do_timer(pg_engine) == {"ceap", "emendas"}


def _linha_de_execucao(conn, estagio="CARREGAR", status="OK", parametros=None):
    conn.execute(
        text(
            "INSERT INTO etl.execucao (estagio, finalizado_em, status, parametros) "
            "VALUES (:e, now(), :s, CAST(:p AS jsonb))"
        ),
        {"e": estagio, "s": status, "p": json.dumps({**(parametros or {}), "teste": "posse"})},
    )


@pytest.mark.parametrize(
    "estagio, status, parametros",
    [
        ("CARREGAR", "ERRO", {"carga": "ceap", "fresca": "true"}),  # execução que falhou não dá a posse
        ("CARREGAR", "COM_ALERTA", {"carga": "ceap", "fresca": "true"}),
        ("CARREGAR", "EXECUTANDO", {"carga": "ceap", "fresca": "true"}),
        ("EXTRAIR", "OK", {"carga": "ceap", "fresca": "true"}),  # outro estágio
        ("CARREGAR", "OK", {"fresca": "true"}),  # linha de outro gravador, sem a chave da carga
        ("CARREGAR", "OK", {"carga": "ceap", "fresca": "talvez"}),
    ],
)
def test_so_a_linha_ok_de_carregar_com_carga_e_fresca_true_da_a_posse(
    pg_engine, sem_execucoes_de_carga, estagio, status, parametros
):
    with pg_engine.begin() as conn:
        fin.registrar_carga_do_git(conn, "ceap", {"despesas": 1})  # a posse parte revogada
        _linha_de_execucao(conn, estagio, status, parametros)
    assert fin.fontes_do_timer(pg_engine) == set()


def test_linhas_antigas_com_a_chave_fonte_continuam_valendo_e_a_nova_prevalece(pg_engine, sem_execucoes_de_carga):
    """Versões anteriores do branch gravavam `fonte`: um banco de desenvolvimento com elas não pode perder a posse."""
    with pg_engine.begin() as conn:
        _linha_de_execucao(conn, parametros={"fonte": "ceap", "fresca": "true"})
        _linha_de_execucao(conn, parametros={"fonte": "emendas", "fresca": "true"})
    assert fin.fontes_do_timer(pg_engine) == {"ceap", "emendas"}
    with pg_engine.begin() as conn:
        fin.registrar_carga_do_git(conn, "emendas", {"emendas": 1})  # a linha nova (chave `carga`) revoga a antiga
    assert fin.fontes_do_timer(pg_engine) == {"ceap"}


def test_a_origem_do_hook_fica_registrada(pg_engine, sem_execucoes_de_carga):
    with pg_engine.begin() as conn:
        fin.registrar_carga_fresca(conn, "ceap", {"despesas": 1}, origem="run_etl")
    with pg_engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT parametros->>'origem' FROM etl.execucao WHERE parametros->>'carga' = 'ceap'")
            ).scalar()
            == "run_etl"
        )
