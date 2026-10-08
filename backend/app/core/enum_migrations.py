"""
Ajustes idempotentes de tipos ENUM do PostgreSQL.

``Base.metadata.create_all`` não altera tipos ENUM existentes; quando o Python
ganha valores novos, o banco precisa de ``ALTER TYPE ... ADD VALUE``. O nome do
tipo depende de quem criou a tabela: SQLAlchemy usa ``tipopresencaenum`` e o
Prisma (database/schema.prisma) usa ``"TipoPresenca"``; tratamos os dois.
Chamado no startup da API (app/main.py) e no início da carga do ETL.
"""

from sqlalchemy import text

NOVOS_VALORES_TIPO_PRESENCA = ("PARTICIPOU_VOTACAO", "PRESENTE_SEM_VOTO")

_SQL = """
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['tipopresencaenum', 'TipoPresenca'] LOOP
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = t) THEN
      EXECUTE format('ALTER TYPE %I ADD VALUE IF NOT EXISTS %L', t, :valor);
    END IF;
  END LOOP;
END $$;
"""


def garantir_valores_tipo_presenca(conn) -> None:
    """Adiciona os valores novos de TipoPresencaEnum aos tipos existentes no banco.

    ``conn`` é uma Connection/Session do SQLAlchemy. Como o DO-block não aceita
    bind parameters, o valor (constante interna, nunca entrada externa) é
    interpolado como literal SQL escapado.
    """
    for valor in NOVOS_VALORES_TIPO_PRESENCA:
        literal = "'" + valor.replace("'", "''") + "'"
        conn.execute(text(_SQL.replace(":valor", literal)))
