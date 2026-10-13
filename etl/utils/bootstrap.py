"""
Prepara o `sys.path` para importar o backend com UM único prefixo (`app.*`).

Antes, módulos do ETL tentavam `backend.app...` e, em fallback, `app...`; carregar os models sob dois
nomes de módulo faz o SQLAlchemy falhar com "Table ... is already defined for this MetaData instance".
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"


def ensure_backend_on_path() -> None:
    for candidate in (str(BACKEND_DIR), str(PROJECT_ROOT)):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
