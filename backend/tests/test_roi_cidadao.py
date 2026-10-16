"""Fórmula do ROI do Cidadão, sem banco: pesos, limites, piso de pontos e faixas."""

import pytest
from app.services import roi_cidadao
from app.services.roi_cidadao import calcular_roi


def _roi(taxa, pontos, custo, ok=True):
    return calcular_roi(custo_total=custo, pontos_ialp=pontos, taxa_presenca=taxa, dados_suficientes=ok)


def test_sem_dados_suficientes_nada_e_inventado():
    r = _roi(95.0, 80.0, 1000.0, ok=False)
    assert r["nota"] is None and r["score"] is None and r["custo_por_ponto"] is None
    assert "Dados insuficientes" in r["diagnostico"]


@pytest.mark.parametrize(
    "taxa,pontos,custo,nota,faixa",
    [
        (100.0, 100.0, 0.0, 100.0, "A+"),  # tudo no máximo
        (100.0, 62.5, 0.0, 85.0, "A+"),  # fronteira da faixa A+
        (100.0, 25.0, 0.0, 70.0, "A"),  # fronteira da faixa A
        (100.0, 0.0, 0.0, 60.0, "B"),  # sem entrega: assiduidade + custo zero
        (100.0, 0.0, 50000.0, 45.0, "C"),  # piso de 1 ponto: custo por ponto = custo total
        (50.0, 0.0, 100000.0, 15.0, "D"),  # custo por ponto na referência zera a parte de custo
        (None, 0.0, 0.0, 30.0, "D"),  # sem taxa de presença a parte de assiduidade é zero
        (100.0, 250.0, 0.0, 100.0, "A+"),  # entrega acima da referência é limitada em 40 pontos
        (100.0, 100.0, 20000000.0, 70.0, "A"),  # custo por ponto acima da referência não fica negativo
    ],
)
def test_nota_e_faixa(taxa, pontos, custo, nota, faixa):
    r = _roi(taxa, pontos, custo)
    assert r["nota"] == pytest.approx(nota, abs=0.05)
    assert r["score"] == faixa


def test_cortes_entre_faixas():
    # com 100% de presença e nenhum ponto, a nota é 30 + 0,3 x (100 - custo/1000)
    assert _roi(100.0, 0.0, 16000.0)["score"] == "B"  # 55,2
    assert _roi(100.0, 0.0, 18000.0)["score"] == "C"  # 54,6
    assert _roi(100.0, 0.0, 66000.0)["score"] == "C"  # 40,2
    assert _roi(100.0, 0.0, 68000.0)["score"] == "D"  # 39,6


def test_piso_de_um_ponto_no_custo_por_ponto():
    r = _roi(90.0, 0.15, 120000.0)
    assert r["custo_por_ponto"] == 120000.0  # divide por 1, não por 0,15


def test_pesos_somam_cem():
    assert roi_cidadao.PESO_ASSIDUIDADE + roi_cidadao.PESO_ENTREGA + roi_cidadao.PESO_CUSTO == pytest.approx(1.0)
    assert "30% assiduidade" in roi_cidadao.METODOLOGIA and "R$ 100.000" in roi_cidadao.METODOLOGIA
