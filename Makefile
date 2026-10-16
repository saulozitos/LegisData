.PHONY: help daily ci test-db-up test-db-down db-migrate db-revision lint format typecheck security test run-all run-etl run-camara run-senado run-tse run-load-db up-db down-db backend-dev run-frontend build-frontend docker-up docker-down

# Identificação de ambiente Python
PYTHON_BIN := $(shell if [ -d "backend/venv/bin" ]; then echo "backend/venv/bin"; elif [ -d ".venv/bin" ]; then echo ".venv/bin"; else echo ""; fi)
ifeq ($(PYTHON_BIN),)
    PYTHON_BIN_ALEMBIC :=
    PY := python3
    PYTEST := pytest
    FLAKE8 := flake8
    BLACK := black
    ISORT := isort
    MYPY := mypy
    BANDIT := bandit
    PIP_AUDIT := pip-audit
else
    PYTHON_BIN_ALEMBIC := ../$(PYTHON_BIN)/
    PY := $(PYTHON_BIN)/python
    PYTEST := $(PYTHON_BIN)/pytest
    FLAKE8 := $(PYTHON_BIN)/flake8
    BLACK := $(PYTHON_BIN)/black
    ISORT := $(PYTHON_BIN)/isort
    MYPY := $(PYTHON_BIN)/mypy
    BANDIT := $(PYTHON_BIN)/bandit
    PIP_AUDIT := $(PYTHON_BIN)/pip-audit
endif

help:
	@echo "=========================================================="
	@echo "                   LEGISDATA - MAKEFILE                   "
	@echo "=========================================================="
	@echo "Validação & Qualidade (CI Local):"
	@echo "  make ci               - Executa todo o pipeline de CI local (fail-fast)"
	@echo "  make lint             - Executa linting estático (flake8 e eslint)"
	@echo "  make format           - Autoformata o código Python (isort e black)"
	@echo "  make typecheck        - Checa tipagem estática (mypy e tsc)"
	@echo "  make security         - Executa varredura estática de segurança (bandit)"
	@echo "  make test-db-up       - Sobe o Postgres descartável de teste (porta 5433)"
	@echo "  make test             - Executa as suítes de testes (pytest e vitest)"
	@echo "  make db-migrate       - Aplica as migrações Alembic (upgrade head)"
	@echo ""
	@echo "Ambiente Local & Infraestrutura:"
	@echo "  make up-db            - Sobe o banco PostgreSQL local via Docker Compose"
	@echo "  make down-db          - Encerra os contêineres Docker locais"
	@echo "  make docker-up        - Sobe toda a stack (PostgreSQL + API FastAPI) via Docker Compose"
	@echo "  make docker-down      - Encerra a stack Docker Compose"
	@echo "  make backend-dev      - Inicia a API FastAPI em modo reload (porta 8000)"
	@echo "  make run-frontend     - Inicia o Next.js App Router (porta 3000)"
	@echo "  make build-frontend   - Valida compilação estática do Next.js (TypeScript & Linter)"
	@echo ""
	@echo "Esteira de Dados (ETL & Carga):"
	@echo "  make run-all          - Executa toda a esteira (BCB + Câmara + Senado + TSE + Carga DB)"
	@echo "  make run-etl          - Executa apenas a extração macroeconômica (BCB/IBGE)"
	@echo "  make run-camara       - Executa extração da Câmara dos Deputados"
	@echo "  make run-senado       - Executa extração do Senado Federal"
	@echo "  make run-tse          - Executa extração de filiação partidária (TSE)"
	@echo "  make run-orcamento    - Executa modelagem de repasses orçamentários por UF"
	@echo "  make run-composicao   - Executa curadoria da composição do Congresso"
	@echo "  make run-renda        - Executa análise de Salário Mínimo vs Parlamentar vs Inflação"
	@echo "  make run-load-db      - Carrega e efetua upsert relacional no PostgreSQL"

# ------------------------------------------------------------------------------
# Comandos de Validação Local (CI)
# ------------------------------------------------------------------------------
ci:
	@./scripts/local_ci.sh

format:
	$(ISORT) backend/app
	$(BLACK) backend/app

lint:
	$(FLAKE8) backend/app --config=.flake8
	cd frontend && npm run lint

typecheck:
	$(MYPY) backend/app --config-file=pyproject.toml
	cd frontend && npx tsc --noEmit

security:
	$(BANDIT) -r backend/app -q
	$(PIP_AUDIT) -r backend/requirements.txt
	cd frontend && npm audit --omit=dev --audit-level=high

# Postgres descartável para a suíte (porta 5433, separado do banco de desenvolvimento)
test-db-up:
	@docker inspect legisdata_test_pg >/dev/null 2>&1 && docker start legisdata_test_pg >/dev/null || \
		docker run -d --name legisdata_test_pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test_pass \
		-e POSTGRES_DB=legis_test -p 127.0.0.1:5433:5432 postgres:16.15-alpine >/dev/null
	@until docker exec legisdata_test_pg pg_isready -U test >/dev/null 2>&1; do sleep 1; done
	@echo "Postgres de teste pronto em localhost:5433"

test-db-down:
	-docker rm -f legisdata_test_pg

# Migrações Alembic (usa DATABASE_URL/POSTGRES_* do ambiente)
db-migrate:
	cd backend && PYTHONPATH=. $(PYTHON_BIN_ALEMBIC)alembic upgrade head

db-revision:
	cd backend && PYTHONPATH=. $(PYTHON_BIN_ALEMBIC)alembic revision -m "$(m)"

test:
	POSTGRES_PASSWORD=test_ci_db_pass_123 ENVIRONMENT=test PYTHONPATH=backend $(PYTEST) --cov=backend/app --cov-branch --cov-fail-under=85 backend/tests/
	cd frontend && npm run test:coverage

# ------------------------------------------------------------------------------
# ETL & Dados
# ------------------------------------------------------------------------------
run-all:
	PYTHONPATH=. $(PY) etl/run_etl.py

run-etl:
	PYTHONPATH=. $(PY) etl/run_etl.py --economic

run-camara:
	PYTHONPATH=. $(PY) etl/run_etl.py --camara

run-senado:
	PYTHONPATH=. $(PY) etl/run_etl.py --senado

run-tse:
	PYTHONPATH=. $(PY) etl/run_etl.py --tse

run-orcamento:
	PYTHONPATH=. $(PY) etl/run_etl.py --orcamento

run-composicao:
	PYTHONPATH=. $(PY) etl/run_etl.py --composicao

run-renda:
	PYTHONPATH=. $(PY) etl/run_etl.py --renda

run-load-db:
	PYTHONPATH=. $(PY) etl/run_etl.py --load-db

# Consolidação diária (presença e faltas, mandatos, IPPM, rede de coautoria). Agende com scripts/systemd/*.timer
daily:
	PYTHONPATH=backend:. $(PY) -m etl.pipelines.cron_daily_consolidation

# ------------------------------------------------------------------------------
# Infraestrutura e Servidores
# ------------------------------------------------------------------------------
# Desenvolvimento: publica Postgres/API em 127.0.0.1 via docker-compose.dev.yml
up-db:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres

down-db:
	docker compose down

docker-up:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

docker-down:
	docker compose down

backend-dev:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

build-frontend:
	cd frontend && npm run build
