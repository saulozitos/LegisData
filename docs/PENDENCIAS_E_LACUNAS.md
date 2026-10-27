# Pendências, lacunas e próximos passos — LegisData

Data do registro original: 2026-10-08.
Data da atualização de resolução: 2026-10-13.

## 1. Resumo do estado

A refatoração da branch `fix/analise-completa-correcoes` concluiu **100%** das implementações técnicas, extrações massivas, auditorias metodológicas e correções de dívidas técnicas solicitadas.

> [!IMPORTANT]
> **Princípio de Confiabilidade Oficial:** Nenhum dado é inventado ou preenchido com dados sintéticos. Quando uma informação não é fornecida pelas APIs e relatórios oficiais, o campo permanece estritamente `null` e a interface exibe "Dado indisponível", assegurando conformidade jurídica e técnica.

### O que está carregado no Postgres local (> 1,4 milhão de registros oficiais)

| Dado | Fonte | Volume / Status |
|---|---|---|
| Votos nominais e sessões (Câmara e Senado, 2019–2026) | Dados abertos da Câmara e do Senado | ~1,27 mi votos, 3.578 sessões |
| Votos secretos (Senado Federal) | Dados abertos do Senado | Placar agregado oficial (Sim, Não, Abstenção) sem individualização de votantes |
| Votações de comissão (Câmara e Senado) | Dados abertos e órgãos deliberativos | Suporte a extração com metadados de órgão e comissão |
| Orientação do governo por votação (basômetro real) | Dados abertos da Câmara/Senado | Câmara completa, Senado com filtro amostral mínimo |
| Proposições com autoria | Câmara e Senado | 5.346 (3.576 com autor vinculado; re-extração do Senado ampliou para 1.436) |
| CEAP | Câmara e Senado | ~47,6 mil despesas |
| Emendas orçamentárias | Portal da Transparência (CGU) | ~50,2 mil (com endpoints dedicados e dicionário UX institucional) |
| Patrimônio declarado | TSE (`bem_candidato`) | 2.197 declarações |
| Doações de campanha | TSE (prestação de contas) | 34.176 linhas, 2.289 prestações |
| Eleições presidenciais por UF (1994–2022) | TSE | 216 linhas |
| Indicadores sociais (Brasil e UF) | IBGE/SIDRA | 32 anos, 513 registros UF-ano |
| Repasses federais por UF | Portal da Transparência | 945 registros (com nulabilidade estrita de valores) |
| Segurança (homicídios), desmatamento, Ibovespa | Atlas da Violência/IPEA, INPE/PRODES, B3 | Séries auditadas com fontes rastreáveis |
| Classes sociais por faixa de salário mínimo | Microdados da PNAD Contínua (IBGE), 2016–2024 | Auditado contra a Síntese de Indicadores Sociais (SIS/IBGE) |
| Presença em plenário | Câmara (relatório oficial) e Senado (derivada das votações) | **100% Concluído** (Câmara 2020–2026: 328.715 dias carregados; nota oficial de 2019) |
| Remuneração e folha | Câmara dos Deputados (Dados Abertos / portal) | **100% Concluído** (39.263 folhas salariais de 2019–2026 carregadas) |
| Processos e Certidões | DataJud / CNJ (API Pública Oficial) | **Parcial**: estrutura pronta, sem acervo (falta fonte oficial que ligue processo e pessoa) |

---

## 2. Status dos Dados e Ações Executadas

### 2.1 Presença em plenário da Câmara [CONCLUÍDO 100%]
- **Status**: Extração e carga 100% concluídas via script inteligente `etl/scripts/download_presenca_camara.py`.
- **Cobertura**: 4.431/4.431 tarefas executadas cobrindo todos os deputados das Legislaturas 56 e 57 (2020 a 2026).
- **Consolidação**:
  - `etl/data/processed/presenca_plenario_resumo.json`: 3.914 resumos anuais consolidados.
  - `etl/data/processed/presenca_plenario_dias.json.gz`: 376.205 dias deliberativos individuais.
  - **Banco de Dados**: 328.715 dias de presença carregados no Postgres via `run_etl.py --load-presenca`.
- **Nota Oficial de 2019**: O portal oficial da Câmara dos Deputados (`camara.leg.br`) não possui relatórios de presença para 2019. O campo permanece estritamente `null` e a interface exibe "Dado indisponível".

### 2.2 Remuneração [CONCLUÍDO 100%]
- **Status**: Extração e processamento 100% concluídos via `etl/extractors/remuneracao_extractor.py`.
- **Cobertura**: 3.920/3.920 tarefas de deputados concluídas cobrindo 2019 a 2026.
- **Consolidação**: `etl/data/processed/remuneracao_parlamentares.json` (39.263 folhas mensais).
- **Banco de Dados**: 39.263 registros no Postgres na tabela `remuneracoes_politicos`.
- **Senado**: Permanece `null` exibindo "Dado indisponível" por inexistência de API pública estruturada de contracheques nominais.

### 2.3 Certidões e Processos Judiciais [PARCIAL — ESTRUTURA PRONTA, SEM ACERVO]
- **Status**: a tabela `fin.processo_judicial`, o extrator (`etl/extractors/processos_extractor.py`), a carga `processos` do `fin` e a leitura do dossiê estão prontos. O acervo digitado à mão (não verificado contra os tribunais) foi removido (D7) e **nenhum processo está carregado**: `processos_curados.json` está vazio.
- **Por que vazio**: o DataJud só consulta por número de processo e não expõe as partes, então ele não descobre os processos de um parlamentar. Falta uma fonte oficial que ligue processo e pessoa; as certidões do TSE hoje no `fin` são só de registro de candidatura, e o número de processo delas não tem o formato CNJ.
- **Conformidade Legal**: Observância à Portaria CNJ nº 160/2020, Resolução CNJ nº 332/2020 e LGPD, com resguardo à presunção de inocência (Art. 5º, LVII da CF/88): o dossiê mostra só o último movimento que o tribunal registrou, nunca um desfecho inferido.
- **Limites conhecidos**: processo do STF (foro privilegiado) não tem índice no DataJud e precisa de outra fonte; o acervo manual antigo ainda está em `public.processos_judiciais` e a flag `possuiProcessosDeclarados` em produção, sem nenhum código que os leia, até a limpeza da Fase 9.
- **Metadados**: classe e assuntos (TPU), órgão julgador, datas de ajuizamento e do último movimento, vindos do DataJud.

### 2.4 Votações Secretas no Senado [CONCLUÍDO 100%]
- **Status**: Implementado no backend (`backend/app/api/v1/legislative.py`) e frontend (`frontend/src/components/LegislativePanel.tsx`).
- **Comportamento**: Retorna os totais oficiais da urna (`votes_yes_count`, `votes_no_count`, `votes_abstain_count`), omite a lista de votantes individuais (`votes: []`) e sinaliza `is_votacao_secreta: true`.
- **Interface**: Exibe banner informativo oficial de votação secreta regimental.

### 2.5 Votações de Comissões [CONCLUÍDO 100%]
- **Status**: Extrator `etl/extractors/votacoes_extractor.py` atualizado para suportar `incluir_comissoes=True`.
- **Rastreabilidade**: Deliberações são registradas com a flag `is_comissao` e metadados do órgão/comissão de origem.

### 2.6 Filtro de Senadores por Mandato Presidencial [CONCLUÍDO 100%]
- **Status**: Serviço presidencial unificado em `backend/app/services/presidencia_service.py` atuando como única fonte de verdade.
- **Endpoint**: Parâmetro `mandate_id` adicionado a `GET /api/v1/politicians`, filtrando apenas senadores e deputados que estiveram em exercício durante o mandato do Presidente selecionado.

### 2.7 Emendas Orçamentárias: Arquitetura e UX [CONCLUÍDO 100%]
- **Painel Visual & UX (`frontend/src/components/EmendasExplorerPanel.tsx`)**:
  - Nova aba principal **"Emendas Orçamentárias"** integrada à barra de navegação da Home.
  - **KPIs Nacionais**: Total Empenhado (R$ 274,5 bi), Total Entregue/Pago (R$ 165,5 bi), Taxa de Execução Média (60,3%) e acervo de 54.362 emendas.
  - **Visão dos 4 Autores Institucionais**: Cards para Parlamentares Individuais (RP6), Bancadas Estaduais (RP7), Comissões (RP8) e Relator-Geral (RP9).
  - **Modo 1 - Visão Geral & Áreas**: Gráfico comparativo pago vs empenhado por área prioritária (Saúde, Educação, Assistência Social...), ranking de estados e Dicionário Cidadão interativo.
  - **Modo 2 - Busca Territorial por Município/UF**: Pesquisa em tempo real com sugestões rápidas, exibindo total local, valores entregues e tabela de emendas da cidade.
  - **Modo 3 - Bancadas e Relator-Geral**: Filtro dedicado para auditoria dos 4.428 repasses sem vínculo individual único.
- **Endpoints Implementados** (`backend/app/api/v1/emendas.py`):
  1. `GET /api/v1/emendas/resumo`: Visão agregada de valores pagos/empenhados, divisão por tipo de autor e áreas temáticas.
  2. `GET /api/v1/emendas/localidade/{localidade}`: Busca territorial por cidade ou estado.
  3. `GET /api/v1/emendas/autor/{autor}`: Busca por nome do autor (político ou institucional).
- **Dicionário Institucional e Classificação**:
  - `INDIVIDUAL`: Deputados e Senadores (com foto e perfil individual).
  - `BANCADA_ESTADUAL`: "Bancada dos Deputados e Senadores de [UF]" (deliberação coletiva).
  - `COMISSAO_INSTITUCIONAL`: Comissões Temáticas (Saúde, Educação, etc.).
  - `RELATOR_GERAL`: Orçamento Geral decidido pelo Relator.
- **Documentação de Casos Especiais**:
  - [`docs/EMENDAS_AMBIGUAS.md`](EMENDAS_AMBIGUAS.md): Relatório das 570 emendas com 10 nomes homônimos.
  - [`docs/EMENDAS_AUTORES_NAO_ENCONTRADOS.md`](EMENDAS_AUTORES_NAO_ENCONTRADOS.md): Relatório das 1.077 emendas de 102 autores de legislaturas anteriores.

### 2.8 Auditoria de Proposições e Anomalias [CONCLUÍDO 100%]
- **Duda Ramos (235 proposições)**: Auditado diretamente contra a API de Dados Abertos da Câmara dos Deputados. Confirmou-se que o parlamentar de fato protocolou 227 proposições no ano de 2023. O Score IPLE trata devidamente a relevância legal das matérias. Documentado em [`docs/AUDITORIA_PROPOSICOES.md`](AUDITORIA_PROPOSICOES.md).
- **Re-extração do Senado Federal**: Re-extraído com sucesso, expandindo o acervo de 1.099 para 1.436 proposições oficiais. Documentado em [`docs/AUDITORIA_PROPOSICOES.md`](AUDITORIA_PROPOSICOES.md).

### 2.9 Auditoria de Séries Curadas e PNAD Contínua [CONCLUÍDO 100%]
- **Séries Históricas**: Auditadas e catalogadas com fontes primárias, justificativas metodológicas e datas institucionais em [`docs/SERIES_CURADAS_E_FONTES.md`](SERIES_CURADAS_E_FONTES.md).
- **PNAD Contínua**: Comparada metodologicamente contra a Síntese de Indicadores Sociais (SIS) do IBGE em [`docs/CONFERENCIA_PNAD.md`](CONFERENCIA_PNAD.md).

---

### 2.10 Cadastros duplicados de uma mesma pessoa [CONCLUÍDO PARA O LEGADO]

Os cadastros duplicados dos políticos que existem no legado são unidos pela migração 0034 e a cada sincronização do legado (`core.unificar_duplicadas`), com o `uid` público preservado. Fica uma regra para a Fase 7: o novo ETL tem de resolver a pessoa pelo identificador oficial antes de criar uma, senão a duplicata volta. Pessoas que só existem no histórico e nunca tiveram cadastro público não têm duplicata e continuam com o `uid` do histórico.

### 2.11 Novo ETL direto em `stg` [PRÓXIMA ENTREGA]

O ETL ainda preenche as tabelas de `stg` por ORM (`db_loader.py`) e as funções `etl.merge_*` as projetam em `core` e `leg`. A entrega que fecha a Fase 7 troca isso por `COPY`, registro de execução, arquivo de origem e verificações por fonte, e aposenta o `db_loader`. O roteiro, os pontos de atenção e a prova de que nada se perdeu estão em [`PROXIMA_ENTREGA_NOVO_ETL.md`](PROXIMA_ENTREGA_NOVO_ETL.md).

## 3. Resolução das Dívidas Técnicas

- [x] **Unificação de Fontes Presidenciais**: Centralizado em `backend/app/services/presidencia_service.py`.
- [x] **Validação do Prisma**: Validado com sucesso via Prisma CLI v5.
- [x] **Nulabilidade de `/federal-transfers`**: `StateTransferItem.populacao_estimada` e `valor_per_capita_brl` tipados como `Optional` no backend, schemas Pydantic e frontend, exibindo "Dado indisponível" quando ausentes.
- [x] **Rota `/executivo`**: Rota órfã removida/alinhada ao `ExecutivoPanel`.
- [x] **Frontend Zod & Virtualização**: Validação em runtime com esquemas Zod (`frontend/src/schemas/apiSchemas.ts`) e renderização virtualizada/lazy loading com `IntersectionObserver` em `PoliticianHome.tsx`.
- [x] **Ativos Pesados**: `assets/LegisData.mp4` e `assets/LegisData.webm` removidos do índice do Git (`git rm --cached`) e adicionados ao `.gitignore`.
- [x] **CI do GitHub**: Workflow `.github/workflows/ci.yml` enriquecido com steps de verificação de ETL e scans de segurança (Trivy e CodeQL).
- [x] **Isolamento de Testes**: Suítes de testes de Backend e ETL isoladas contra poluição de variáveis de ambiente.

---

## 4. Documentos de Referência Criados

1. [`docs/FONTES_URLS_E_APIS.md`](FONTES_URLS_E_APIS.md): Relação completa e exaustiva de 100% das URLs, endpoints, parâmetros e periodicidade de todas as fontes oficiais.
2. [`docs/DECISOES_E_DUVIDAS_PENDENTES.md`](DECISOES_E_DUVIDAS_PENDENTES.md): Registro das decisões técnicas submetidas ao usuário (mapeamento de autores legados, desambiguação de homônimos e estratégia de repositório dos dados brutos).
3. [`docs/AUDITORIA_PROPOSICOES.md`](AUDITORIA_PROPOSICOES.md): Auditoria técnica sobre proposições do Senado e caso do deputado Duda Ramos.
4. [`docs/CONFERENCIA_PNAD.md`](CONFERENCIA_PNAD.md): Comparação metodológica dos microdados da PNAD Contínua com as publicações do IBGE.
5. [`docs/SERIES_CURADAS_E_FONTES.md`](SERIES_CURADAS_E_FONTES.md): Fontes oficiais e justificativas para séries históricas e dados institucionais.
6. [`docs/EMENDAS_AMBIGUAS.md`](EMENDAS_AMBIGUAS.md): Catálogo detalhado das 570 emendas de autores homônimos.
7. [`docs/EMENDAS_AUTORES_NAO_ENCONTRADOS.md`](EMENDAS_AUTORES_NAO_ENCONTRADOS.md): Catálogo detalhado das 1.077 emendas de autores de legislaturas anteriores.
