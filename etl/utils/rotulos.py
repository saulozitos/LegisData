"""Rótulos de texto que o ETL grava quando a fonte não informa o dado e que outras camadas precisam reconhecer."""

# `backend/app/services/financas_service.py` repete este texto (o backend não importa o ETL); um teste do ETL confere
# que os dois lados são iguais.
DOADOR_NAO_IDENTIFICADO = "Doador não identificado"
FORNECEDOR_NAO_IDENTIFICADO = "Fornecedor não identificado"
