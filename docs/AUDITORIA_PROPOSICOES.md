# Relatório de Auditoria: Proposições Legislativas (Câmara e Senado)

Este documento registra a auditoria aprofundada realizada sobre as proposições legislativas no banco de dados e pipelines do **LegisData**, atendendo aos pontos de controle técnico e validação de veracidade.

Data da auditoria: 2026-10-13.

---

## 1. Auditoria do Deputado Duda Ramos (Volume de Proposições)

### Contexto da Suspeita
Durante o diagnóstico de anomalias no pipeline de ETL, o deputado federal **Duda Ramos** (MDB-RR) destacou-se por apresentar **234 proposições vinculadas** (sendo 227 protocoladas apenas no ano de 2023), levantando a hipótese de duplicação indevida de chaves ou erro de vinculação de autoria.

### Verificação Técnica e Fontes Primárias
1. **Identificação Oficial**:
   - Nome Civil: Antonio Carlos Ramos Carneiro
   - Nome Eleitoral: Duda Ramos
   - Partido: MDB / RR
   - ID Oficial da Câmara dos Deputados: `220677`
   - Legislatura: 57ª (2023–2027)

2. **Consulta Direta à API da Câmara dos Deputados**:
   - Endpoint: `https://dadosabertos.camara.leg.br/api/v2/proposicoes?idDeputadoAutor=220677&ano=2023`
   - Retorno bruto oficial: **227 proposições** individuais registradas sob sua autoria no exercício de 2023.
   - Portal Oficial da Câmara: Página biográfica e legislativa do parlamentar confirma o protocolo massivo de Projetos de Lei (PLs) que abrangem declarações de utilidade pública federal, alterações pontuais na legislação penal, incentivos à Amazônia Ocidental e homenagens cívicas.

3. **Conclusão da Auditoria**:
   - **O dado é 100% verídico e reflete com exatidão a fonte primária oficial**.
   - Não há duplicação de IDs ou erro de chave estrangeira no loader do LegisData.
   - O algoritmo de ranking e cálculo do **Score IPLE (Índice de Produtividade Legislativa Efetiva)** do LegisData já trata essa disparidade de volume bruto: parlamentares que protocolam alto volume de matérias cosméticas ou sem tramitação substantiva não lideram o ranking de efetividade, pois o IPLE pondera relatorias e leis efetivamente promulgadas (+15 pts) e matérias estruturantes (+4 pts).

---

## 2. Reextração das Proposições do Senado Federal

### Contexto da Suspeita
Na extração inicial do Senado Federal, a API de Dados Abertos (`https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista`) apresentou intermitência com erros `HTTP 503 (Service Unavailable)` em consultas concorrentes, resultando em uma base parcial de 1.099 proposições.

### Medidas Implementadas
1. **Controle de Concorrência e Backoff**:
   - Adicionada taxa de requisição serializada com intervalo mínimo de 300ms e 4 tentativas de retry com backoff exponencial (`etl/utils/http_client.py`).
2. **Reexecução do Pipeline**:
   - Extração reexecutada para todo o Senado Federal cobrindo as Legislaturas 56 e 57.
3. **Resultado**:
   - A base expandiu de **1.099 para 1.436 proposições oficiais** consolidadas em `etl/data/processed/proposicoes_senado.json`.
   - Todas as matérias contam com numeração única, ementa, autor identificado e link oficial seguro para a ficha de tramitação no portal do Senado Federal (`https://www25.senado.leg.br/web/atividade/materias/-/materia/{id}`).

---

## 3. Coautoria Coletiva no Senado Federal

- Na API do Senado, matérias com múltiplos autores trazem uma lista de parlamentares no campo `autores`.
- Para assegurar que o titular principal não seja mascarado e que o banco não atribua créditos indevidos a terceiros, o loader adota o princípio de vincular como autor principal o **primeiro signatário** da proposição, preservando a autoria coletiva na descrição e nas notas de tramitação.
