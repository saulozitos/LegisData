# Relatório de Auditoria e Rastreabilidade: Séries Curadas e Fontes Históricas

Este documento registra a auditoria, verificação e rotulagem oficial das séries históricas curadas do projeto **LegisData**, garantindo transparência total e conformidade com o **Princípio de Confiabilidade Oficial**.

Data do registro: 2026-10-13.

---

## 1. Composição das Bancadas e Presidentes das Casas Legislativas

- **Arquivo**: `etl/data/processed/composicao_congresso.json` e `etl/extractors/composicao_extractor.py`.
- **Fonte Primária**:
  - Dados Abertos do TSE (bancadas eleitas para a Câmara e Senado na data da eleição geral).
  - Anais da Câmara dos Deputados e do Senado Federal para mesas diretoras e presidentes eleitos em fevereiro de cada biênio.
- **Divergências e Migrações Partidárias**:
  - O total de deputados e senadores por bancada reflete a **configuração inicial pós-posse** da legislatura correspondente. Trocas partidárias posteriores decorrentes da "janela partidária", fusões de partidos (ex.: DEM + PSL = União Brasil, PTB + Patriota = PRD) e cassações judiciais geram divergências naturais ao longo do mandato.
  - Para o Senado de 1995 (mandato FHC 1), os dados abertos do TSE cobrem apenas a partir de 1994 (senadores com mandato de 8 anos eleitos em 1990 não possuem registro estruturado no portal de dados abertos do TSE). Por esse motivo, esse mandato contém a nota explicativa explícita no JSON e na interface.
  - As bancadas trazem notas metodológicas transparentes exibidas no painel de Composição de Governo.

---

## 2. Espectro Político e Lemas Partidários

- **Fontes**: Estatutos registrados no TSE, dados do DIAP (Departamento Intersindical de Assessoria Parlamentar) e classificação consolidada da Ciência Política brasileira.
- **Rótulos**: Centro-Esquerda, Esquerda, Centro, Centro-Direita e Direita.
- **Princípio**: Não são emitidos juízos de valor editorial; os rótulos refletem o posicionamento público nos estatutos partidários oficiais e na literatura acadêmica de referência.

---

## 3. Fidelidade Partidária (`NOMADES_HISTORICO`)

- **Arquivo**: `etl/data/processed/fidelidade_partidaria_historica.json`.
- **Fonte Primária**: Dados Abertos do TSE — tabela `filiacao_partidaria` (arquivos estaduais consolidados).
- **Verificação**: Políticos rotulados como "nômades" (com alto número de trocas partidárias) possuem todas as suas desfiliações e novas filiações rastreadas por data oficial de certidão de filiação partidária no TSE.

---

## 4. Marcos Políticos e Posse de Michel Temer

- **Data Definida**: `31/08/2016`.
- **Base Jurídica Oficial**: Ata da Sessão Conjunta do Congresso Nacional de 31 de agosto de 2016, que lavrou a perda do mandato de Dilma Rousseff após julgamento pelo Senado Federal e a posse imediata de Michel Temer como 37º Presidente da República Federativa do Brasil.

---

## 5. Indicadores Macroeconômicos e Sociais

| Indicador | Fonte Oficial | Metodologia de Cálculo | Observação Técnica |
|---|---|---|---|
| **Ibovespa (2026)** | B3 / Yahoo Finance | Média ou última cotação disponível no ano | Rotulado como **ano parcial em curso** (sem fechamento oficial consolidado). |
| **Taxa de Desemprego** | IBGE / PNAD Contínua | Média aritmética dos 4 trimestres do ano | O dado anual oficial do IBGE é a média dos 4 trimestres (ex.: 8,0% em 2023), diferindo pontualmente da taxa do 4º trimestre isolado divulgada pela mídia (7,8%). |
| **Homicídios (Taxa por 100k)** | Atlas da Violência / IPEA / FBSP / SIM-DataSUS | Óbitos por agressão / População de projeção estatística do SIM | A taxa do Atlas (22,0 por 100 mil em 2023) utiliza a base censitária recalculada do DataSUS, mantendo consistência com a série histórica de 30 anos. |
| **Inflação (IPCA)** | IBGE / SIDRA (Tabela 1737) | Variação percentual acumulada no ano civil (dezembro a dezembro) | Fonte primária oficial e inalterada. |
| **PIB Real** | IBGE / Contas Nacionais Trimestrais e Anuais | Variação percentual anual do volume do PIB | Série histórica oficial desde 1994. |
| **Salário Mínimo** | Diário Oficial da União (DOU) / Legislação Federal | Valor nominal fixado por Lei ou Medida Provisória em 1º de janeiro de cada ano | Valores convertidos para dólar Ptax média anual do BCB para análises comparativas. |

---

## 6. Papel do `IBGEExtractor`

- O componente `etl/extractors/ibge_extractor.py` provê a interface programática direta com a API do SIDRA do IBGE (tabelas 1737, 6784, 5938, etc.).
- Os pipelines chamam o extrator para alimentar as séries temporais de indicadores sociais por Unidade da Federação e nível nacional.
