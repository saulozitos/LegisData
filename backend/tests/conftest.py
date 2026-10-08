import os
import pytest

# Garante variáveis mínimas para a suíte de testes sem vazar credenciais
os.environ.setdefault("POSTGRES_PASSWORD", "test_db_password_ci")
os.environ.setdefault("ENVIRONMENT", "test")
