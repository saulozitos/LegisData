# Pendências e lacunas de dados — LegisData

Documento de passagem de contexto. Registra o estado do projeto ao final da refatoração
da branch `fix/analise-completa-correcoes`, o que ainda falta e como retomar em outra máquina.

Data do registro: 2026-10-08.

## 1. Resumo do estado

A branch aplica as correções da análise completa (backend, ETL, frontend, infra/CI e testes) e
troca dados fabricados por dados de fontes oficiais. O CI local (`scripts/local_ci.sh`) passou
inteiro, o ETL tem testes próprios e o banco local foi populado com dados reais.

Princípio adotado: **nenhum dado é inventado**. Quando não há fonte oficial verificável, o campo fica
`null` e a interface mostra "Dado indisponível".

### O que está carregado no Postgres local (1,4 milhão de registros)

| Dado | Fonte | Volume |
|---|---|---|
| Votos nominais e sessões (Câmara e Senado, 2019–2026) | Dados abertos da Câmara e do Senado | ~1,27 mi votos, 3.578 sessões |
| Orientação do governo por votação (basômetro real) | Dados abertos da Câmara/Senado | Câmara completa, Senado parcial |
| Proposições com autoria | Câmara e Senado | 5.346 (3.576 com autor vinculado) |
| CEAP | Câmara e Senado | ~47,6 mil despesas |
| Emendas parlamentares | Portal da Transparência | ~50,2 mil |
| Patrimônio declarado | TSE (`bem_candidato`) | 2.197 declarações |
| Doações de campanha | TSE (prestação de contas) | 34.176 linhas, 2.289 prestações |
| Eleições presidenciais por UF (1994–2022) | TSE | 216 linhas |
| Indicadores sociais (Brasil e UF) | IBGE/SIDRA | 32 anos, 513 registros UF-ano |
| Repasses federais por UF | Portal da Transparência | 945 registros |
| Segurança (homicídios), desmatamento, Ibovespa | Atlas da Violência/IPEA, INPE/PRODES, Yahoo/B3 | séries anuais |
| Classes sociais por faixa de salário mínimo | Microdados da PNAD Contínua (IBGE), 2016–2024 | arquivo JSON |
| Presença em plenário | Câmara (relatório oficial) e Senado (derivada das votações) | Senado completo, Câmara ~3% |

## 2. Dados que ainda faltam

### 2.1 Presença em plenário da Câmara (parcial)

- O portal da Câmara limita a ~3–4 páginas por minuto (HTTP 429). A extração completa leva
  em torno de 15 horas (3.588 páginas deputado × ano).
- Estado ao parar: cerca de 6 diretórios/arquivos de deputados em cache (`etl/data/raw/presenca/camara`).
  O Senado está completo (2019–2026, 153 senadores).
- A extração é **retomável**: o cache fica em `etl/data/raw/presenca/`. O processo em segundo plano foi
  interrompido de propósito antes da cópia para o HD externo.
- Para retomar e carregar:
  ```bash
  PYTHONPATH=backend:. python -m etl.extractors.presenca_extractor --so-camara --intervalo 7
  PYTHONPATH=backend:. python etl/run_etl.py --presenca --load-presenca
  ```
- O portal só publica presença de 2020 em diante; 2019 retorna "Não há dados".
- Presenças anteriores a 2023 de parlamentares sem mandato cadastrado na época usam o mandato mais
  próximo (o loader reporta o total em `mandato_aproximado`, ~11,8 mil no último carregamento).

### 2.2 Remuneração (não carregada)

- Câmara: extrator existe (`etl/extractors/remuneracao_extractor.py`), validado com 2 deputados, mas
  **o universo completo não foi extraído** e compete pela mesma cota de requisições do portal.
  A carga avisou "arquivo ausente: remuneracao_parlamentares.json". Rodar `--remuneracao` e depois
  `--load-presenca`.
- Senado: não há fonte estruturada (só consulta em HTML por servidor). Fica `null`.
- O líquido só é coletado para o mês mais recente. O acumulado usa o subsídio bruto.

### 2.3 Dados sem fonte aberta automatizável

- **Certidões de "nada consta" e processos judiciais:** exigem chave do DataJud/CNJ. Hoje só existem
  4 registros de candidaturas adversas vindos do TSE (indeferidas, canceladas ou cassadas). O status
  geral da ficha continua `null` ("desconhecido"). O acervo manual de processos
  (`etl/extractors/processos_loader.py`) permanece desligado, porque os dados são digitados e não
  verificáveis (exige `--allow-unverified-legal`).
- **Feminicídio:** `null` em todos os anos (não há fonte aberta automatizável; os valores antigos eram digitados).
- **Bens de 2002:** o TSE não publica `bem_candidato_2002`.
- **Eleição presidencial de 1989:** não existe nos dados abertos do TSE e não é estimada.
- **Votos do exterior (UF "ZZ"):** não entram na tabela por UF.
- **Eleições municipais 2020/2024 e prestação de contas 2024:** não carregadas (arquivos > 1 GB, fora dos cargos do projeto).
  O patrimônio de 2024 foi incluído.
- **Ipeadata não respondeu** do ambiente de desenvolvimento. Por isso a pobreza antes de 2012 e o
  analfabetismo antes de 2016 não têm série. Insegurança alimentar de 2009, 2013 e 2017-18 não tem série no SIDRA.
  Os valores da Rede PENSSAN (2020 e 2022) ficam em campos próprios, nunca misturados à série do IBGE.

### 2.4 Cobertura limitada dentro do que foi carregado

- **Orientação do governo no Senado:** só 147 de 534 sessões trazem orientação SIM/NÃO. O basômetro do
  Senado tem amostra baixa. Votos secretos não têm voto individual.
- **Votações de comissão:** não foram extraídas, só plenário.
- **Suplentes de senado** que nunca votaram não entram.
- **Datas de mandato de senador** são as do mandato, não do período de exercício.
- **Emendas sem vínculo (4.428 de 54.362):**
  - 2.781 institucionais (R$ 104 bi): "Relator-Geral" e bancadas estaduais, que não são pessoas.
  - 570 ambíguas (10 nomes homônimos, como "Rodrigo Pacheco" e "Atila Lira"): o loader recusa por regra.
  - 1.077 de 102 autores não encontrados na base (provável grafia diferente ou legislatura anterior à 55).
  - Diagnóstico: `etl/scripts/diagnose_emendas.py`.
- Um parlamentar de teste apresentou R$ 197 milhões em emendas empenhadas (19 emendas); vale auditar se o loader
  não atribui emendas de bancada ou de comissão ao autor.
- Um deputado (Duda Ramos) tem 235 proposições vinculadas, e o nome do autor na API é exatamente esse.
  Parece dado real, mas vale auditar com `etl/scripts/diagnose_anomalies.py`.
- A API do Senado respondeu HTTP 503 em parte das consultas de proposições durante a extração; o total
  extraído foi 1.099. Vale reexecutar `--senado` e comparar.

### 2.5 Séries ainda curadas à mão (rotuladas, não verificadas)

- Bancadas base/oposição e presidentes das Casas (`composicao_extractor.py`). A verificação contra o TSE mostra
  divergências em quase todos os mandatos por causa de trocas partidárias, e o Senado de 1995 não é verificável
  (1990 não está nos dados abertos). Cada mandato traz uma `nota`. Os totais de eleitos do TSE da Câmara de 1999 (516)
  e da legislatura de 2007 não fecham.
- Lemas e ideologia de partidos, `NOMADES_HISTORICO`, posses, vices e ministros.
- Data de posse de Temer (31/08/2016) é decisão editorial.
- Ibovespa de 2026 é parcial (sem fechamento). Desemprego usa a média dos 4 trimestres (2023: 8,0% contra 7,8% divulgado).
- Taxa de homicídios calculada com a população implícita nas séries do Atlas (22,0 contra 21,7 divulgados).
- `IBGEExtractor` não é chamado por nenhum pipeline.

### 2.6 PNAD — conferir antes de divulgar

- Classes e faixas de salário mínimo vêm dos microdados da PNAD Contínua (visita 5, 2016–2024).
  **Não foram comparadas com as tabelas publicadas pelo IBGE** (Síntese de Indicadores Sociais).
  Conferir sobretudo a renda per capita.
- O peso domiciliar é aproximado pelo peso do responsável (V2005 = "01"), porque o IBGE não publica peso domiciliar.
- Valores nominais: compare entre anos só em salários mínimos.

## 3. Dívidas técnicas e riscos conhecidos

- **Stack completa do Docker não foi exercitada.** O build das imagens falhou no ambiente de desenvolvimento
  porque a rede do container intercepta TLS (certificado autoassinado) e o `pip` não alcança o PyPI. Só o Postgres
  rodou em container; backend e frontend rodaram na máquina. Falta validar o `docker compose up --build`
  (imagens, healthchecks, `DB_SSLMODE`, rewrite `/api/health`) em uma rede sem interceptação, e a carga
  contra o Postgres do compose.
- **Nada foi testado contra Postgres** nos testes automatizados (backend e ETL usam SQLite em memória). A carga real rodou
  contra o Postgres local, mas o comportamento de `ON CONFLICT`/DDL deve ser conferido em CI com Postgres real.
- **Rate limit** é em memória, por worker. Para limite distribuído, aplicar no proxy/WAF. O cooldown de `force_refresh` também é por worker.
- **Três fontes de verdade para presidentes** (`PresidentialMandate`, `Mandate` PRESIDENTE e o JSON) ainda não foram unificadas.
- **Prisma:** `database/schema.prisma` foi alinhado aos models, mas não foi validado com o Prisma CLI e não há migrações Alembic.
- **`/federal-transfers`** ainda coage população ausente para 0, e o tipo `StateTransferItem` não é anulável.
- **`/executivo`** continua como rota órfã que duplica o `ExecutivoPanel`.
- **Frontend:** não há validação de resposta em runtime (zod/OpenAPI) nem virtualização do catálogo de políticos
  (renderização incremental).
- **Arquivos legados ainda no repositório**, sem campo `fonte` e recusados pelos loaders, mantidos por compatibilidade:
  `proposicoes_2023.json`, `proposicoes_senado.json`, `votos_nominais_*.json`, `sessoes_votacao_*.json`,
  `deputados_camara.json`, `senadores_senado.json`, `resultados_eleicoes_presidenciais_uf.*` (digitado à mão),
  `salario_vs_inflacao.json`. Podem ser removidos quando os extratores oficiais substituírem todos.
- **CI do GitHub:** não foram adicionados Trivy nem CodeQL (não foi possível obter SHAs confiáveis das actions). O ETL
  não roda no workflow `ci.yml`; só no local. Falta configurar no GitHub: secrets `DEPLOY_HOST`,
  `DEPLOY_HOST_FINGERPRINT`, o ambiente `production` com revisores e o Private Vulnerability Reporting.
- **`SECURITY.md`:** o e-mail de contato é pessoal e tem um TODO para o mantenedor confirmar.
- **Ativos pesados:** `assets/LegisData.mp4` e `.webm` (~61 MB) e dados grandes estão no repositório. Mover para
  Releases ou Git LFS.
- Os testes do backend e do ETL no mesmo `pytest` podem falhar por poluição de variáveis de ambiente; rode os dois separados.

## 4. Como retomar em outra máquina

### 4.1 O que copiar para o HD externo

O git **não** guarda os dados brutos baixados (ficam no `.gitignore`). Para levar tudo, copie a pasta inteira do
repositório (incluindo ocultos), não só um `git clone`:

| Caminho | Tamanho aprox. | No git? |
|---|---|---|
| `etl/data/raw/tse` | 3,1 GB | não |
| `etl/data/raw/pnad` | 1,6 GB | não |
| `etl/data/raw/votacoes` | 704 MB | não |
| `etl/data/raw/transferencias` | 492 MB | não |
| `etl/data/raw/presenca` | 7 MB (cache retomável) | não |
| `etl/data/raw/{sidra,atlas_violencia,yahoo,*.json}` | poucos MB | não |
| `etl/data/processed/*` | 44 MB | sim |
| `.env` (senha do Postgres local) | pequeno | **não, nunca commitar** |

Total de brutos: ~5,8 GB. O volume do Postgres (Docker) não está no repositório; para levar o banco, recarregue com
`python etl/run_etl.py --load-db --load-presenca` ou faça `pg_dump` do container `politica_postgres`.

### 4.2 Ambiente

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt \
            -r etl/requirements.txt -r etl/requirements-dev.txt -r scripts/requirements-ci-tools.txt
(cd frontend && npm ci)
cp .env.example .env   # e troque os CHANGE_ME por segredos fortes
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres
```

### 4.3 Validar

```bash
bash scripts/local_ci.sh                        # backend, frontend, lint, tipos, segurança, build
PYTHONPATH=backend:. pytest -q etl/tests        # ETL (rodar separado do backend)
```

### 4.4 Carregar e subir

```bash
PYTHONPATH=backend:. python etl/run_etl.py --load-db --load-presenca
cd backend && ENVIRONMENT=development DB_SSLMODE=disable uvicorn app.main:app --port 8000
cd frontend && INTERNAL_BACKEND_URL=http://127.0.0.1:8000 npm run dev
```

O primeiro start da API aplica o DDL de startup (colunas novas). Suba a API antes de rodar o `--load-db`
em um banco já existente.

### 4.5 Reextrair do zero (opcional, demorado)

Etapas do `run_etl.py`: `--economic --camara --senado --tse --patrimonio --doacoes --eleicoes --candidaturas
--social --orcamento --composicao --renda --ceap --pnad --votacoes --presenca --remuneracao`. Use `--no-cache`
para ignorar caches. Fontes e métodos estão em `etl/FONTES_OFICIAIS.md` e no `README.md`.

## 5. Ordem sugerida do que fazer a seguir

1. Terminar a presença da Câmara e a remuneração (execução longa, retomável) e recarregar.
2. Conferir a PNAD contra as tabelas do IBGE.
3. Auditar as emendas (valores altos por parlamentar e as 4.428 sem vínculo).
4. Validar `docker compose up --build` e a carga em Postgres real, inclusive no CI.
5. Obter chave do DataJud/CNJ se certidões e processos forem requisito do produto.
6. Substituir as séries curadas (bancadas, lemas, `NOMADES_HISTORICO`) por fontes oficiais ou rotular com fonte.
7. Remover os arquivos legados sem `fonte` e os ativos pesados do repositório.
