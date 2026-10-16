"""Carga das séries em `eco.observacao` e dos metadados presidenciais: parsing puro e Postgres de teste."""

import csv
import json
from datetime import date

import pytest
from sqlalchemy import text

from etl.pipelines import economia_loader as eco
from etl.pipelines import presidencia_loader as pres


def test_numero_aceita_virgula_e_descarta_lixo():
    assert eco.numero("3,5") == 3.5
    assert eco.numero(" 2 ") == 2.0
    for ruim in (None, "", "  ", "nan", "inf", "-inf", "abc", float("nan")):
        assert eco.numero(ruim) is None


def test_observacoes_anuais_descarta_sinteticas_vazias_e_anos_antes_da_janela():
    linhas = [
        {"ano": "1994", "gini": "0.6"},
        {"ano": "1995", "gini": "0.58"},
        {"ano": "1996", "gini": ""},
        {"ano": "1997", "gini": "0.5", "is_synthetic": "True"},
        {"ano": "abc", "gini": "0.5"},
    ]
    obs = eco.observacoes_anuais(linhas, {"gini": "GINI"}, com_uf=False)
    assert obs == [("GINI", date(1995, 1, 1), None, 0.58, False)]


def test_observacoes_por_uf_exigem_a_sigla():
    linhas = [{"ano": "2020", "uf": "sp", "pobreza_pct": "10"}, {"ano": "2020", "uf": "", "pobreza_pct": "11"}]
    assert eco.observacoes_anuais(linhas, {"pobreza_pct": "POBREZA_UF"}, com_uf=True) == [
        ("POBREZA_UF", date(2020, 1, 1), "SP", 10.0, False)
    ]


def test_parcial_vem_da_coluna_do_arquivo():
    obs = eco.observacoes_anuais([{"ano": "2024", "x": "1", "parcial": "true"}], {"x": "X"}, com_uf=False)
    assert obs[0][4] is True


def test_ipca_mensal_normaliza_para_o_dia_1_e_ignora_antes_da_janela():
    linhas = [
        {"data": "1994-12-01", "valor": "2.0"},
        {"data": "1995-01-15", "valor": "1,7"},
        {"data": "data ruim", "valor": "1"},
        {"data": "1995-02-01", "valor": ""},
    ]
    assert eco.observacoes_ipca_mensal(linhas) == [("IPCA_MENSAL", date(1995, 1, 1), None, 1.7, False)]


def test_series_mensais_trazem_o_codigo_da_serie_na_linha():
    linhas = [
        {"serie": "CAMBIO_MENSAL", "data": "1995-01-01", "valor": "0.85"},
        {"serie": "SELIC_META", "data": "1994-12-01", "valor": "50"},
        {"serie": "", "data": "1995-01-01", "valor": "1"},
        {"serie": "SELIC_META", "data": "1995-02-01", "valor": "nan"},
    ]
    assert eco.observacoes_mensais(linhas) == [("CAMBIO_MENSAL", date(1995, 1, 1), None, 0.85, False)]


def test_zero_e_valor_valido_e_nao_ausencia():
    for zero in (0, "0", "0,0", " 0.00 "):
        assert eco.numero(zero) == 0.0
    linhas = [{"data": "1995-02-01", "valor": "0,00"}]
    assert eco.observacoes_ipca_mensal(linhas) == [("IPCA_MENSAL", date(1995, 2, 1), None, 0.0, False)]
    assert eco.observacoes_anuais([{"ano": "1996", "gini": "0"}], {"gini": "GINI"}, com_uf=False)[0][3] == 0.0


def test_marcos_ignoram_vazios_e_espacos():
    assert pres.marcos({"marcos_economicos": [" Plano Real ", "", None, "  "]}) == ["Plano Real"]
    assert pres.marcos({}) == []


def _escrever_csv(diretorio, nome, cabecalho, linhas):
    with open(diretorio / nome, "w", newline="", encoding="utf-8") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


@pytest.fixture()
def arquivos(tmp_path):
    _escrever_csv(
        tmp_path,
        "resumo_macroeconomico_anual.csv",
        ["ano", "ipca_acumulado_ano_pct", "pib_crescimento_real_pct"],
        [[1995, 22.4, 4.2], [1996, 9.5, ""]],
    )
    _escrever_csv(tmp_path, "indicadores_sociais_anuais.csv", ["ano", "gini"], [[1995, 0.58]])
    _escrever_csv(
        tmp_path,
        "seguranca_publica_historico.csv",
        ["ano", "taxa_homicidios", "homicidios_total"],
        [[2000, 26.0, 45433]],
    )
    _escrever_csv(tmp_path, "indicadores_sociais_uf.csv", ["ano", "uf", "pobreza_pct"], [[2020, "SP", 10.0]])
    _escrever_csv(
        tmp_path, "bcb_series_mensais.csv", ["serie", "data", "valor"], [["CAMBIO_MENSAL", "1995-01-01", 0.85]]
    )
    _escrever_csv(
        tmp_path, "subsidio_parlamentar.csv", ["ano", "valor", "norma"], [[1995, 8000, "Decreto Legislativo 7/1995"]]
    )
    _escrever_csv(tmp_path, "ipca_mensal_historico.csv", ["data", "valor"], [["1995-01-01", 1.7], ["1995-02-01", 1.0]])
    return tmp_path


def test_reunir_falha_se_faltar_arquivo(arquivos):
    (arquivos / "ipca_mensal_historico.csv").unlink()
    with pytest.raises(FileNotFoundError):
        eco.reunir(arquivos)


def _contagem(engine):
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text("SELECT s.codigo, count(*) FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id GROUP BY 1")
            ).all()
        )


def test_carga_grava_e_e_idempotente(pg_engine, arquivos):
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.observacao"))
    primeira = eco.carregar(pg_engine, arquivos)
    assert primeira["IPCA_MENSAL"] == 2 and primeira["PIB_CRESC_REAL"] == 1 and primeira["CAMBIO_MENSAL"] == 1
    assert primeira["SUBSIDIO_PARLAMENTAR"] == 1
    antes = _contagem(pg_engine)
    assert eco.carregar(pg_engine, arquivos) == primeira
    assert _contagem(pg_engine) == antes
    with pg_engine.connect() as conn:
        uf = conn.execute(text("SELECT uf, uf_chave FROM eco.observacao WHERE uf IS NOT NULL")).one()
        nacional = conn.execute(text("SELECT DISTINCT uf_chave FROM eco.observacao WHERE uf IS NULL")).scalars().all()
    assert tuple(uf) == ("SP", "SP") and nacional == ["BR"]


def test_carga_regrava_a_serie_inteira_mas_preserva_as_que_o_arquivo_nao_traz(pg_engine, arquivos):
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.observacao"))
    eco.carregar(pg_engine, arquivos)
    _escrever_csv(
        arquivos,
        "resumo_macroeconomico_anual.csv",
        ["ano", "ipca_acumulado_ano_pct", "pib_crescimento_real_pct"],
        [[1995, 20.0, ""]],
    )
    eco.carregar(pg_engine, arquivos)
    contagem = _contagem(pg_engine)
    assert contagem["IPCA_ACUM_ANO"] == 1  # a linha de 1996 saiu: a série é regravada por inteiro
    assert contagem["PIB_CRESC_REAL"] == 1  # coluna vazia no arquivo novo: a série não foi tocada


def test_carga_com_arquivos_sem_dados_nao_apaga_a_base(pg_engine, arquivos):
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.observacao"))
    eco.carregar(pg_engine, arquivos)
    for nome, cab in (
        ("resumo_macroeconomico_anual.csv", ["ano", "ipca_acumulado_ano_pct"]),
        ("indicadores_sociais_anuais.csv", ["ano", "gini"]),
        ("seguranca_publica_historico.csv", ["ano", "taxa_homicidios"]),
        ("indicadores_sociais_uf.csv", ["ano", "uf", "pobreza_pct"]),
        ("ipca_mensal_historico.csv", ["data", "valor"]),
        ("bcb_series_mensais.csv", ["serie", "data", "valor"]),
        ("subsidio_parlamentar.csv", ["ano", "valor", "norma"]),
    ):
        _escrever_csv(arquivos, nome, cab, [])
    antes = _contagem(pg_engine)
    assert eco.carregar(pg_engine, arquivos) == {}
    assert _contagem(pg_engine) == antes


def _semear_presidente(pg_engine, slug="x-2023"):
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE core.pessoa, core.mandato, core.mandato_presidencial, core.marco_governo RESTART IDENTITY CASCADE"
            )
        )
        pessoa = conn.execute(text("INSERT INTO core.pessoa (nome_exibicao) VALUES ('Fulano') RETURNING id")).scalar()
        mandato = conn.execute(
            text(
                "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio) VALUES (:p, "
                "(SELECT id FROM ref.cargo WHERE codigo = 'PRESIDENTE'), "
                "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), DATE '2023-01-01') RETURNING id"
            ),
            {"p": pessoa},
        ).scalar()
        conn.execute(
            text("INSERT INTO core.mandato_presidencial (mandato_id, slug) VALUES (:m, :s)"), {"m": mandato, "s": slug}
        )


@pytest.fixture()
def presidente(pg_engine):
    """Um mandato presidencial `x-2023`; o banco do ETL é compartilhado, então limpa também ao final."""
    _semear_presidente(pg_engine)
    yield
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE core.pessoa, core.mandato, core.mandato_presidencial, core.marco_governo RESTART IDENTITY CASCADE"
            )
        )


def _catalogo(tmp_path, itens):
    (tmp_path / "presidentes_historico.json").write_text(json.dumps(itens), encoding="utf-8")


def _estado(pg_engine):
    with pg_engine.connect() as conn:
        linha = conn.execute(text("SELECT vice_texto, motivo_inicio, status FROM core.mandato_presidencial")).one()
        marcos = conn.execute(text("SELECT texto FROM core.marco_governo ORDER BY ordem")).scalars().all()
    return tuple(linha), marcos


def test_presidencia_atualiza_metadados_e_e_idempotente(pg_engine, tmp_path, presidente):
    _catalogo(
        tmp_path,
        [
            {
                "id_referencia": "x-2023",
                "vice_presidente": " Vice ",
                "motivo_inicio": "Eleito",
                "status_mandato": "TITULAR_ATIVO",
                "marcos_economicos": ["A", "B"],
            }
        ],
    )
    assert pres.carregar(pg_engine, tmp_path) == {"atualizados": 1}
    assert pres.carregar(pg_engine, tmp_path) == {"atualizados": 1}
    assert _estado(pg_engine) == (("Vice", "Eleito", "TITULAR_ATIVO"), ["A", "B"])


def test_presidencia_campo_ausente_no_catalogo_nao_apaga_o_que_ja_esta_no_banco(pg_engine, tmp_path, presidente):
    _catalogo(
        tmp_path,
        [
            {
                "id_referencia": "x-2023",
                "vice_presidente": "Vice",
                "status_mandato": "TITULAR_ATIVO",
                "marcos_economicos": ["A"],
            }
        ],
    )
    pres.carregar(pg_engine, tmp_path)
    _catalogo(tmp_path, [{"id_referencia": "x-2023", "motivo_inicio": "Novo motivo"}])
    pres.carregar(pg_engine, tmp_path)
    # vice, situação e marcos continuam; só o motivo mudou
    assert _estado(pg_engine) == (("Vice", "Novo motivo", "TITULAR_ATIVO"), ["A"])


def test_presidencia_status_invalido_nao_e_gravado(pg_engine, tmp_path, presidente):
    _catalogo(tmp_path, [{"id_referencia": "x-2023", "status_mandato": "INVENTADO"}])
    pres.carregar(pg_engine, tmp_path)
    assert _estado(pg_engine)[0][2] is None


def test_presidencia_mandato_do_catalogo_sem_identificador_falha_e_nao_grava_nada(pg_engine, tmp_path, presidente):
    _catalogo(
        tmp_path,
        [
            {"id_referencia": "x-2023", "vice_presidente": "Vice"},
            {"id_referencia": "y-1999", "vice_presidente": "Outro"},
        ],
    )
    with pytest.raises(RuntimeError, match="y-1999"):
        pres.carregar(pg_engine, tmp_path)
    assert _estado(pg_engine) == ((None, None, None), [])  # a transação inteira voltou


def test_presidencia_sem_catalogo_e_erro(pg_engine, tmp_path):
    with pytest.raises(FileNotFoundError):
        pres.carregar(pg_engine, tmp_path)


def test_serie_fora_do_catalogo_e_erro_e_nao_altera_a_base(pg_engine, arquivos):
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.observacao"))
    eco.carregar(pg_engine, arquivos)
    antes = _contagem(pg_engine)
    _escrever_csv(
        arquivos, "bcb_series_mensais.csv", ["serie", "data", "valor"], [["SERIE_INEXISTENTE", "1995-01-01", 1]]
    )
    with pytest.raises(ValueError, match="SERIE_INEXISTENTE"):
        eco.carregar(pg_engine, arquivos)
    assert _contagem(pg_engine) == antes


def test_parcial_e_zero_chegam_ao_banco(pg_engine, arquivos):
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE eco.observacao"))
    _escrever_csv(
        arquivos,
        "seguranca_publica_historico.csv",
        ["ano", "taxa_homicidios", "homicidios_total", "parcial"],
        [[2024, 0, 10, "true"]],
    )
    eco.carregar(pg_engine, arquivos)
    with pg_engine.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT o.valor, o.parcial FROM eco.observacao o JOIN eco.serie s ON s.id = o.serie_id "
                "WHERE s.codigo = 'HOMICIDIOS_TAXA'"
            )
        ).one()
    assert (float(linha[0]), linha[1]) == (0.0, True)
