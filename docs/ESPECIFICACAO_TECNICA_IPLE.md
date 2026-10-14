# Especificação Técnica: Índice de Poder Legislativo do Executivo (IPLE)

Esta especificação define os requisitos de engenharia de dados, regras de negócio e fórmulas matemáticas para a implementação do **Índice de Poder Legislativo do Executivo (IPLE)** e suas variáveis contextuais na plataforma **LegisData**.

---

## 1. Escopo e Objetivo

O IPLE processa dados brutos de produção legislativa (proposições, votações nominais e mensagens de veto) para calcular objetivamente o grau de governabilidade e a força política de chefes do Executivo (Presidente da República) frente ao Congresso Nacional.

O indicador varia estritamente de **0.000 a 1.000** (normalizado).

---

## 2. Requisitos de Dados e Entradas do Pipeline

O sistema processa as seguintes entidades de dados das Casas Legislativas (Câmara dos Deputados e Senado Federal):

1. **Proposições do Executivo ($P_{exec}$):** Projetos de lei, PECs e medidas provisórias cuja autoria formal seja de iniciativa exclusiva ou discricionária do Poder Executivo.
   - *Filtro de Relevância:* Exclusão de matérias de autoria parlamentar de baixa relevância e projetos meramente cerimoniais.
2. **Proposições do Executivo Aprovadas ($P_{exec\_aprov}$):** Subconjunto de $P_{exec}$ que concluiu o rito de tramitação bicameral e foi transformado em lei (promulgado ou sancionado).
3. **Vetos do Executivo ($V_{total}$):** Total de mensagens de veto (totais ou parciais) aplicadas pelo chefe do Executivo a autógrafos legislativos.
4. **Vetos Mantidos ($V_{mantidos}$):** Subconjunto de vetos que passou pela deliberação da sessão conjunta do Congresso Nacional e cuja decisão de veto foi ratificada (mantida) pelos parlamentares.
5. **Vetos Pendentes de Pauta ($V_{pendentes}$):** Vetos ainda não apreciados pelo plenário do Congresso.
6. **Composição Partidária ($Cadeiras_i$):** Distribuição do número de assentos por partido ($i$) na Câmara (513) e Senado (81).
7. **Alinhamento Político Declarado ($Bloco_j$):** Classificação partidária em relação ao governo (Base / Independente / Oposição).

---

## 3. Fórmulas Matemáticas e Regras de Negócio

### 3.1. Taxa de Sucesso Legislativo (TS)
Mede o percentual de aprovação da agenda prioritária enviada pelo Executivo:
$$TS = \frac{|P_{exec\_aprov}|}{|P_{exec}|}$$

### 3.2. Taxa de Manutenção de Vetos (TMV)
Mede a capacidade do Executivo de fazer valer suas preferências em situações de conflito explícito com o Parlamento:
$$TMV = \frac{|V_{mantidos}|}{|V_{total\_apreciados}|}$$

* **Regra de Consistência Científica:** Vetos pendentes de pauta ($V_{pendentes}$) são rigorosamente expurgados do denominador $|V_{total\_apreciados}|$, impedindo penalizações artificiais ao Executivo por atrasos no cronograma de convocação das sessões conjuntas.
* **Salvaguarda de Divisão por Zero:** Quando $|V_{total\_apreciados}| = 0$, o sistema adota $TMV = 1.000$ (se nenhum veto foi derrubado) ou imputa $TS$ como o score principal.

### 3.3. Cálculo do IPLE Principal
O IPLE é a média aritmética simples das duas taxas ponderadas:
$$IPLE = \frac{TS + TMV}{2}$$

---

## 4. Variáveis Contextuais de Validação (QCA)

Para enriquecer a análise via **QCA (Qualitative Comparative Analysis)**, o sistema calcula três indicadores contextuais em paralelo:

1. **Tamanho da Oposição ($X_1$):**
   $$X_1 = \frac{\text{Total de Parlamentares em Bancadas de Oposição}}{\text{Total de Assentos Ativos na Casa}}$$
   - Sinaliza se a oposição atinge quórum para abertura de CPIs ($> 33.4\%$ ou $1/3$ dos membros).

2. **Fragmentação Partidária — Número Efetivo de Partidos ($X_2$):**
   $$NEP = \frac{1}{\sum_{i=1}^{n} (p_i)^2}$$
   *(Fórmula clássica de Laakso & Taagepera, 1979)*, onde $p_i$ é a proporção de assentos do partido $i$ no total da Casa.

3. **Polarização Ideológica Ponderada ($X_3$):**
   $$IPP = \sum_{i=1}^{n} p_i \cdot (x_i - \bar{x})^2$$
   Onde $p_i$ é a proporção de cadeiras do partido $i$, $x_i$ é a posição do partido na escala ideológica calibrada (1 = Esquerda a 10 = Direita), e $\bar{x} = \sum p_i x_i$ é a média ponderada da Casa.

---

## 5. Parâmetros de Calibragem e Ponto de Corte (Crisp-Set QCA)

| Indicador | Parâmetro de Corte | Classificação Se Verdadeiro (1) | Classificação Se Falso (0) |
| :--- | :--- | :--- | :--- |
| **TS** | $\ge 87\%$ ($0.870$) | Sucesso Alto | Sucesso Baixo |
| **TMV** | $\ge 70\%$ ($0.700$) | Manutenção Alta | Manutenção Baixa |
| **IPLE** | $\ge 0.785$ | Executivo Forte / Poderoso | Executivo Fraco / Desafiado |
| **Oposição ($X_1$)** | $> 33.4\%$ ($0.334$) | Oposição Numerosa (Quórum CPI) | Oposição Fraca |
| **Fragmentação ($X_2$)** | $\ge 8.45$ (NEP) | Parlamento Fragmentado | Baixa Fragmentação |
| **Polarização ($X_3$)** | $> 2.20$ (IPP) | Parlamento Polarizado | Baixa Polarização |

---

## 6. Resultados Históricos Consolidados (Nova República 1992 - Presente)

| Mandato | Presidente | Período | TS | TMV | IPLE Score | NEP ($X_2$) | IPP ($X_3$) | Classificação QCA |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `itamar-franco-1992` | Itamar Franco | 1992-1995 | 88.2% | 84.4% | **0.863** | 8.42 | 2.90 | Executivo Forte / Poderoso |
| `fhc-1995` | Fernando Henrique Cardoso 1 | 1995-1999 | 90.9% | 89.8% | **0.904** | 8.14 | 3.03 | Executivo Forte / Poderoso |
| `fhc-1999` | Fernando Henrique Cardoso 2 | 1999-2003 | 86.8% | 75.1% | **0.810** | 7.12 | 2.94 | Executivo Forte / Poderoso |
| `lula-2003` | Luiz Inácio Lula da Silva 1 | 2003-2007 | 87.2% | 81.3% | **0.842** | 8.52 | 4.02 | Executivo Forte / Poderoso |
| `lula-2007` | Luiz Inácio Lula da Silva 2 | 2007-2011 | 91.4% | 90.4% | **0.909** | 9.33 | 3.82 | Executivo Forte / Poderoso |
| `dilma-2011` | Dilma Rousseff 1 | 2011-2015 | 86.8% | 71.5% | **0.792** | 10.74 | 3.91 | Executivo Forte / Poderoso |
| `dilma-2015` | Dilma Rousseff 2 | 2015-2016 | 61.1% | 42.2% | **0.516** | 13.56 | 4.88 | Executivo Fraco (Impeachment) |
| `temer-2016` | Michel Temer | 2016-2019 | 80.0% | 72.2% | **0.761** | 14.12 | 3.10 | Executivo Fraco / Desafiado |
| `bolsonaro-2019` | Jair Bolsonaro | 2019-2023 | 74.0% | 62.7% | **0.683** | 16.41 | 4.40 | Executivo Fraco / Desafiado |
| `lula-2023` | Luiz Inácio Lula da Silva 3 | 2023-2027 | 82.1% | 68.8% | **0.755** | 9.93 | 4.55 | Executivo Fraco / Desafiado |

---

## 7. Arquitetura e Integração Técnica

1. **Módulo de Cálculo (`backend/app/services/iple_service.py`):**
   - Funções analíticas: `calcular_taxa_sucesso`, `calcular_taxa_manutencao_vetos`, `calcular_iple`, `calcular_nep`, `calcular_polarizacao_ideologica`, `calibrar_crisp_set_qca`.
   - Banco de dados histórico completo de mandatos presidenciais com parâmetros empíricos calibrados.
2. **Endpoints de API:**
   - `GET /api/v1/executivo/iple?mandate_id=...`: Devolve o payload completo do mandato ou de todos os mandatos.
   - `GET /api/v1/analytics/congress-composition?mandate_id=...`: Devolve a composição das casas legislativas e o IPLE.
   - `GET /api/v1/analytics/mandates-performance`: Devolve todos os mandatos enriquecidos com `iple`.
   - `GET /api/v1/analytics/compare-mandates`: Devolve o confronto direto de dois mandatos com delta de IPLE e governabilidade.
3. **Componentes Frontend:**
   - `CongressCompositionPanel.tsx`: Card de IPLE, barras de TS e TMV, badges Crisp-set e modal expansível com explicação detalhada da metodologia.
   - `ExecutivoPanel.tsx`: Seção completa de IPLE no Raio-X do Executivo e alternador dinâmico de ranking entre PIB Médio e IPLE.
   - `comparador/page.tsx`: Dimensão 4 na Tabela Multidimensional confrontando governabilidade e variáveis QCA lado a lado.
