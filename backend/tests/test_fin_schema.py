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
        db,
        lambda: inserir_fin(db, "despesa_cota_fornecedor", cnpj="12345678901", **{**colunas, "nome": "Y"}),
        "despesa_cota_fornecedor_cnpj_check",
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
        ("9876543200", False),
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


def test_chave_do_fornecedor_e_o_cnpj_ou_o_nome_quando_nao_ha_cnpj(db, pessoa):
    colunas = dict(pessoa_id=pessoa, nome="MEI", cnpj=None, valor_total=1, notas=1)
    inserir_fin(db, "despesa_cota_fornecedor", **colunas)
    _viola(
        db,
        lambda: inserir_fin(db, "despesa_cota_fornecedor", **colunas),
        "despesa_cota_fornecedor_pessoa_id_grupo_key",
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


def test_tipo_e_situacao_do_autor_so_aceitam_os_valores_do_enum(db):
    _viola(db, lambda: _emenda(db, tipo_autor="OUTRO"), "emenda_tipo_autor_check")
    _viola(db, lambda: _emenda(db, autor_situacao="TALVEZ"), "emenda_autor_situacao_check")


def test_ano_minimo_de_emenda_doacao_e_patrimonio(db, pessoa):
    _viola(db, lambda: _emenda(db, ano=1994), "emenda_ano_check")
    _viola(
        db,
        lambda: inserir_fin(
            db,
            "doacao_campanha",
            pessoa_id=pessoa,
            ano_eleicao=1994,
            doador_nome="D",
            valor=1,
            fonte_id=fonte_id(db, "TSE"),
        ),
        "doacao_campanha_ano_eleicao_check",
    )
    _viola(
        db,
        lambda: inserir_fin(
            db,
            "declaracao_patrimonio",
            pessoa_id=pessoa,
            ano_eleicao=1994,
            valor_declarado=1,
            fonte_id=fonte_id(db, "TSE"),
        ),
        "declaracao_patrimonio_ano_eleicao_check",
    )


def test_uf_da_emenda_tem_de_existir_em_ref_uf(db):
    _viola(db, lambda: _emenda(db, uf="XX"), "emenda_uf_fkey")
    _emenda(db, uf="SP")


def test_nao_se_apaga_pessoa_com_emenda_identificada(db, pessoa):
    _emenda(db, autor_situacao="IDENTIFICADO", pessoa_id=pessoa)
    db.commit()
    _viola(
        db, lambda: db.execute(text("DELETE FROM core.pessoa WHERE id = :p"), {"p": pessoa}), "emenda_pessoa_id_fkey"
    )


# ── busca por trecho: curingas como texto, índices trigram e a migração de ida e volta ───────────────────────────────


@pytest.mark.parametrize(
    "texto, trecho, esperado",
    [
        ("São Paulo", "sao", True),
        ("SÃO PAULO", "paulo", True),
        ("Maria Silva", "SILVA", True),
        ("a_b", "_", True),
        ("ab", "_", False),  # "_" é texto, não curinga de um caractere
        ("100%", "%", True),
        ("abc", "%", False),  # "%" é texto, não curinga
        ("a\\b", "\\", True),
        ("abc", "\\", False),
        ("abc", "xyz", False),
    ],
)
def test_contem_texto_ignora_acento_e_caixa_e_trata_curingas_como_texto(db, texto, trecho, esperado):
    assert db.execute(text("SELECT ref.contem_texto(:t, :c)"), {"t": texto, "c": trecho}).scalar() is esperado


@pytest.mark.parametrize(
    "coluna, indice", [("autor_texto", "ix_emenda_autor_trgm"), ("localidade_destino", "ix_emenda_localidade_trgm")]
)
def test_busca_por_trecho_usa_o_indice_trigram(db, coluna, indice):
    _emenda(db)
    db.commit()
    db.execute(text("SET LOCAL enable_seqscan = off"))  # a tabela é pequena: sem isto o planejador prefere varrê-la
    plano = "\n".join(
        r[0]
        for r in db.execute(
            text(f"EXPLAIN SELECT id FROM fin.emenda WHERE ref.contem_texto({coluna}, :termo)"), {"termo": "abel"}
        )
    )
    assert indice in plano


def test_migracao_0031_desce_e_sobe_de_novo(pg_engine):
    """O downgrade apaga o schema `fin` e a função de busca na ordem certa, e o upgrade os recria idênticos."""
    import os

    from alembic import command
    from alembic.config import Config
    from app.core.migrations import BACKEND_DIR

    from .conftest import TEST_DATABASE_URL

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    anterior = os.environ.get("ALEMBIC_DATABASE_URL")
    os.environ["ALEMBIC_DATABASE_URL"] = TEST_DATABASE_URL

    def existe(sql):
        with pg_engine.connect() as conn:
            return bool(conn.execute(text(sql)).scalar())

    try:
        command.downgrade(config, "0030")
        assert not existe("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'fin')")
        assert not existe("SELECT to_regprocedure('ref.contem_texto(text, text)') IS NOT NULL")
        command.upgrade(config, "head")
        assert existe("SELECT to_regclass('fin.doacao_campanha') IS NOT NULL")
        assert existe("SELECT to_regprocedure('ref.contem_texto(text, text)') IS NOT NULL")
        assert existe("SELECT to_regclass('fin.ix_emenda_autor_trgm') IS NOT NULL")
    finally:
        if anterior is None:
            os.environ.pop("ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["ALEMBIC_DATABASE_URL"] = anterior
        command.upgrade(config, "head")
