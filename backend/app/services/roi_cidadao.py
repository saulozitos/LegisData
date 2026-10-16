"""ROI do Cidadão: assiduidade (30%) + entrega legislativa em pontos IALP (40%) + custo por ponto IALP (30%).

A entrega vem do IALP (tipo x papel do autor x andamento), não da contagem de proposições: assinar requerimentos ou
apoiar projetos de outros vale pouco, e só avanço na tramitação pontua de verdade.
"""

from typing import Any, Dict, Optional

# pontos IALP que dão a nota máxima na parte de entrega e custo por ponto que zera a parte de custo
PONTOS_IALP_REFERENCIA = 100.0
CUSTO_POR_PONTO_REFERENCIA = 100000.0
PESO_ASSIDUIDADE = 0.30
PESO_ENTREGA = 0.40
PESO_CUSTO = 0.30
PISO_DE_PONTOS = 1.0

# (nota mínima, faixa, diagnóstico), da maior para a menor
_FAIXAS = (
    (
        85.0,
        "A+",
        "Alta eficiência: entrega legislativa expressiva em pontos IALP, assiduidade alta e baixo custo por ponto.",
    ),
    (70.0, "A", "Bom custo-benefício para o cidadão, com produção legislativa consistente."),
    (55.0, "B", "Produção legislativa e assiduidade em nível regular."),
    (40.0, "C", "Custo operacional elevado em relação à entrega legislativa medida em pontos IALP."),
    (0.0, "D", "Baixo retorno legislativo em proporção ao custo operacional do mandato."),
)
DIAGNOSTICO_SEM_DADOS = "Dados insuficientes (CEAP, remuneração e presenças são necessários para calcular o indicador)."

METODOLOGIA = (
    f"Nota = 30% assiduidade + 40% pontos IALP (referência de {PONTOS_IALP_REFERENCIA:.0f} pontos para a nota máxima "
    f"nesta parte) + 30% custo por ponto IALP (zera em R$ {CUSTO_POR_PONTO_REFERENCIA:,.0f} por ponto). O custo soma a "
    "cota parlamentar (CEAP) e os subsídios brutos registrados."
).replace(",", ".")


def calcular_roi(
    *,
    custo_total: float,
    pontos_ialp: float,
    taxa_presenca: Optional[float],
    dados_suficientes: bool,
) -> Dict[str, Any]:
    """Nota, faixa e custo por ponto. Sem dados suficientes nada é inventado: tudo vem None."""
    if not dados_suficientes:
        return {"nota": None, "score": None, "custo_por_ponto": None, "diagnostico": DIAGNOSTICO_SEM_DADOS}
    # abaixo de 1 ponto o custo por ponto usaria o custo inteiro: a nota parte do piso de 1 ponto
    custo_por_ponto = round(custo_total / max(pontos_ialp, PISO_DE_PONTOS), 2)
    fator_presenca = min(taxa_presenca or 0.0, 100.0) * PESO_ASSIDUIDADE
    fator_entrega = min(pontos_ialp / PONTOS_IALP_REFERENCIA * 100.0, 100.0) * PESO_ENTREGA
    fator_custo = max(0.0, 100.0 - custo_por_ponto / CUSTO_POR_PONTO_REFERENCIA * 100.0) * PESO_CUSTO
    nota = round(fator_presenca + fator_entrega + fator_custo, 1)
    _, faixa, diagnostico = next(f for f in _FAIXAS if nota >= f[0])
    return {"nota": nota, "score": faixa, "custo_por_ponto": custo_por_ponto, "diagnostico": diagnostico}
