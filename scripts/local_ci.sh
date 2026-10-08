#!/usr/bin/env bash
# ==============================================================================
# LEGISDATA - LOCAL CI VALIDATION SCRIPT
# Executa todas as etapas de validação idênticas ao GitHub Actions.
# Para na primeira falha (fail-fast / set -e).
# ==============================================================================
set -e

# Cores para feedback visual no terminal
BOLD="\033[1m"
GREEN="\033[0;32m"
BLUE="\033[0;34m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "\n${BOLD}${BLUE}================================================================${RESET}"
echo -e "${BOLD}${BLUE}               LEGISDATA - ESTEIRA DE CI LOCAL                  ${RESET}"
echo -e "${BOLD}${BLUE}================================================================${RESET}\n"

# Identifica o Python do ambiente virtual
if [ -d "backend/venv" ]; then
    PYTHON="backend/venv/bin/python"
    PYTEST="backend/venv/bin/pytest"
    FLAKE8="backend/venv/bin/flake8"
    BLACK="backend/venv/bin/black"
    ISORT="backend/venv/bin/isort"
    MYPY="backend/venv/bin/mypy"
    BANDIT="backend/venv/bin/bandit"
elif [ -d ".venv" ]; then
    PYTHON=".venv/bin/python"
    PYTEST=".venv/bin/pytest"
    FLAKE8=".venv/bin/flake8"
    BLACK=".venv/bin/black"
    ISORT=".venv/bin/isort"
    MYPY=".venv/bin/mypy"
    BANDIT=".venv/bin/bandit"
else
    PYTHON="python3"
    PYTEST="pytest"
    FLAKE8="flake8"
    BLACK="black"
    ISORT="isort"
    MYPY="mypy"
    BANDIT="bandit"
fi

export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-test_ci_db_pass_123}"
export ENVIRONMENT="test"

echo -e "${BOLD}[1/6] Checagem de Formatação (black & isort)...${RESET}"
$ISORT --check-only backend/app
$BLACK --check backend/app
echo -e "${GREEN}✓ Formatação Python em conformidade.${RESET}\n"

echo -e "${BOLD}[2/6] Análise Estática & Linting (flake8 & eslint)...${RESET}"
$FLAKE8 backend/app --config=.flake8
(cd frontend && npm run lint)
echo -e "${GREEN}✓ Linting Python e TypeScript sem pendências.${RESET}\n"

echo -e "${BOLD}[3/6] Checagem de Tipagem Estática (mypy & tsc)...${RESET}"
$MYPY backend/app --config-file=pyproject.toml
(cd frontend && npx tsc --noEmit)
echo -e "${GREEN}✓ Checagem de tipos estáticos aprovada.${RESET}\n"

echo -e "${BOLD}[4/6] Auditoria Estática de Segurança (bandit)...${RESET}"
$BANDIT -r backend/app -q
echo -e "${GREEN}✓ Auditoria de segurança sem vulnerabilidades detectadas.${RESET}\n"

echo -e "${BOLD}[5/6] Execução da Suíte de Testes Automatizados (pytest & vitest)...${RESET}"
PYTHONPATH=backend $PYTEST backend/tests/
(cd frontend && npm test -- --run)
echo -e "${GREEN}✓ Todos os testes automatizados passaram com sucesso.${RESET}\n"

echo -e "${BOLD}[6/6] Compilação de Produção Frontend (next build)...${RESET}"
(cd frontend && NEXT_TELEMETRY_DISABLED=1 npm run build)
echo -e "${GREEN}✓ Compilação de produção concluída sem erros.${RESET}\n"

echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo -e "${BOLD}${GREEN}  ✓ PARABÉNS! TODAS AS VALIDAÇÕES DO CI PASSARAM COM SUCESSO.   ${RESET}"
echo -e "${BOLD}${GREEN}================================================================${RESET}\n"
