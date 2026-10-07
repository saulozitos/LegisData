.PHONY: help run-all run-etl run-camara run-senado run-tse run-load-db up-db down-db backend-dev run-frontend build-frontend docker-up docker-down

help:
	@echo "=========================================================="
	@echo "    POLÍTICA & ECONOMIA BRASILEIRA - COMANDOS MAKEFILE    "
	@echo "=========================================================="
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
	@echo ""
	@echo "Ambiente Local & Infraestrutura:"
	@echo "  make up-db            - Sobe o banco PostgreSQL local via Docker Compose"
	@echo "  make down-db          - Encerra os contêineres Docker locais"
	@echo "  make docker-up        - Sobe toda a stack (PostgreSQL + API FastAPI) via Docker Compose"
	@echo "  make docker-down      - Encerra a stack Docker Compose"
	@echo "  make backend-dev      - Inicia a API FastAPI em modo reload (porta 8000)"
	@echo "  make run-frontend     - Inicia o Next.js App Router (porta 3000)"
	@echo "  make build-frontend   - Valida compilação estática do Next.js (TypeScript & Linter)"

run-all:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py

run-etl:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --economic

run-camara:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --camara

run-senado:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --senado

run-tse:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --tse

run-orcamento:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --orcamento

run-composicao:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --composicao

run-renda:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --renda

run-load-db:
	PYTHONPATH=. .venv/bin/python3 etl/run_etl.py --load-db

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
