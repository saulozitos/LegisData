"""Carga de repasses federais e resultados presidenciais por UF em `eco`."""

import csv
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from etl.pipelines import territorial_loader as terr
from etl.pipelines.loader_helpers import ler_repasse, ler_resultado_eleitoral
from etl.utils.provenance import mark_official


def repasse(mandato="lula-2023", uf="AC", area="Saúde", valor=100.0, **extra):
    base = {
        "mandato_id_ref": mandato,
        "ano": 2026,
        "uf": uf,
        "area_tematica": area,
        "valor_pago_brl": valor,
        "populacao_estimada": 1000,
        "valor_per_capita_brl": valor / 1000,
        "periodo_inicio": "2023-01",
        "periodo_fim": "2026-09",
        "meses_cobertos": 45,
        "parcial": False,
    }
    base.update(extra)
    return mark_official(base, "Portal da Transparência (CGU)")


def eleicao(ano=2022, turno=2, uf="AC", **extra):
    base = {
        "ano_eleicao": str(ano),
        "mandato_id_ref": "lula-2023",
        "uf": uf,
        "candidato_vencedor_nome": "Fulano",
        "partido_vencedor_sigla": "PT",
        "votos_vencedor_pct": "60.5",
        "candidato_segundo_nome": "Beltrano",
        "partido_segundo_sigla": "PL",
        "votos_segundo_pct": "39.5",
        "total_votos_validos": "1000",
        "turno": str(turno),
        "verificado": "True",
        "is_synthetic": "False",
        "fonte": "TSE — Dados Abertos",
    }
    base.update(extra)
    return base


# ── funções puras ─────────────────────────────────────────────────────────────────────────────────────────────────


def test_repasse_valido_vira_campos_tipados_com_o_periodo_no_primeiro_dia_do_mes():
    lido, motivo = ler_repasse(repasse())
    assert motivo is None
    assert (lido["mandato"], lido["uf"], lido["area"], lido["ano"]) == ("lula-2023", "AC", "Saúde", 2026)
    assert lido["valor"] == Decimal("100.0") and lido["per_capita"] == Decimal("0.1")
    assert (lido["inicio"], lido["fim"], lido["meses"], lido["parcial"]) == (
        date(2023, 1, 1),
        date(2026, 9, 1),
        45,
        False,
    )


def test_repasse_negativo_e_estorno_e_vale():
    assert ler_repasse(repasse(valor=-5.5))[0]["valor"] == Decimal("-5.5")


@pytest.mark.parametrize(
    "mudanca",
    [
        {"uf": "ACRE"},
        {"uf": None},
        {"area_tematica": "  "},
        {"mandato_id_ref": None},
        {"ano": 1990},
        {"ano": "x"},
        {"valor_pago_brl": None},
        {"valor_pago_brl": float("nan")},
        {"valor_pago_brl": 10**17},
    ],
)
def test_repasse_com_campo_essencial_invalido_e_contado_como_invalido(mudanca):
    assert ler_repasse(repasse(**mudanca)) == (None, "invalidas")


def test_repasse_sem_proveniencia_ou_sintetico_nao_entra():
    assert ler_repasse({"mandato_id_ref": "lula-2023", "uf": "AC"}) == (None, "sem_proveniencia")
    assert ler_repasse({**repasse(), "is_synthetic": True}) == (None, "sem_proveniencia")
    assert ler_repasse("lixo") == (None, "sem_proveniencia")


def test_repasse_o_que_a_fonte_nao_informa_fica_nulo_nunca_zero():
    lido, _ = ler_repasse(
        repasse(populacao_estimada=None, valor_per_capita_brl="", periodo_inicio=None, meses_cobertos=0, parcial="sim")
    )
    assert lido["populacao"] is None and lido["per_capita"] is None and lido["inicio"] is None
    assert lido["meses"] is None and lido["parcial"] is None


def test_repasse_com_periodo_invertido_ou_ilegivel_descarta_o_periodo_sem_corrigir():
    invertido, _ = ler_repasse(repasse(periodo_inicio="2026-09", periodo_fim="2023-01"))
    assert invertido["inicio"] is None and invertido["fim"] is None
    ilegivel, _ = ler_repasse(repasse(periodo_inicio="2023-13", periodo_fim="jan/2026"))
    assert ilegivel["inicio"] is None and ilegivel["fim"] is None


def test_resultado_eleitoral_verificado_e_lido():
    lido, motivo = ler_resultado_eleitoral(eleicao())
    assert motivo is None and (lido["ano"], lido["turno"], lido["uf"]) == (2022, 2, "AC")
    assert lido["vencedor_pct"] == Decimal("60.5") and lido["total_votos"] == 1000


@pytest.mark.parametrize(
    "mudanca, motivo",
    [
        ({"verificado": "False"}, "nao_verificada"),
        ({"verificado": ""}, "nao_verificada"),
        ({"is_synthetic": "True"}, "nao_verificada"),
        ({"fonte": ""}, "nao_verificada"),
        ({"turno": "3"}, "invalidas"),
        ({"ano_eleicao": "1990"}, "invalidas"),
        ({"uf": ""}, "invalidas"),
        ({"votos_vencedor_pct": "101"}, "invalidas"),
        ({"votos_segundo_pct": ""}, "invalidas"),
        ({"candidato_vencedor_nome": " "}, "invalidas"),
    ],
)
def test_resultado_eleitoral_nao_verificado_ou_invalido_nao_entra(mudanca, motivo):
    assert ler_resultado_eleitoral(eleicao(**mudanca)) == (None, motivo)


def test_resultado_eleitoral_sem_total_de_votos_fica_nulo():
    assert ler_resultado_eleitoral(eleicao(total_votos_validos=""))[0]["total_votos"] is None
    assert ler_resultado_eleitoral(eleicao(total_votos_validos="-3"))[0]["total_votos"] is None


# ── carga no Postgres ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def limpo(pg_engine):
    """Dois mandatos presidenciais (`lula-2023`, `bolsonaro-2019`) e as tabelas de destino vazias; limpa ao final."""

    def apagar():
        with pg_engine.begin() as conn:
            conn.execute(text("DELETE FROM eco.repasse_federal"))
            conn.execute(text("DELETE FROM eco.resultado_eleitoral_uf"))
            conn.execute(
                text(
                    "TRUNCATE core.pessoa, core.mandato, core.mandato_presidencial, core.marco_governo "
                    "RESTART IDENTITY CASCADE"
                )
            )

    apagar()
    with pg_engine.begin() as conn:
        for slug, inicio in (("bolsonaro-2019", "2019-01-01"), ("lula-2023", "2023-01-01")):
            pessoa = conn.execute(
                text("INSERT INTO core.pessoa (nome_exibicao) VALUES (:n) RETURNING id"), {"n": slug}
            ).scalar()
            mandato = conn.execute(
                text(
                    "INSERT INTO core.mandato (pessoa_id, cargo_id, circunscricao_id, inicio) VALUES (:p, "
                    "(SELECT id FROM ref.cargo WHERE codigo = 'PRESIDENTE'), "
                    "(SELECT id FROM ref.circunscricao WHERE tipo = 'BR'), :i) RETURNING id"
                ),
                {"p": pessoa, "i": inicio},
            ).scalar()
            conn.execute(
                text("INSERT INTO core.mandato_presidencial (mandato_id, slug) VALUES (:m, :s)"),
                {"m": mandato, "s": slug},
            )
    yield
    apagar()


def _gravar(pasta, repasses=None, eleicoes=None):
    if repasses is not None:
        (pasta / terr.REPASSES_ARQUIVO).write_text(json.dumps(repasses, ensure_ascii=False), encoding="utf-8")
    if eleicoes is not None:
        colunas = list(eleicao().keys())
        with open(pasta / terr.ELEICOES_ARQUIVO, "w", newline="", encoding="utf-8") as fh:
            escritor = csv.DictWriter(fh, fieldnames=colunas)
            escritor.writeheader()
            escritor.writerows(eleicoes)


def _repasses_no_banco(pg_engine):
    with pg_engine.connect() as conn:
        return {
            (s, uf, area): (valor, inicio, fim)
            for s, uf, area, valor, inicio, fim in conn.execute(
                text(
                    "SELECT p.slug, r.uf, r.area_tematica, r.valor_pago, r.periodo_inicio, r.periodo_fim "
                    "FROM eco.repasse_federal r JOIN core.mandato_presidencial p USING (mandato_id)"
                )
            )
        }


def test_carga_grava_repasses_e_eleicoes_e_e_idempotente(limpo, pg_engine, tmp_path):
    _gravar(tmp_path, [repasse(), repasse(area="Educação", valor=50.0)], [eleicao(), eleicao(uf="AL")])
    primeira = terr.carregar(pg_engine, tmp_path)
    assert primeira == {"repasses": 2, "eleicoes": 2}
    assert terr.carregar(pg_engine, tmp_path) == primeira
    assert _repasses_no_banco(pg_engine) == {
        ("lula-2023", "AC", "Saúde"): (Decimal("100.00"), date(2023, 1, 1), date(2026, 9, 1)),
        ("lula-2023", "AC", "Educação"): (Decimal("50.00"), date(2023, 1, 1), date(2026, 9, 1)),
    }
    with pg_engine.connect() as conn:
        linha = conn.execute(
            text(
                "SELECT e.vencedor_nome, e.vencedor_votos_pct, e.total_votos_validos, p.slug, f.codigo "
                "FROM eco.resultado_eleitoral_uf e LEFT JOIN core.mandato_presidencial p USING (mandato_id) "
                "JOIN etl.fonte f ON f.id = e.fonte_id WHERE e.uf = 'AL'"
            )
        ).one()
    assert tuple(linha) == ("Fulano", Decimal("60.50"), 1000, "lula-2023", "TSE")


def test_retrato_do_mandato_substitui_as_linhas_antigas_e_preserva_os_outros_mandatos(limpo, pg_engine, tmp_path):
    _gravar(tmp_path, [repasse(), repasse(area="Educação"), repasse(mandato="bolsonaro-2019", valor=7.0)])
    terr.carregar(pg_engine, tmp_path)
    _gravar(tmp_path, [repasse(valor=999.0)])  # o novo retrato de lula-2023 traz só Saúde
    terr.carregar(pg_engine, tmp_path)
    banco = _repasses_no_banco(pg_engine)
    assert banco[("lula-2023", "AC", "Saúde")][0] == Decimal("999.00")
    assert ("lula-2023", "AC", "Educação") not in banco  # saiu do retrato
    assert ("bolsonaro-2019", "AC", "Saúde") in banco  # outro mandato fica


def test_mandato_desconhecido_e_linha_invalida_ficam_de_fora_e_sao_contados(limpo, pg_engine, tmp_path):
    _gravar(tmp_path, [repasse(), repasse(mandato="inventado-2099"), repasse(uf="XX9"), {"sem": "proveniencia"}])
    resultado = terr.carregar(pg_engine, tmp_path)
    assert resultado["repasses"] == 1
    assert (resultado["repasses_sem_mandato"], resultado["repasses_invalidas"]) == (1, 1)
    assert resultado["repasses_sem_proveniencia"] == 1


def test_arquivo_ausente_ou_sem_linha_valida_nao_apaga_a_base(limpo, pg_engine, tmp_path):
    _gravar(tmp_path, [repasse()], [eleicao()])
    terr.carregar(pg_engine, tmp_path)
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    assert terr.carregar(pg_engine, vazio)["repasses"] == 0  # sem arquivos
    _gravar(vazio, [{"lixo": 1}], [eleicao(verificado="False")])
    assert terr.carregar(pg_engine, vazio)["eleicoes"] == 0
    assert len(_repasses_no_banco(pg_engine)) == 1
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM eco.resultado_eleitoral_uf")).scalar() == 1


def test_eleicao_do_ano_e_regravada_por_inteiro_e_a_digitacao_manual_nao_entra(limpo, pg_engine, tmp_path):
    _gravar(tmp_path, eleicoes=[eleicao(), eleicao(uf="AL"), eleicao(ano=2018, uf="AC")])
    terr.carregar(pg_engine, tmp_path)
    _gravar(tmp_path, eleicoes=[eleicao(uf="AC", votos_vencedor_pct="61"), eleicao(uf="BA", verificado="False")])
    resultado = terr.carregar(pg_engine, tmp_path)
    assert resultado["eleicoes"] == 1 and resultado["eleicoes_nao_verificada"] == 1
    with pg_engine.connect() as conn:
        linhas = {
            (ano, uf): pct
            for ano, uf, pct in conn.execute(
                text("SELECT ano_eleicao, uf, vencedor_votos_pct FROM eco.resultado_eleitoral_uf")
            )
        }
    assert linhas == {(2022, "AC"): Decimal("61.00"), (2018, "AC"): Decimal("60.50")}  # 2022 refeita; 2018 intacta


def test_o_csv_digitado_a_mao_nunca_e_lido_so_a_apuracao_do_tse(limpo, pg_engine, tmp_path):
    _gravar(tmp_path, eleicoes=[eleicao(candidato_vencedor_nome="Oficial")])
    (tmp_path / "resultados_eleicoes_presidenciais_uf.csv").write_text(
        "ano_eleicao,mandato_id_ref,uf,estado_nome,regiao,candidato_vencedor_nome,partido_vencedor_sigla,"
        "votos_vencedor_pct,candidato_segundo_nome,partido_segundo_sigla,votos_segundo_pct,turno,verificado\n"
        "2022,lula-2023,MG,Minas Gerais,Sudeste,Digitado,PT,99,X,PL,1,2,True\n",
        encoding="utf-8",
    )
    terr.carregar(pg_engine, tmp_path)
    with pg_engine.connect() as conn:
        nomes = conn.execute(text("SELECT vencedor_nome FROM eco.resultado_eleitoral_uf")).scalars().all()
    assert nomes == ["Oficial"]


def test_constraints_do_banco_recusam_o_que_o_etl_nunca_enviaria(limpo, pg_engine):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), pg_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO eco.resultado_eleitoral_uf (ano_eleicao, turno, uf, vencedor_nome, vencedor_partido, "
                "vencedor_votos_pct, segundo_nome, segundo_partido, segundo_votos_pct, fonte_id) "
                "SELECT 2022, 3, 'AC', 'a', 'b', 50, 'c', 'd', 40, id FROM etl.fonte LIMIT 1"
            )
        )
