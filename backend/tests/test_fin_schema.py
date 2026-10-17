"""Schema `fin`: as restrições do banco barram o que o ETL nunca deveria gravar (CPF, vínculo de emenda, chaves)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .conftest import fonte_id, inserir_fin


def _emenda(db, **mudancas):
    base = dict(
        autor_texto="ANA",
        tipo_autor="INDIVIDUAL",
        autor_situacao="NAO_CADASTRADO",
        ano=2024,
        codigo_emenda="1",
        tipo_emenda="Emenda Individual",
        valor_empenhado=10,
        valor_pago=5,
        localidade_destino="SÃO PAULO (UF)",
        funcao="Saúde",
        fonte_id=fonte_id(db, "PORTAL_TRANSPARENCIA"),
    )
    base.update(mudancas)
    inserir_fin(db, "emenda", **base)


def _viola(db, funcao, constraint):
    """A restrição NOMEADA é a que barra a linha (outra violação da mesma tabela não vale)."""
    with pytest.raises(IntegrityError, match=constraint):
        funcao()
    db.rollback()


def test_cnpj_do_fornecedor_exige_14_digitos(db, pessoa):
    colunas = dict(pessoa_id=pessoa, nome="X", valor_total=1, notas=1)
    inserir_fin(db, "despesa_cota_fornecedor", cnpj="02558157000162", **colunas)
    _viola(
        db, lambda: inserir_fin(db, "despesa_cota_fornecedor", cnpj="12345678901", **{**colunas, "nome": "Y"}), "cnpj"
    )


@pytest.mark.parametrize(
    "documento,aceito",
    [
        ("***.060.603-**", True),
        ("00.887.169/0001-05", True),
        ("00887169000105", True),
        (None, True),
        ("12345678901", False),
        ("123.456.789-01", False),
        ("123456789**", False),
        ("***.060.603-12", False),
        ("6507955124", False),
    ],
)
def test_documento_do_doador_so_aceita_cnpj_ou_mascara_de_cpf(db, pessoa, documento, aceito):
    def inserir():
        inserir_fin(
            db,
            "doacao_campanha",
            pessoa_id=pessoa,
            ano_eleicao=2022,
            doador_nome="D",
            doador_documento=documento,
            valor=1,
            fonte_id=fonte_id(db, "TSE"),
        )

    if aceito:
        inserir()
    else:
        _viola(db, inserir, "doacao_campanha_doador_documento_check")


def test_emenda_identificada_exige_pessoa_e_pessoa_exige_situacao_identificado(db, pessoa):
    _viola(db, lambda: _emenda(db, autor_situacao="IDENTIFICADO"), "emenda_check")
    _viola(db, lambda: _emenda(db, autor_situacao="NAO_CADASTRADO", pessoa_id=pessoa), "emenda_check")
    _emenda(db, autor_situacao="IDENTIFICADO", pessoa_id=pessoa)


def test_chave_natural_da_emenda_trata_nulos_como_iguais(db):
    _emenda(db, codigo_emenda=None, funcao=None)
    db.commit()  # o rollback do _viola não pode levar a linha-base junto
    _viola(db, lambda: _emenda(db, codigo_emenda=None, funcao=None), "emenda_autor_texto_codigo_emenda_ano")
    _emenda(db, codigo_emenda=None, funcao="Saúde")  # outra função: outra linha
    db.commit()
    assert db.execute(text("SELECT count(*) FROM fin.emenda")).scalar() == 2


def test_chave_do_fornecedor_trata_cnpj_nulo_como_igual(db, pessoa):
    colunas = dict(pessoa_id=pessoa, nome="MEI", cnpj=None, valor_total=1, notas=1)
    inserir_fin(db, "despesa_cota_fornecedor", **colunas)
    _viola(
        db,
        lambda: inserir_fin(db, "despesa_cota_fornecedor", **colunas),
        "despesa_cota_fornecedor_pessoa_id_nome_cnpj_key",
    )


def test_ano_mes_e_quantidades_tem_limites(db, pessoa):
    _viola(
        db,
        lambda: inserir_fin(db, "despesa_cota", pessoa_id=pessoa, ano=1994, tipo_despesa="T", valor_liquido=1),
        "despesa_cota_ano_check",
    )
    _viola(
        db,
        lambda: inserir_fin(db, "remuneracao", pessoa_id=pessoa, ano=2024, mes=13, salario_bruto=1),
        "remuneracao_mes_check",
    )
    _viola(
        db,
        lambda: inserir_fin(
            db, "declaracao_patrimonio", pessoa_id=pessoa, ano_eleicao=2022, valor_declarado=1, quantidade_bens=-1
        ),
        "declaracao_patrimonio_quantidade_bens_check",
    )
    _viola(
        db,
        lambda: inserir_fin(db, "despesa_cota_resumo", pessoa_id=pessoa, total_notas=-1),
        "despesa_cota_resumo_total_notas_check",
    )


def test_busca_de_texto_ignora_acento_e_caixa(db):
    assert db.execute(text("SELECT ref.contem_texto('São Paulo (UF)', 'SAO paulo')")).scalar() is True
    assert db.execute(text("SELECT ref.contem_texto('Bahia', 'minas')")).scalar() is False
