# LegisData

> **Plataforma Open-Source de Transparência, Inteligência Política e Cidadania Ativa**
>
> Arsenal cívico e de auditoria pública que cruza macroeconomia, indicadores socioambientais, votações nominais, financiadores de campanha (TSE), custos de gabinete (CEAP), emendas orçamentárias, o Basômetro governista, linha do tempo dos mandatos presidenciais (1992 - Presente) e a relevância real das proposições legislativas — **com participação popular direta em consultas públicas ao vivo do Congresso Nacional**.

[![CI Quality Gate](https://github.com/saulozitos/LegisData/actions/workflows/ci.yml/badge.svg)](https://github.com/saulozitos/LegisData/actions/workflows/ci.yml)
[![Security Policy](https://img.shields.io/badge/Security-Policy-brightgreen?style=for-the-badge&logo=shield)](SECURITY.md)
[![Frontend](https://img.shields.io/badge/Frontend-Next.js%2016%20%7C%20TypeScript%20%7C%20Tailwind-black?style=for-the-badge&logo=next.js)](https://nextjs.org/)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Python%203.11-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Database](https://img.shields.io/badge/Database-PostgreSQL%2016-336791?style=for-the-badge&logo=postgresql)](https://www.postgresql.org/)
[![Data Engine](https://img.shields.io/badge/ETL-Pandas%20%7C%20NumPy-150458?style=for-the-badge&logo=pandas)](https://pandas.pydata.org/)
[![Containers](https://img.shields.io/badge/Containers-Docker%20Non--Root-2496ED?style=for-the-badge&logo=docker)](https://www.docker.com/)
[![Licença](https://img.shields.io/badge/Licen%C3%A7a-GNU%20AGPLv3-blue.svg?style=for-the-badge)](LICENSE)

---

## 💡 Sobre o Desenvolvimento & Metodologia

> ### 🤖 Nota de Desenvolvimento (Vibe Coding)
> **Este projeto foi idealizado e arquitetado por mim, mas seu código-fonte foi integralmente desenvolvido através da metodologia de *Vibe Coding* (programação assistida por Inteligência Artificial / LLMs). A stack tecnológica utilizada (Python, FastAPI, Next.js, PostgreSQL) não faz parte do meu domínio principal. Meu foco foi a engenharia de prompts, visão do produto de dados, regras de negócio e arquitetura da informação para criar uma plataforma robusta de transparência pública.**
>
> *Autor: Saulo Araujo Campos • Licenciado sob GNU AGPLv3*

---

## 📺 Demonstração da Plataforma

<p align="center">
  <a href="assets/LegisData.mp4" title="Clique para assistir ao tour completo de 6 minutos em alta resolução">
    <img src="assets/preview.gif" alt="Demonstração da Plataforma LegisData" width="100%" />
  </a>
  <br>
  <em>▶️ <b>Demonstração da plataforma em execução:</b> clique na animação acima para assistir ao tour completo em alta definição (<a href="assets/LegisData.mp4">Versão MP4</a> | <a href="assets/LegisData.webm">Versão WebM</a>).</em>
</p>

---

## 🎯 1. Propósito e Arsenal Cívico

O **LegisData** foi concebido como uma resposta técnica, visual e independente à polarização vazia e à desinformação no debate público brasileiro. Em vez de narrativas sem lastro empírico, a plataforma centraliza **dados abertos oficiais** de múltiplos órgãos de Estado para responder com rigor às principais perguntas do cidadão:

1. **Quem Paga a Conta? (Financiamento Eleitoral):** De onde veio o dinheiro que elegeu o parlamentar? Quais foram seus maiores doadores (partidos, fundos públicos e pessoas físicas)?
2. **O Basômetro (Adesão ao Governo):** O parlamentar vota alinhado com a base governista ou faz oposição sistemática nas matérias de interesse do Palácio do Planalto?
3. **Detector de Leis Inúteis (Taxa de Relevância):** O congressista atua em reformas econômicas e políticas públicas estruturais ou concentra o mandato em homenagens, títulos honorários e datas comemorativas?
4. **Custo do Mandato (Cota Parlamentar - CEAP):** Quanto o gabinete gasta em passagens aéreas, divulgação e locações, e quais empresas mais faturam com esses reembolsos?
5. **A Trilha do Dinheiro (Emendas Orçamentárias):** Para onde vão as emendas individuais, de bancada e Emendas PIX do parlamentar?
6. **Raio-X Judicial & Ficha Limpa:** Auditoria de certidões cíveis e criminais do TSE, STF e tribunais estaduais à luz da Lei Complementar nº 135/2010.
7. **Macropolítica e Indicadores Reais:** Cruzamento histórico da atuação política com PIB real, inflação (IPCA), taxa Selic, câmbio USD, salário mínimo, desigualdade (Gini), fome, desmatamento (INPE) e taxas de violência (IPEA/FBSP).
8. **Linha do Tempo Presidencial (1992 - Presente):** Raio-X comparativo dinâmico de todos os mandatos presidenciais com métricas fiscais, monetárias e sociais ano a ano.
9. **Cidadania Ativa & Votação Direta:** O cidadão não apenas fiscaliza o passado, mas intervém no presente. A plataforma lista consultas públicas e enquetes oficiais em tramitação em tempo real no Congresso Nacional (e-Cidadania e e-Democracia), permitindo votar e registrar sua posição oficial diretamente nas instâncias legislativas.

---

## 🏛️ 2. Fontes Abertas Oficiais

Todos os dados são coletados de forma rastreável por extratores dedicados (`User-Agent: LegisDataBot/1.0`), estritamente fundamentados na **Lei de Acesso à Informação (Lei nº 12.527/2011)**:

| Órgão / Instituição | Dados Coletados | Endpoint / Repositório Oficial |
| :--- | :--- | :--- |
| **TSE (Justiça Eleitoral)** | Prestações de contas eleitorais, doações de campanha, certidões judiciais e declarações de bens | Portal Dados Abertos TSE & DivulgaCandContas |
| **Câmara dos Deputados** | Deputados, mandatos, presenças, votos nominais, proposições e despesas da cota parlamentar (CEAP) | `dadosabertos.camara.leg.br/api/v2` |
| **Senado Federal** | Senadores, proposições legislativas, sessões deliberativas e cota parlamentar | `legis.senado.leg.br/dadosabertos` |
| **Banco Central do Brasil (BCB)** | Séries temporais de IPCA, taxa Selic, Câmbio USD PTAX e Dívida Líquida/PIB | Sistema Gerenciador de Séries Temporais (SGS) |
| **IBGE** | Contas Nacionais (PIB real), séries demográficas e desemprego (PNAD Contínua) | Banco de Dados SIDRA / Agregados API |
| **IBGE (microdados)** | Classes sociais por faixas de salário mínimo, calculadas dos microdados anuais da PNAD Contínua (visita 5, 2016 em diante) com o peso amostral calibrado | `ftp.ibge.gov.br/.../Pesquisa_Nacional_por_Amostra_de_Domicilios_continua/Anual/Microdados/` |
| **INPE** | Desmatamento anual consolidado na Amazônia Legal e Cerrado | Projeto PRODES / Plataforma TerraBrasilis |
| **IPEA & FBSP** | Séries históricas de segurança pública, taxas de homicídio e feminicídio | IpeaData & Fórum Brasileiro de Segurança Pública |

---

## 🔒 3. Segurança, Infraestrutura e Conformidade

A infraestrutura e o pipeline de CI/CD do LegisData foram endurecidos contra ameaças cibernéticas e auditorias de conformidade:

- **Isolamento de Rede:** no `docker-compose.yml` de produção, PostgreSQL e backend **não publicam portas no host**; a comunicação ocorre pela rede interna do Compose. O frontend escuta apenas em `127.0.0.1:3000` e deve ser exposto por um proxy reverso que termine TLS e envie HSTS. Para desenvolvimento, `docker-compose.dev.yml` publica Postgres (`5432`) e API (`8000`) somente em loopback (`make up-db` / `make docker-up`).
- **Fail-Fast de Credenciais:** a aplicação recusa iniciar sem uma senha de banco explícita configurada no ambiente. O `.env.example` traz apenas `CHANGE_ME`. O modo SSL do banco é configurável (`DB_SSLMODE`; `disable` no Postgres interno do Compose, `require` para bancos gerenciados).
- **Contêineres Endurecidos:** backend e frontend executam sob usuário não-privilegiado (`appuser`), com `no-new-privileges`, `cap_drop: ALL`, healthchecks e limites de recursos. O Postgres usa a imagem oficial (inicializa como root e depois roda como `postgres`) e também recebe `no-new-privileges`. Imagens fixadas em tag minor; o Dependabot propõe as atualizações.
- **Proteção contra Vazamento:** arquivos `.dockerignore` na raiz e nos subprojetos garantem que segredos (`.env`), chaves e arquivos temporários não entrem nas camadas das imagens.
- **CI/CD Endurecido (GitHub Actions):**
  - Runner em nuvem isolado (`ubuntu-latest`), sem runners `self-hosted`, e sem `pull_request_target`.
  - Privilégio mínimo (`permissions: { contents: read }`), `timeout-minutes` em todos os jobs e actions fixadas por SHA.
  - Deploy só dispara **após o CI concluir com sucesso na `main`**, usa o ambiente protegido `production` (configure revisores obrigatórios nas Settings do GitHub), `concurrency` sem sobreposição, verifica o fingerprint do host SSH (secret `DEPLOY_HOST_FINGERPRINT`) e implanta o SHA exato validado.
  - Auditoria de dependências (`pip-audit`, `npm audit --omit=dev`), `bandit`, `mypy` e gate de cobertura com branches. O CI local (`make ci` / `scripts/local_ci.sh`) executa as mesmas etapas. Dependabot configurado para pip, npm, Docker e Actions.
- **Limitação a clientes (rate limit):** a API aplica limite por IP em memória (`RATE_LIMIT_PER_MINUTE`, resposta 429), **por worker**; o `force_refresh` de `/cidadania/consultas` exige o header `X-Admin-Token`. Para um limite distribuído, aplique também limites no proxy reverso/WAF.
- **Divulgação Responsável:** política formal em [SECURITY.md](SECURITY.md). Habilitar o *Private Vulnerability Reporting* é uma configuração do GitHub que não é verificável pelo repositório: confirme em Settings → Security.

### ⚠️ Ações manuais pendentes (fora do código)

- Configurar os secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_DIR` e **`DEPLOY_HOST_FINGERPRINT`**, e criar o ambiente `production` com revisores obrigatórios.
- Usar uma chave SSH dedicada ao deploy, com `command=` restrito no `authorized_keys` do servidor.
- Os vídeos `assets/LegisData.mp4` e `assets/LegisData.webm` (~60 MB) e os dados em `etl/data/` (ex.: `emendas_parlamentares_2019_2026.json`, ~35 MB, e `raw/` duplicados por data) pesam no clone: mover para GitHub Releases ou Git LFS (não foram removidos aqui para não quebrar referências).
- Confirmar o e-mail de contato em `SECURITY.md` e o *Private Vulnerability Reporting*.
- Pin por digest (`@sha256:`) das imagens base, se desejado, via Dependabot/Renovate.

---

## 🛠️ 4. Stack Tecnológica

- **Frontend:**
  - **Next.js 16 (App Router & Turbopack)** com TypeScript rigoroso.
  - **Tailwind CSS v4** com design system HSL escuro e alta fidelidade visual.
  - **Recharts 3.10** para gráficos de pizza, barras, séries temporais e comparadores.
  - **Lucide React** para iconografia técnica.
- **Backend:**
  - **Python 3.11+** com **FastAPI** assíncrono.
  - **Pydantic v2** com `pydantic-settings` para validação estrita de contratos.
  - **SQLAlchemy 2.0** com connection pooling resiliente.
  - **Gunicorn & Uvicorn Workers** em produção.
- **Banco de Dados:**
  - **PostgreSQL 16** com mais de 23.000 registros relacionais e índices de concorrência.
- **Qualidade & DevOps:**
  - **Docker Compose** para orquestração segura.
  - **Linters & Formatters:** `black`, `isort`, `flake8`, `mypy`, `eslint`.
  - **Segurança:** `bandit`, `pip-audit`, `npm audit`.
  - **Testes Automatizados:** `pytest` (backend) e `vitest` (frontend).

---

## 🚀 5. Instalação e Execução Local

### Pré-requisitos
- **Git**
- **Docker** e **Docker Compose**
- **Python 3.11+**
- **Node.js 22+**

### Passo 1: Clonar o Repositório e Configurar o `.env`
```bash
git clone https://github.com/saulozitos/LegisData.git
cd LegisData

# Copie o arquivo de exemplo e defina uma senha forte
cp .env.example .env
```

Edite o `.env` garantindo que a variável `POSTGRES_PASSWORD` esteja preenchida:
```env
POSTGRES_USER=politica_user
POSTGRES_PASSWORD=sua_senha_secreta_aqui
POSTGRES_DB=politica_db
POSTGRES_PORT=5432
POSTGRES_SERVER=localhost
ENVIRONMENT=development
```

### Passo 2: Subir o PostgreSQL Local via Docker
```bash
make up-db
```
*(Ou diretamente: `docker compose up -d postgres`)*

### Passo 3: Configurar o Ambiente Virtual Python
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### Passo 4: Executar a Carga Inicial do Banco de Dados
```bash
make run-load-db
```
*O pipeline executará as migrações, ingerindo séries históricas, parlamentares, cota CEAP, emendas, processos e doações do TSE.*

Etapas de extração independentes (cada uma grava só se a validação passar): `python etl/run_etl.py --ceap` (CEAP e emendas oficiais) e `python etl/run_etl.py --pnad` (baixa ~1,5 GB de microdados da PNAD Contínua para `etl/data/raw/pnad/`, ignorado pelo Git, e gera `etl/data/processed/pnad_faixas_salario_minimo.json`, consumido por `/api/v1/analytics/social-classes`).

Dados do TSE (dados abertos em `cdn.tse.jus.br`; os zips brutos, de ~2 GB no total, ficam em `etl/data/raw/tse/`, ignorado pelo Git): `--patrimonio` (bens declarados, `bem_candidato`, 2006–2024), `--doacoes` (receitas de campanha, `prestacao_contas`, 2002–2022; os 20 maiores doadores por candidato e uma linha "Demais doadores"; CPF de pessoa física gravado mascarado), `--eleicoes` (resultados presidenciais por UF, 1994–2022, turno decisivo, a partir de `votacao_candidato_munzona`) e `--candidaturas` (registros de candidatura indeferidos/cancelados/cassados, `consulta_cand`). O vínculo candidato→político usa CPF e data de nascimento obtidos das APIs oficiais da Câmara e do Senado (cache em `etl/data/raw/identidades_parlamentares.json`, nunca versionado) e nome EXATO; homônimos ambíguos são descartados. Lacunas conhecidas: não há bens declarados de 2002 nem resultados de 1989 nos dados abertos do TSE, e não há fonte aberta unificada de processos judiciais (o DataJud/CNJ exige chave); sem dado, a tela mostra "Dado indisponível".

Votações: `python etl/run_etl.py --votacoes` baixa os arquivos anuais de votações da Câmara (2019 em diante, cache em `etl/data/raw/votacoes/`, ignorado pelo Git) e as votações nominais do Senado, com a orientação da bancada do **Governo** em cada votação, e grava `etl/data/processed/votacoes/{camara,senado}_AAAA.json.gz` mais `parlamentares_legislaturas_anteriores.json` (ex-parlamentares, para vincular emendas, CEAP e votos). A carga (`--load-db`) é idempotente, cria os ex-parlamentares com seus mandatos e alimenta o **Basômetro** (`/api/v1/politicians/{id}`): % de votos alinhados à orientação do Governo, calculada só sobre votações com orientação SIM/NÃO e com amostra mínima de 10 votações. Só entram votações de plenário ligadas a PEC, PL, PLP, MPV ou PDL; voto secreto não tem voto individual. `python -m etl.scripts.diagnose_emendas` mostra por que emendas ficam sem vínculo (bancadas e Relator-Geral não são pessoas).

Presença em plenário e remuneração (somente dados oficiais; nada é sorteado): `python etl/run_etl.py --presenca` extrai (i) da **Câmara** o relatório oficial "Presença em Plenário" de cada deputado no portal da Câmara (dia com sessão deliberativa: presença, ausência, missão, licença e demais justificativas; série publicada a partir de 2020, e o resultado é conferido com o resumo oficial da própria página) e (ii) do **Senado** a presença derivada das votações nominais de plenário (voto, P-NRV ou presidência = presente; AP, MIS, LS e LP = ausência justificada; a API não informa ausência não justificada, então esse campo fica `null`). O portal da Câmara limita a taxa de requisições (HTTP 429, algo em torno de 3 a 4 páginas por minuto): o cliente espera o resfriamento sem alterar a identificação, a extração é **retomável** pelo cache em `etl/data/raw/presenca/` (ignorado pelo Git) e grava um resultado parcial a cada 200 páginas novas. Use `--presenca-max-paginas N` para limitar as páginas novas por execução e rode de novo para continuar. `python etl/run_etl.py --remuneracao` lê no portal da Câmara a remuneração fixa mensal de cada deputado e o líquido do mês mais recente (demais campos ficam `null`; o Senado não tem fonte estruturada). `--load-presenca` carrega ambos de forma idempotente (substitui o período do parlamentar, inclusive linhas sintéticas antigas); o dossiê mostra unidade, período e fonte da assiduidade.

### Passo 5: Iniciar o Backend (FastAPI)
```bash
make backend-dev
```
A API estará em execução em **`http://localhost:8000`**.
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Passo 6: Iniciar o Frontend (Next.js)
Em outro terminal:
```bash
cd frontend
npm install
npm run dev
```
O portal estará disponível em **`http://localhost:3000`**.

---

## 🧪 6. Esteira de Validação Local (CI Quality Gate)

Para validar localmente todo o código antes de submeter commits ou Pull Requests:

```bash
# Executa todos os testes, linters, tipagem e build em modo fail-fast
make ci
```

Você também pode executar as validações de forma granular:

| Comando | Descrição |
| :--- | :--- |
| `make format` | Autoformatação de código Python com `black` e `isort` |
| `make lint` | Análise estática com `flake8` (Python) e `eslint` (TypeScript) |
| `make typecheck` | Checagem de tipos com `mypy` e `tsc --noEmit` |
| `make security` | Auditoria estática de vulnerabilidades com `bandit` |
| `make test` | Execução das suítes de testes automatizados (`pytest` e `vitest`) |
| `make build-frontend` | Validação de compilação de produção do Next.js |

---

## 📡 7. Principais Endpoints da API RESTful

| Método | Endpoint | Descrição |
| :--- | :--- | :--- |
| `GET` | `/api/v1/politicians` | Listagem e busca de políticos com filtros por cargo, partido e estado |
| `GET` | `/api/v1/politicians/{id}` | Dossiê completo: perfil, Basômetro, relevância de leis e doações |
| `GET` | `/api/v1/politicians/{id}/doacoes` | Prestações de contas eleitorais e Top Doadores (TSE) |
| `GET` | `/api/v1/politicians/{id}/ceap` | Cota parlamentar: gastos por categoria e fornecedores contratados |
| `GET` | `/api/v1/politicians/{id}/emendas` | Emendas parlamentares pagas e municípios beneficiados |
| `GET` | `/api/v1/politicians/{id}/certidoes` | Certidões judiciais cíveis e criminais (Ficha Limpa) |
| `GET` | `/api/v1/economic/annual-summary` | Série macroeconômica histórica (PIB, IPCA, Dólar, Salário Mínimo) |
| `GET` | `/api/v1/analytics/mandates-performance` | Desempenho consolidado por mandato presidencial |
| `GET` | `/api/v1/analytics/compare-mandates` | Comparação normalizada de mandatos ($T_0 \dots T_n$) |
| `GET` | `/api/v1/analytics/party-fidelity` | Saldo líquido de bancadas e migrações partidárias |
| `GET` | `/api/v1/cidadania/consultas` | Consultas públicas e enquetes ao vivo (Senado e Câmara) |
| `GET` | `/api/v1/legislative/ranking/authors` | Ranking de produtividade parlamentar com Score IPLE |
| `GET` | `/api/v1/legislative/calendar` | Diário do Congresso com calendário anual de votações nominais |

---

## 📜 8. Licença e Transparência

Este projeto é software livre licenciado sob a [GNU Affero General Public License v3.0 (GNU AGPLv3)](LICENSE). Copyright (c) 2026 Saulo Araujo Campos. Todas as informações exibidas constituem patrimônio público acessível sob os ditames da Lei nº 12.527/2011 (LAI) e da legislação eleitoral brasileira.
