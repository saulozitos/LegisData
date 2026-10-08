.PHONY: help ci lint format typecheck security test run-all run-etl run-camara run-senado run-tse run-load-db up-db down-db backend-dev run-frontend build-frontend docker-up docker-down

# Identificação de ambiente Python
PYTHON_BIN := $(shell if [ -d "backend/venv/bin" ]; then echo "backend/venv/bin"; elif [ -d ".venv/bin" ]; then echo ".venv/bin"; else echo ""; fi)
ifeq ($(PYTHON_BIN),)
    PY := python3
    PYTEST := pytest
    FLAKE8 := flake8
    BLACK := black
    ISORT := isort
    MYPY := mypy
    BANDIT := bandit
else
    PY := $(PYTHON_BIN)/python
    PYTEST := $(PYTHON_BIN)/pytest
    FLAKE8 := $(PYTHON_BIN)/flake8
    BLACK := $(PYTHON_BIN)/black
    ISORT := $(PYTHON_BIN)/isort
    MYPY := $(PYTHON_BIN)/mypy
    BANDIT := $(PYTHON_BIN)/bandit
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
	@echo "  make test             - Executa as suítes de testes (pytest e vitest)"
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

test:
	POSTGRES_PASSWORD=test_ci_db_pass_123 ENVIRONMENT=test PYTHONPATH=backend $(PYTEST) backend/tests/
	cd frontend && npm test -- --run

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

# ------------------------------------------------------------------------------
# Infraestrutura e Servidores
# ------------------------------------------------------------------------------
up-db:
	docker compose up -d postgres

down-db:
	docker compose down

docker-up:
	docker compose up -d

docker-down:
	docker compose down

backend-dev:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

run-frontend:
	cd frontend && npm run dev

build-frontend:
	cd frontend && npm run build
