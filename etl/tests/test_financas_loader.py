"""Carga do schema `fin`: funções puras, resolução de pessoas e as seis cargas contra Postgres real."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import text

from etl.pipelines import financas_loader as fin
from etl.pipelines.loader_helpers import (
    cnpj_do_fornecedor,
    decimal_de,
    documento_do_doador,
    nome_do_fornecedor,
    nome_sem_cpf,
    tipo_do_autor,
    uf_da_localidade,
)
from etl.pipelines.pessoa_resolver import ResolvedorDePessoas

# ── funções puras ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_cnpj_do_fornecedor_so_aceita_14_digitos_e_nunca_cpf():
    assert cnpj_do_fornecedor("27.456.163/0001-30") == "27456163000130"
    assert cnpj_do_fornecedor("274.561.630/0013-0") == "27456163000130"  # formatação torta da fonte
    assert cnpj_do_fornecedor("065.079.551-24") is None  # CPF: D3
    assert cnpj_do_fornecedor("000.000.000/0000-1") is None  # enchimento de "CELULAR FUNCIONAL"
    assert cnpj_do_fornecedor("123") is None and cnpj_do_fornecedor(None) is None


def test_nome_do_fornecedor_tira_cpf_embutido_e_nunca_devolve_vazio():
    assert nome_do_fornecedor("BRUNO DE SOUZA 06507955124") == "BRUNO DE SOUZA"
    assert nome_do_fornecedor("EMPRESA 123 LTDA") == "EMPRESA 123 LTDA"  # número curto não é CPF
    assert nome_do_fornecedor("06507955124") == "Fornecedor não identificado"
    # CPF com pontuação ou espaços também sai (decisão D3)
    assert nome_do_fornecedor("JOAO 061.507.955-12") == "JOAO"
    assert nome_do_fornecedor("MEI 061 507 955 12") == "MEI"
    assert nome_do_fornecedor("MEI 061.507.95512 ME") == "MEI ME"
    assert nome_do_fornecedor("EMPRESA 12.345.678/0001-95") == "EMPRESA 12.345.678/0001-95"  # CNPJ não é CPF
    assert nome_do_fornecedor(None) == "Fornecedor não identificado"


@pytest.mark.parametrize(
    "nome",
    [
        "MEI 6507955124",  # CPF que perdeu o zero à esquerda
        "MEI 065-079-551-24",
        "MEI 065/079/551-24",
        "MEI 065_079_551_24",
        "MEI 065,079,551-24",
    ],
)
def test_nome_do_fornecedor_tira_cpf_com_qualquer_separador(nome):
    limpo = nome_do_fornecedor(nome)
    assert limpo == "MEI"


def test_nome_do_fornecedor_preserva_cnpj_e_anos_no_nome():
    assert nome_do_fornecedor("LOJA 2020 2021 2022") == "LOJA 2020 2021 2022"
    assert nome_do_fornecedor("X 12345678901234") == "X 12345678901234"
    assert nome_do_fornecedor("A 12.345.678/0001-95 MEI 065.079.551-24") == "A 12.345.678/0001-95 MEI"


def test_nome_sem_cpf_devolve_none_quando_so_havia_cpf():
    assert nome_sem_cpf("065.079.551-24") is None and nome_sem_cpf("Maria 06507955124") == "Maria"
    assert nome_sem_cpf(None) is None


def test_documento_do_doador_mascara_cpf_completo_e_preserva_cnpj_e_mascara_da_fonte():
    assert documento_do_doador("123.456.789-01") == "***.456.789-**"
    assert documento_do_doador("12345678901") == "***.456.789-**"
    assert documento_do_doador("***.060.603-**") == "***.060.603-**"
    assert documento_do_doador("00.887.169/0001-05") == "00.887.169/0001-05"
    assert documento_do_doador("  ") is None
    # formatos fora do padrão nunca passam crus: CPF que perdeu o zero é mascarado, máscara parcial e lixo viram None
    assert documento_do_doador("6507955124") == "***.079.551-**"
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
        "٠٦٥٠٧٩٥٥١٢٤",
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
            "MEI 06507955124": {"nome": "MEI 06507955124", "cnpj_cpf": "065.079.551-24", "total": 10.0, "notas": 1},
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
    doadores = [{"nome_doador": "MEI JOAO 061.507.955-12", "cpf_cnpj_doador": "123456789**", "valor_doado": 5}]
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
    with pytest.raises(RuntimeError):
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
    with pytest.raises(RuntimeError):
        _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", 1))


def test_a_protecao_so_libera_com_o_valor_exato_1(pg_engine, banco, tmp_path, monkeypatch):
    _rodar(pg_engine, "emendas", tmp_path, _arquivo_com("emendas", 20))
    monkeypatch.setenv(fin.VARIAVEL_ACEITAR_ENCOLHIMENTO, "true")
    with pytest.raises(RuntimeError):
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
