# Registro Oficial de Fontes, URLs e APIs — LegisData

Este documento registra com **100% de cobertura** todas as fontes de dados oficiais, URLs, endpoints de APIs REST, downloads em lote (bulk files), parâmetros de consulta, periodicidade de atualização e regras de integração utilizadas pelo projeto **LegisData**.

> [!IMPORTANT]
> **Princípio de Confiabilidade Oficial**: O LegisData não utiliza nenhum dado inventado, sintético ou estimado. Quando uma informação não é fornecida pelas APIs e relatórios oficiais, o campo permanece estritamente `null` e a interface exibe "Dado indisponível".

---

## 0. Especificações oficiais das APIs (consulta obrigatória antes de mexer em extrator)

Cópias em markdown das especificações oficiais, para consultar campos, parâmetros e limites em vez de adivinhar:

- [`docs/apis/camara-dadosabertos-api.md`](apis/camara-dadosabertos-api.md): API de Dados Abertos da Câmara (`https://dadosabertos.camara.leg.br/api/v2/`, 79 operações em 11 grupos; spec em `.../api/v2/api-docs`). Listagens devolvem 15 itens por padrão e no máximo 100 por requisição.
- [`docs/apis/senado-dadosabertos-api.md`](apis/senado-dadosabertos-api.md): API de Dados Abertos do Senado (`https://legis.senado.leg.br/dadosabertos`; spec em `.../v3/api-docs`).

**Limites de requisição** (valem para todo extrator e toda rotina agendada):

- **Senado:** mais de **10 requisições por segundo** podem receber **HTTP 429**; em horários de muita demanda, **HTTP 503**. A própria documentação pede para **não agendar rotinas em horários arredondados** (00:00, 01:15…), porque isso gera picos simultâneos. Por isso o `legisdata-financas.timer` roda às 05:37 UTC, com atraso aleatório.
- **Câmara, arquivos em lote** (`www.camara.leg.br/cotas/Ano-{ano}.csv.zip` e os de `dadosabertos.camara.leg.br/arquivos/`): a especificação da API não descreve limite para eles, mas na prática o servidor responde **429** a vários CSVs anuais pedidos em sequência (visto com 7 downloads em cerca de 30 s). A CEAP espera 10 s entre downloads e tenta de novo uma vez após 90 s (`PAUSA_ENTRE_DOWNLOADS`, `ESPERA_NOVA_TENTATIVA` em `sync_ceap_emendas.py`).
- Use sempre `etl.utils.http_client.HttpClient` (timeout, retry com backoff e rate limit) e confira o limite aqui antes de paralelizar qualquer extração.

---

## 1. Câmara dos Deputados

### 1.1 API de Dados Abertos (v2)
- **Documentação Oficial**: `https://dadosabertos.camara.leg.br/swagger/api.html`
- **Base URL**: `https://dadosabertos.camara.leg.br/api/v2`
- **Autenticação**: Não requer chave (acesso público irrestrito).
- **Formato**: JSON (cabeçalho `Accept: application/json`).
- **Limites de Requisição**: Recomenda-se limite de 5 a 10 requisições/segundo para evitar bloqueios temporários (`HTTP 429`).

#### Endpoints Utilizados:
1. **`/deputados`**:
   - *O que busca*: Lista de deputados federais por legislatura (`idLegislatura=56,57`), partidos, nomes eleitorais, UF de representação e link para fotos oficiais.
   - *Parâmetros*: `idLegislatura`, `ordem=ASC`, `ordenarPor=nome`.
2. **`/deputados/{id}`**:
   - *O que busca*: Biografia completa, nome civil, data de nascimento, escolaridade, naturalidade e redes oficiais.
3. **`/proposicoes`**:
   - *O que busca*: Catálogo de matérias legislativas com filtragem por tipo suportado (`siglaTipo=PEC,PL,PLP,MPV,PDL`), ano de apresentação e tramitação.
   - *Parâmetros*: `siglaTipo`, `ano`, `itens=100`.
4. **`/proposicoes/{id}`**:
   - *O que busca*: Ementa detalhada, autor original, regime de tramitação e URL da ficha no portal da Câmara.
5. **`/proposicoes/{id}/autores`**:
   - *O que busca*: Signatários da matéria para conferência de autoria e coautoria.
6. **`/votacoes/{id}/votos`**:
   - *O que busca*: Relação nominal de votos de cada deputado (Sim, Não, Abstenção, Obstrução, Artigo 17) para uma votação específica.
7. **`/votacoes/{id}/orientacoes`**:
   - *O que busca*: Orientação oficial de bancada e da liderança do "Governo" na votação.
8. **`/orgaos` e `/orgaos/{id}/votacoes`**:
   - *O que busca*: Deliberações e votações nominais realizadas nas comissões permanentes e temporárias da Casa (ex.: CCJC, CFT, CAE, etc.).

### 1.2 Arquivos Anuais em Lote (Bulk Data CSV)
- **Base URL**: `https://dadosabertos.camara.leg.br/arquivos/`
- **Periodicidade**: Atualização diária pelo portal da Câmara.
- **Arquivos baixados por ano (`{ano}` de 2019 a 2026)**:
  - `https://dadosabertos.camara.leg.br/arquivos/votacoes/csv/votacoes-{ano}.csv`: Metadados de todas as votações realizadas no plenário e comissões.
  - `https://dadosabertos.camara.leg.br/arquivos/votacoesVotos/csv/votacoesVotos-{ano}.csv`: Todos os votos nominais individuais proferidos no ano.
  - `https://dadosabertos.camara.leg.br/arquivos/votacoesProposicoes/csv/votacoesProposicoes-{ano}.csv`: Vinculação de votações a matérias legislativas.
  - `https://dadosabertos.camara.leg.br/arquivos/votacoesObjetos/csv/votacoesObjetos-{ano}.csv`: Objeto da deliberação da matéria.
  - `https://dadosabertos.camara.leg.br/arquivos/votacoesOrientacoes/csv/votacoesOrientacoes-{ano}.csv`: Orientações de bancada emitidas no ano.

### 1.3 Portal Oficial da Câmara — Relatórios de Presença e Remuneração
- **Presença em Plenário**:
  - *URL*: `https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}`
  - *O que busca*: Relatório oficial diário com registro deliberativo de cada sessão ordinária e extraordinária (Presença, Falta Justificada com motivo formal, Falta Não Justificada).
  - *Período Oficial Coberto*: **2020 a 2026** (100% extraído e carregado no banco local).
  - *Nota Oficial*: O portal da Câmara dos Deputados **não publica relatórios de presença para o ano de 2019** (retorna oficialmente "Não há dados").
- **Remuneração e Folha de Pagamento**:
  - *URL*: `https://www.camara.leg.br/deputados/{id}/remuneracao/{ano}`
  - *O que busca*: Demonstrativo mensal de contracheque dos parlamentares (subsídio mensal bruto, descontos legais e salário líquido).
  - *Período Coberto*: 2019 a 2026 (39.263 folhas mensais 100% carregadas).

---

## 2. Senado Federal

### 2.1 API de Dados Abertos
- **Documentação Oficial**: `https://legis.senado.leg.br/dadosabertos/docs/ui/index.html`
- **Base URL**: `https://legis.senado.leg.br/dadosabertos`
- **Formato**: JSON (cabeçalho `Accept: application/json`).
- **Autenticação**: Acesso público irrestrito.

#### Endpoints Utilizados:
1. **`/senador/lista/atual`**:
   - *O que busca*: Composição atual dos 81 senadores da República, identificadores de cadastro, partidos e UFs.
2. **`/senador/{codigo}` e `/senador/{codigo}/mandatos`**:
   - *O que busca*: Trajetória biográfica, suplentes, datas de início e fim dos mandatos na Casa.
3. **`/materia/pesquisa/lista?ano={ano}`**:
   - *O que busca*: Catálogo de matérias legislativas protocoladas no Senado nos anos de interesse.
4. **`/materia/{codigo}`**:
   - *O que busca*: Ementa oficial, autor ou autores signatários, matérias correlatas na Câmara e link de tramitação.
5. **`/votacao?ano={ano}`**:
   - *O que busca*: Votações nominais no Plenário do Senado Federal. Para votações nominais, traz a lista de votos de cada senador; para **votações secretas**, traz os totais apurados na urna (`totalVotosSim`, `totalVotosNao`, `totalVotosAbstencao`) sem individualizar o votante.
6. **`/plenario/votacao/orientacaoBancada/{dataInicio}/{dataFim}`**:
   - *O que busca*: Orientações de bancada emitidas pelas lideranças partidárias e pela liderança do Governo no Senado.
7. **`/dadosabertos/votacaoComissao/comissao/{siglaComissao}`**:
   - *O que busca*: Deliberações e votações nas comissões permanentes do Senado (CCJ, CAE, CAS, CRA, etc.).

---

## 3. Tribunal Superior Eleitoral (TSE)

### 3.1 Portal de Dados Abertos
- **Base URL**: `https://dadosabertos.tse.jus.br/dataset/`
- **Formato**: Arquivos compactados em ZIP contendo arquivos CSV com separador `;` e codificação `latin1` ou `utf-8`.

#### Arquivos Utilizados:
1. **Candidatos e Situação Eleitoral (`consulta_cand_{ano}.zip`)**:
   - *O que busca*: Registros de candidatura para Presidente, Senador e Deputado Federal (1994 a 2024). Traz número eleitoral, coligações, partido, declaração de bens vinculada e situação da candidatura (deferida, cancelada, indeferida com ou sem recurso, cassada).
2. **Bens e Patrimônio Declarado (`bem_candidato_{ano}.zip`)**:
   - *O que busca*: Declaração pormenorizada de patrimônio informada à Justiça Eleitoral em cada eleição disputada.
   - *Período Coberto*: 1994, 1998, 2006, 2010, 2014, 2018, 2022 e 2024.
   - *Nota Oficial*: O TSE não disponibilizou arquivos de bens para a eleição geral de 2002.
3. **Prestações de Contas e Doações Eleitorais (`prestacao_contas_{ano}.zip`)**:
   - *O que busca*: Doadores de campanha (nome/razão social, CPF/CNPJ), valores doados e despesas eleitorais de campanhas federais.
4. **Resultados Eleitorais por Município e UF (`votacao_candidato_munzona_{ano}.zip`)**:
   - *O que busca*: Totalização de votos nominais de todas as eleições presidenciais brasileiras desde 1994 por Unidade da Federação.
5. **Filiação Partidária (`filiacao_partidaria.zip`)**:
   - *O que busca*: Certidões de filiação e desfiliação de todos os políticos brasileiros, permitindo mapear fidelidade partidária e migrações.

---

## 4. DataJud — Conselho Nacional de Justiça (CNJ)

### 4.1 API Pública de Processos Judiciais
- **Documentação Oficial**: `https://datajud-wiki.cnj.jus.br/api-publica/`
- **Base URL**: `https://api-publica.datajud.cnj.jus.br/api_publica_{sigla_tribunal}/_search`
- **Autenticação**: Chave de API pública oficial do CNJ:
  `APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENxbUp1R2x6OFVacw==`
- **Formato**: Requisições HTTP POST com consultas JSON no padrão Elasticsearch.

#### Padrão de Numeração e Tribunais Suportados:
- Baseia-se na numeração única de 20 dígitos da **Resolução CNJ nº 65/2008**: `NNNNNNN-DD.AAAA.J.TR.OOOO`.
- *Roteamento de Tribunais*:
  - Superior Tribunal de Justiça: `api_publica_stj`
  - Supremo Tribunal Federal: `api_publica_stf`
  - Tribunal Superior Eleitoral: `api_publica_tse`
  - Tribunais Regionais Federais: `api_publica_trf1` a `api_publica_trf6`
  - Tribunais de Justiça Estaduais: `api_publica_tjsp`, `api_publica_tjrj`, `api_publica_tjmg`, `api_publica_tjba`, etc.
  - Tribunais Regionais Eleitorais: `api_publica_tre-sp`, `api_publica_tre-rj`, etc.

#### Metadados Coletados:
- Classe processual oficial (código e nome das Tabelas Processuais Unificadas — TPU).
- Assuntos processuais oficiais (código e descrição TPU).
- Data de ajuizamento/distribuição.
- Órgão julgador e comarca/vara.
- Últimas movimentações públicas (histórico de andamento).

---

## 5. Portal da Transparência do Governo Federal (CGU)

### 5.1 Emendas Parlamentares
- **URL**: `https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares`
- **Período**: 2019 a 2026.
- **O que busca**:
  - Código único da emenda (ex.: `202430300001`).
  - Autor institucional ou individual (Deputado, Senador, Bancada Estadual, Comissão Temática, Relator-Geral).
  - Tipo de emenda: Individual com Finalidade Definida, Individual Especial (PIX), Bancada Estadual, Comissão, Relator.
  - Valores orçados, empenhados (reservados), liquidados e pagos (entregues).
  - Município e UF de destino da verba.
  - Função orçamentária (Saúde, Educação, Cidades, Agricultura, Segurança, etc.).

### 5.2 Transferências da União por Estado
- **URL**: `https://portaldatransparencia.gov.br/download-de-dados/transferencias`
- **Período**: 2014 a 2026.
- **O que busca**: Repasses federais diretos da União para as 27 Unidades da Federação discriminados por área temática.

### 5.3 CEAP (Cota Parlamentar)
- **URL**: `https://www.camara.leg.br/transparencia/gastos-parlamentares/dados-abertos`
- **O que busca**: Notas fiscais, fornecedores, CNPJ e valores reembolsados aos deputados federais e senadores.

---

## 6. Instituto Brasileiro de Geografia e Estatística (IBGE)

### 6.1 API do SIDRA
- **Base URL**: `https://apisidra.ibge.gov.br/values/`
- **Tabelas Utilizadas**:
  - **Tabela 1737**: IPCA — Variação acumulada anual e mensal (1994 a 2026).
  - **Tabela 5938**: Contas Nacionais — Produto Interno Bruto (PIB) e taxas reais de crescimento.
  - **Tabela 6784**: PNAD Contínua — Taxa de desocupação (média dos 4 trimestres de cada ano).

### 6.2 Microdados Anuais da PNAD Contínua
- **Base URL**: `https://www.ibge.gov.br/estatisticas/sociais/trabalho/9171-pesquisa-nacional-por-amostra-de-domicilios-continua-mensal.html?edicao=39649&t=microdados`
- **Período**: 2016 a 2024 (Acumulado de 5ª Visita / Visita Anual).
- **O que busca**: Microdados de rendimento domiciliar per capita, salários e distribuição por classes de salário mínimo para o Brasil e todas as 27 UFs.

---

## 7. Banco Central do Brasil (BCB)

### 7.1 API do SGS (Sistema Gerenciador de Séries Temporais)
- **Base URL**: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json`
- **Séries Consultadas**:
  - `Série 1`: Taxa de câmbio — Dólar americano (comercial venda) diária e média anual.
  - `Série 432`: Meta da taxa Selic fixada pelo Copom (% a.a.).
  - `Série 4505`: Dívida Líquida do Setor Público (DLSP) consolidada (% do PIB).

---

## 8. Segurança Pública e Meio Ambiente

### 8.1 Atlas da Violência (IPEA / FBSP / SIM-DataSUS)
- **URL**: `https://www.ipea.gov.br/atlasviolencia/dados-series`
- **O que busca**: Taxa oficial de homicídios por 100 mil habitantes (série histórica consolidada de 1994 a 2023).

### 8.2 PRODES Amazônia (INPE / TerraBrasilis)
- **URL**: `http://terrabrasilis.dpi.inpe.br/app/dashboard/deforestation/biomes/legal_amazon/rates`
- **O que busca**: Taxa anual de desmatamento no bioma Amazônia Legal (em km² apurados de agosto a julho de cada ano).

---

## 9. Mercado Financeiro

### 9.1 B3 / Yahoo Finance API
- **URL**: `https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP`
- **O que busca**: Série histórica do Índice Bovespa (^BVSP), fechamento anual em pontos (1994 a 2025, e cotação parcial para 2026).
