"""Remove as tabelas do painel do Executivo do legado.

`public.presidential_mandates` e `public.mandate_indicators` guardavam dois mandatos e indicadores mensais digitados à
mão (aprovação popular, emendas, câmbio, Selic) por `seed_executivo.py`, que deixou de existir (decisão D7: só fonte
oficial rastreada). O painel passou a ler `core.mandato_presidencial` e as séries de `eco`.

Irreversível nos dados: o `downgrade` recria a estrutura, mas não restaura o que foi apagado ou renomeado. Faça backup antes
de aplicar (`pg_dump`).

Revision ID: 0027
Revises: 0026
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.mandate_indicators")
    op.execute("DROP TABLE IF EXISTS public.presidential_mandates")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.presidential_mandates (
            id uuid PRIMARY KEY,
            nome varchar(255) NOT NULL,
            inicio date NOT NULL,
            fim date,
            partido varchar(50) NOT NULL,
            foto_url varchar(500),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE public.mandate_indicators (
            id uuid PRIMARY KEY,
            mandate_id uuid NOT NULL REFERENCES public.presidential_mandates(id) ON DELETE CASCADE,
            chave_indicador varchar(100) NOT NULL,
            valor double precision NOT NULL,
            data_medicao date NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
