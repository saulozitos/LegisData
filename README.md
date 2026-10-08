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
| **INPE** | Desmatamento anual consolidado na Amazônia Legal e Cerrado | Projeto PRODES / Plataforma TerraBrasilis |
| **IPEA & FBSP** | Séries históricas de segurança pública, taxas de homicídio e feminicídio | IpeaData & Fórum Brasileiro de Segurança Pública |

---

## 🔒 3. Segurança, Infraestrutura e Conformidade

A infraestrutura e o pipeline de CI/CD do LegisData foram endurecidos contra ameaças cibernéticas e auditorias de conformidade:

- **Isolamento de Banco e API:** O serviço PostgreSQL (`5432`) e o backend FastAPI (`8000`) são restritos estritamente ao loopback local (`127.0.0.1`), impedindo conexões diretas via rede externa ou LAN.
- **Fail-Fast de Credenciais:** A aplicação recusa iniciar sem uma senha de banco explícita configurada no ambiente. Não existem senhas padrão ou fallbacks no código.
- **Contêineres Não-Root:** As imagens Docker executam sob usuário não-privilegiado (`appuser`), mitigando riscos de escalonamento de privilégios.
- **Proteção contra Vazamento:** Arquivos `.dockerignore` na raiz e nos subprojetos garantem que segredos (`.env`), chaves e arquivos temporários não entrem nas camadas das imagens.
- **CI/CD Endurecido (GitHub Actions):**
  - Runner em nuvem isolado (`ubuntu-latest`) substituindo runners `self-hosted` para blindagem contra Remote Code Execution (RCE) via Pull Requests de forks.
  - Princípio de privilégio mínimo: `permissions: { contents: read }`.
  - Fixação de todas as actions por hash imutável (SHA).
- **Proteção contra DoS em APIs Governamentais:** O endpoint `/cidadania/consultas` possui rate-limiting em memória com cooldown mínimo de 5 minutos, protegendo os servidores do Senado e da Câmara contra bloqueios.
- **Divulgação Responsável:** Política formal de segurança em [SECURITY.md](SECURITY.md) e recurso *Private Vulnerability Reporting* habilitado no repositório.

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
  - **Segurança Estática:** `bandit`.
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
