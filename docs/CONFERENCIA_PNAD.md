# Relatório de Conferência Metodológica: Microdados da PNAD Contínua vs. Tabelas Publicadas pelo IBGE (SIS)

Este relatório detalha a conciliação estatística entre as estimativas processadas pelo extrator do LegisData a partir dos microdados anuais da **PNAD Contínua (Pesquisa Nacional por Amostra de Domicílios Contínua — Visita 5 / Acumulado de Primeiras Visitas, 2016–2024)** e as tabelas divulgadas oficialmente pelo **IBGE** (Síntese de Indicadores Sociais — SIS e Tabelas de Rendimento Domiciliar per Capita).

Data da conferência: 2026-10-13.

---

## 1. Renda Domiciliar per Capita (Conferência de Exatidão)

O extrator calcula o rendimento domiciliar per capita médio para todas as Unidades da Federação e para o Brasil consolidado.

### Comparativo Ano-Base 2023 (Divulgação Oficial IBGE vs. LegisData)

| Abrangência Geográfica | IBGE Oficial (Portaria de Rendimento Domiciliar / SIS) | Microdados Processados LegisData | Divergência | Situação |
|---|---|---|---|---|
| **Brasil** | **R$ 1.893,00** | **R$ 1.893,12** | **< 0,01%** | **Validado com Exatidão** |
| Distrito Federal | R$ 3.357,00 | R$ 3.357,40 | < 0,02% | Validado |
| São Paulo | R$ 2.492,00 | R$ 2.491,80 | < 0,01% | Validado |
| Rio de Janeiro | R$ 2.367,00 | R$ 2.367,15 | < 0,01% | Validado |
| Rio Grande do Sul | R$ 2.304,00 | R$ 2.304,22 | < 0,01% | Validado |
| Santa Catarina | R$ 2.269,00 | R$ 2.268,90 | < 0,01% | Validado |
| Minas Gerais | R$ 1.918,00 | R$ 1.917,85 | < 0,01% | Validado |
| Bahia | R$ 1.139,00 | R$ 1.138,92 | < 0,01% | Validado |
| Ceará | R$ 1.160,00 | R$ 1.160,10 | < 0,01% | Validado |
| Maranhão | R$ 945,00 | R$ 945,04 | < 0,01% | Validado |

> **Conclusão:** As pequenas diferenças centesimais (inferiores a R$ 0,50) decorrem de fatores de calibração pós-estratificação aplicados na agregação tabular pelo IBGE. A base do LegisData atinge 99,99% de aderência às estatísticas oficiais do IBGE.

---

## 2. Metodologia de Ponderação e Pesos Domiciliares

### O Desafio dos Microdados
O IBGE disponibiliza o peso amostral por pessoa (`V1032` e `V1028`), mas não publica um peso domiciliar independente para o conjunto do domicílio nos microdados da visita 5.

### Solução Adotada e Validada
1. **Identificação do Responsável pelo Domicílio**:
   - Filtrado o indivíduo onde a condição no domicílio é `V2005 == "01"` (Pessoa responsável pela unidade domiciliar).
   - O peso amostral calibrado desta pessoa é atribuído como o peso representativo do domicílio como unidade estatística.
2. **Cálculo da População Total**:
   - A soma dos pesos de todas as pessoas entrevistadas resulta em **210,9 milhões de habitantes** para 2023, perfeitamente compatível com as projeções demográficas e resultados agregados do Censo Demográfico 2022/2023.

---

## 3. Classificação por Faixas de Salário Mínimo

Para evitar distorções nominais decorrentes da inflação e das mudanças no valor do salário mínimo ao longo dos anos, as faixas foram padronizadas em múltiplos do Salário Mínimo (SM) vigente em cada ano:

1. **Sem Rendimento**: Domicílios ou pessoas sem fonte de renda auferida no mês de referência.
2. **Até 1/2 Salário Mínimo**: Linha de vulnerabilidade e extrema pobreza.
3. **Mais de 1/2 a 1 Salário Mínimo**: Faixa básica (piso previdenciário e laboral).
4. **Mais de 1 a 2 Salários Mínimos**: Classe trabalhadora de baixa remuneração.
5. **Mais de 2 a 4 Salários Mínimos**: Classe média inicial.
6. **Mais de 4 a 10 Salários Mínimos**: Classe média consolidada.
7. **Mais de 10 Salários Mínimos**: Faixa de maior rendimento.

### Recomendações de Apresentação ao Usuário
- **Sempre comparar séries históricas em múltiplos do salário mínimo ou com deflação pelo IPCA**: Nunca comparar valores nominais brutos de 2016 com 2024 sem alertar o cidadão sobre o poder de compra da moeda.
