"""Carga do schema `fin`: funções puras, resolução de pessoas e as seis cargas contra Postgres real."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from etl.pipelines import financas_loader as fin
from etl.pipelines.loader_helpers import (
    LIMITE_REMUNERACAO,
    cnpj_do_fornecedor,
    decimal_de,
    documento_do_doador,
    nome_do_fornecedor,
    nome_sem_cpf,
    texto_sem_cpf,
    tipo_do_autor,
    uf_da_localidade,
)
from etl.pipelines.pessoa_resolver import ResolvedorDePessoas

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
    # a carga relatou que não gravou nada (e não gravou por acaso o mesmo conteúdo)
    assert (
        resultado.get("arquivo_ausente")
        or resultado.get("arquivo_ausente_ou_sem_proveniencia")
        or not any(
            resultado.get(chave) for chave in ("despesas", "emendas", "meses", "declaracoes", "linhas", "certidoes")
        )
    )


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


def _total_da_carga(engine, carga):
    return sum(_contar(engine, t) for t in TABELAS_POR_CARGA[carga][:1])


def _rodar(engine, carga, pasta, conteudo):
    _gravar(pasta, ARQUIVO_DA_CARGA[carga], conteudo)
    with engine.begin() as conn:
        FUNCAO_DA_CARGA[carga](conn, pasta)


@pytest.mark.parametrize("carga", list(TABELAS_POR_CARGA))
def test_carga_que_encolheria_a_tabela_para_menos_da_metade_aborta_sem_alterar_o_banco(
    pg_engine, banco, tmp_path, monkeypatch, carga
):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 20))
    assert _total_da_carga(pg_engine, carga) == 20
    antes = _fotografia(pg_engine, carga)

    with pytest.raises(RuntimeError, match="nada foi alterado"):
        _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 3))
    assert _fotografia(pg_engine, carga) == antes

    monkeypatch.setenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, "1")  # redução legítima, liberada de propósito
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 3))
    assert _total_da_carga(pg_engine, carga) == 3


@pytest.mark.parametrize("carga", list(TABELAS_POR_CARGA))
def test_limite_exato_da_protecao_metade_passa_e_menos_que_a_metade_aborta(
    pg_engine, banco, tmp_path, monkeypatch, carga
):
    monkeypatch.delenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, raising=False)
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 20))
    with pytest.raises(RuntimeError, match="nada foi alterado"):
        _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 9))
    _rodar(pg_engine, carga, tmp_path, _arquivo_com(carga, 10))  # exatamente 50%
    assert _total_da_carga(pg_engine, carga) == 10


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
        _pessoa(conn, "Eva Fim", mandato=("2021-01-01", "2022-06-30"))
    with pg_engine.connect() as conn:
        resolvedor = ResolvedorDePessoas(conn)
        assert resolvedor.por_nome(["Eva Fim"], 2020).pessoa_id == a  # termina em 31/12: ainda conta
        assert resolvedor.por_nome(["Eva Fim"], 2021).pessoa_id != a  # começa em 01/01 do outro


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
        return SimpleNamespace(pessoa_id=1)

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
    completos, incompletas = fin._resumos_completos(resumos)
    assert completos == [] and incompletas == 1  # a contagem parcial (500) não aparece ao lado do gasto completo
    # as duas conhecidas continuam somando
    entradas["SENADO"]["total_notas"] = 20
    _d, _f, resumos, _c = fin.linhas_da_ceap(entradas, _SempreAPessoa(), {"CAMARA_CSV": 1, "SENADO_API": 2})
    completos, incompletas = fin._resumos_completos(resumos)
    assert incompletas == 0 and fin._somar(completos, ("p",), ("notas",))[0][0]["notas"] == 520


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

    def arquivo(n_fornecedores, com_resumo):
        entradas = {}
        for i in range(12):
            entradas[f"P{i}"] = _ceap(
                nome=f"P{i}",
                camara_id=1000 + i,
                total_notas=3 if com_resumo else None,
                por_ano_tipo={"2023": {"T": 1.0}},
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

    # as despesas continuam 12, mas a fonte deixou de trazer fornecedores (ou o total de notas)
    _gravar(
        tmp_path,
        fin.CEAP_ARQUIVO,
        arquivo(0 if tabela == "despesa_cota_fornecedor" else 2, tabela != "despesa_cota_resumo"),
    )
    with pytest.raises(RuntimeError, match=f"fin.{tabela}.*nada foi alterado"):
        with pg_engine.begin() as conn:
            fin.carregar_ceap(conn, tmp_path)
    assert _contar(pg_engine, tabela) == antes
