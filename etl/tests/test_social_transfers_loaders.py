"""Carga no banco de indicadores sociais oficiais e repasses federais (SQLite em memória)."""

import json
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from app.models import AnnualSocialIndicator, Base, FederalTransferByState, StateSocialIndicator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from etl.pipelines.db_loader import DatabaseLoader
from etl.utils.provenance import mark_official


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        yield s


def repasse(mandato="lula-2023", uf="AC", area="Saúde", valor=100.0, **extra):
    base = {
        "mandato_id_ref": mandato,
        "ano": 2026,
        "uf": uf,
        "estado_nome": "Acre",
        "regiao": "Norte",
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


def gravar(pasta: Path, nome: str, dados) -> None:
    (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def test_repasses_oficiais_sao_carregados_com_periodo_e_substituem_o_retrato_do_mandato(session, tmp_path):
    gravar(tmp_path, "repasses_federais_uf.json", [repasse(valor=100.0), repasse(area="Educação", valor=50.0)])
    loader = DatabaseLoader(data_dir=tmp_path)
    loader._load_federal_transfers(session)
    session.commit()
    linha = session.query(FederalTransferByState).filter_by(area_tematica="Saúde").one()
    assert linha.valor_pago_brl == Decimal("100.00")
    assert (linha.periodo_inicio, linha.periodo_fim, linha.meses_cobertos, linha.parcial) == (
        "2023-01",
        "2026-09",
        45,
        False,
    )

    # nova extração: totais maiores, outro `ano` de referência e uma área que sumiu -> o retrato é substituído
    gravar(tmp_path, "repasses_federais_uf.json", [repasse(valor=120.0, ano=2027, periodo_fim="2026-10")])
    loader._load_federal_transfers(session)
    session.commit()
    linhas = session.query(FederalTransferByState).all()
    assert len(linhas) == 1 and linhas[0].valor_pago_brl == Decimal("120.00") and linhas[0].periodo_fim == "2026-10"


def test_carga_de_repasses_preserva_mandatos_ausentes_do_arquivo(session, tmp_path):
    session.add(
        FederalTransferByState(
            mandate_id_ref="dilma-2011",
            ano=2014,
            uf="AC",
            estado_nome="Acre",
            regiao="Norte",
            area_tematica="Saúde",
            valor_pago_brl=Decimal("1.00"),
        )
    )
    session.commit()
    gravar(tmp_path, "repasses_federais_uf.json", [repasse()])
    DatabaseLoader(data_dir=tmp_path)._load_federal_transfers(session)
    session.commit()
    assert {r.mandate_id_ref for r in session.query(FederalTransferByState).all()} == {"dilma-2011", "lula-2023"}


def test_repasses_legados_sem_proveniencia_sao_recusados(session, tmp_path):
    gravar(tmp_path, "repasses_federais_uf.json", [{**repasse(), "fonte": None, "is_synthetic": None}])
    DatabaseLoader(data_dir=tmp_path)._load_federal_transfers(session)
    assert session.query(FederalTransferByState).count() == 0


def test_indicadores_sociais_oficiais_chegam_ao_banco_sem_zerar_lacunas(session, tmp_path):
    anual = pd.DataFrame(
        [
            mark_official(
                {
                    "ano": 2024,
                    "analfabetismo": 5.3,
                    "extrema_pobreza_pct": 4.7,
                    "pobreza_pct": 26.5,
                    "inseguranca_alimentar_pct": None,
                    "inseguranca_alimentar_total_pct": 24.2,
                    "gini": 0.504,
                    "desemprego_pct": 6.9,
                    "serie_gini": "PNAD Contínua (t7435)",
                },
                "IBGE/SIDRA (PNAD, PNAD Contínua, ODS) e BCB/SGS",
            )
        ]
    )
    anual.to_csv(tmp_path / "indicadores_sociais_anuais.csv", index=False)
    uf = pd.DataFrame(
        [
            mark_official(
                {
                    "ano": 2024,
                    "uf": "MA",
                    "estado_nome": "Maranhão",
                    "regiao": "Nordeste",
                    "taxa_analfabetismo_pct": 11.2,
                    "extrema_pobreza_pct": 13.9,
                    "pobreza_pct": 51.3,
                    "inseguranca_alimentar_pct": None,
                    "indice_gini": 0.487,
                },
                "IBGE/SIDRA",
            )
        ]
    )
    uf.to_csv(tmp_path / "indicadores_sociais_uf.csv", index=False)

    loader = DatabaseLoader(data_dir=tmp_path)
    loader._load_social_and_election_data(session)
    loader._load_social_and_election_data(session)  # idempotente
    session.commit()

    a = session.query(AnnualSocialIndicator).one()
    assert a.poverty_pct == Decimal("26.50") and a.food_insecurity_total_pct == Decimal("24.20")
    assert a.unemployment_pct == Decimal("6.90") and a.gini_index == Decimal("0.504")
    assert a.food_insecurity_pct is None and "t7435" in a.gini_series  # lacuna segue None
    assert a.data_source.startswith("IBGE/SIDRA")
    estado = session.query(StateSocialIndicator).one()
    assert estado.uf == "MA" and estado.poverty_pct == Decimal("51.30") and estado.food_insecurity_pct is None
