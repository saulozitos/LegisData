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

## 6. Resultados Históricos Consolidados (Nova República, janela de dados a partir de 1995)

Tabela gerada da API (`GET /api/v1/executivo/iple`) com a carga atual de `leg.producao_executivo`, `leg.bancada_mandato` e `core.partido_posicao_ideologica`. "Indisponível" significa que o mandato não tem bancadas carregadas para aquela variável (nunca é zero). Os períodos seguem a regra da seção 8.

| Mandato | Presidente | Período | TS | TMV | IPLE Score | NEP ($X_2$) | IPP ($X_3$) | Classificação QCA |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `fhc-1995` | Fernando Henrique Cardoso (FHC 1) | 1995 - 1998 | 90.9% | 89.8% | **0.904** | 8.14 | 3.03 | Executivo Forte / Poderoso |
| `fhc-1999` | Fernando Henrique Cardoso (FHC 2) | 1999 - 2002 | 83.1% | 78.8% | **0.810** | indisponível | indisponível | Executivo Forte / Poderoso |
| `lula-2003` | Lula (Lula 1) | 2003 - 2006 | 87.2% | 81.2% | **0.842** | 8.52 | 4.02 | Executivo Forte / Poderoso |
| `lula-2007` | Lula (Lula 2) | 2007 - 2010 | 91.6% | 90.2% | **0.909** | 9.29 | 3.82 | Executivo Forte / Poderoso |
| `dilma-2011` | Dilma Rousseff (Dilma 1) | 2011 - 2014 | 84.5% | 73.8% | **0.792** | 10.43 | 4.00 | Executivo Forte / Poderoso |
| `dilma-2015` | Dilma Rousseff (Dilma 2) | 2015 - 2016 | 57.1% | 46.2% | **0.516** | 13.33 | 3.47 | Executivo Fraco |
| `temer-2016` | Michel Temer | 2016 - 2018 | 81.1% | 71.0% | **0.761** | 13.33 | 3.53 | Executivo Fraco |
| `bolsonaro-2019` | Jair Bolsonaro | 2019 - 2022 | 74.0% | 62.7% | **0.683** | 16.41 | 4.40 | Executivo Fraco |
| `lula-2023` | Lula (Lula 3) | 2023 - Presente | 82.1% | 68.8% | **0.754** | 9.93 | 4.55 | Executivo Fraco |

---

## 7. Arquitetura e Integração Técnica

1. **Módulo de Cálculo (`backend/app/services/iple_service.py`):**
   - Funções analíticas: `calculate_ts`, `calculate_tmv`, `calculate_iple`, `calculate_nep`, `calculate_ipp`, `calibrate_crisp_set`.
   - A produção do Executivo vem de `leg.producao_executivo`, as bancadas de `leg.bancada_mandato` e a escala ideológica de `core.partido_posicao_ideologica`; nada disso é constante no código. `bancadas_service.py` lê bancadas, totais e governabilidade.
2. **Endpoints de API:**
   - `GET /api/v1/executivo/iple?mandate_id=...`: Devolve o payload completo do mandato ou de todos os mandatos.
   - `GET /api/v1/analytics/congress-composition?mandate_id=...`: Devolve a composição das casas legislativas e o IPLE.
   - `GET /api/v1/analytics/mandates-performance`: Devolve todos os mandatos enriquecidos com `iple`.
   - `GET /api/v1/analytics/compare-mandates`: Devolve o confronto direto de dois mandatos com delta de IPLE e governabilidade.
3. **Componentes Frontend:**
   - `CongressCompositionPanel.tsx`: Card de IPLE, barras de TS e TMV, badges Crisp-set e modal expansível com explicação detalhada da metodologia.
   - `ExecutivoPanel.tsx`: Seção completa de IPLE no Raio-X do Executivo e alternador dinâmico de ranking entre PIB Médio e IPLE.
   - `comparador/page.tsx`: Dimensão 4 na Tabela Multidimensional confrontando governabilidade e variáveis QCA lado a lado.

---

## 8. Regras de cálculo da camada de dados (Entrega 3b)

- **Período do mandato.** O fim de `core.mandato` é exclusivo quando coincide com a posse do sucessor em 1º de janeiro (o mandato que termina em 01/01/2003 vai até 2002). Mandato que termina no meio do ano (impeachment, renúncia) vale até o próprio ano do fim: Dilma 2 (fim em 31/08/2016) é "2015 - 2016". A regra única é `periodos.ultimo_ano_do_mandato`.
- **Governabilidade.** Base aliada, centro e oposição são somas das bancadas classificadas. Maioria simples: `base > total / 2`. Maioria para PEC: `base >= ceil(3 * total / 5)`. Sem nenhuma bancada classificada, tudo é `None`. Com classificação parcial, a maioria só é afirmada quando a base já alcança o mínimo (verdadeiro) ou quando nem somando todas as cadeiras sem classificação ela alcançaria (falso); no meio disso é `None` (não dá para afirmar) e `nao_classificadas_cadeiras` mostra o que falta classificar.
- **Variável ausente nunca vira zero.** X1, X2 e X3 sem bancadas (ou sem classificação, no caso de X1) ficam `None` e a calibragem sai "Indisponível". A cobertura da escala ideológica (`cobertura_ipp_pct`) informa quantas cadeiras tinham posição conhecida no cálculo do X3.
- **Índice do salário.** Base 100 no primeiro ano da série (1995). O IPCA acumulado percorre todos os anos desde o primeiro; se faltar o IPCA de algum ano do intervalo, o índice sai `None` dali em diante, em vez de um acumulado parcial.
- **Oposição parcial não é piso.** Se parte das cadeiras da Casa não foi classificada, X1 não usa a soma parcial da oposição: na Câmara vale a oposição curada de `leg.producao_executivo`, no Senado X1 fica indisponível. A composição marca `dados_incompletos` nesse caso.
- **Proposições do mandato em curso.** Para o mandato sem data de fim, a contagem real da base considera só proposições do Executivo apresentadas a partir do início do mandato (a base cobre desde 1995) e vale se superar a curadoria.
