"""Configuração dos testes do ETL: raiz do projeto no sys.path e ambiente mínimo para importar o backend."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT / "backend")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

# O engine do backend é criado no import (sem conectar). Uma URL qualquer basta para os testes de import.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("ENVIRONMENT", "test")
