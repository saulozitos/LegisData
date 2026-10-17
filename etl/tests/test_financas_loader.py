"""Carga do schema `fin`: funções puras, resolução de pessoas e as seis cargas contra Postgres real."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import text

from etl.pipelines import financas_loader as fin
from etl.pipelines.loader_helpers import (
    cnpj_do_fornecedor,
    documento_do_doador,
    nome_do_fornecedor,
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
    assert nome_do_fornecedor(None) == "Fornecedor não identificado"


def test_documento_do_doador_mascara_cpf_completo_e_preserva_cnpj_e_mascara_da_fonte():
    assert documento_do_doador("123.456.789-01") == "***.456.789-**"
    assert documento_do_doador("12345678901") == "***.456.789-**"
    assert documento_do_doador("***.060.603-**") == "***.060.603-**"
    assert documento_do_doador("00.887.169/0001-05") == "00.887.169/0001-05"
    assert documento_do_doador("  ") is None


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
    assert all(not linha["diferenca"] for linha in relatorio["emendas_empenhado"] + relatorio["emendas_pago"])
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
