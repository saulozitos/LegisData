"""Relatos de informação incorreta enviados pelos usuários.

A plataforma passa a receber "Encontrou uma informação incorreta?" já vinculado ao parlamentar ou à matéria consultada, para a
correção chegar com contexto. É tabela interna da operação, por isso fica em `etl` (os schemas de leitura não a expõem) e não
guarda CPF: o serviço recusa texto com CPF. O contato é opcional.

Revision ID: 0044
Revises: 0043
"""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE etl.relato_erro (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            criado_em timestamptz NOT NULL DEFAULT now(),
            alvo_tipo text NOT NULL CHECK (alvo_tipo IN
                ('POLITICO', 'VOTACAO', 'PROPOSICAO', 'PARTIDO', 'PAINEL', 'CLASSIFICACAO', 'OUTRO')),
            alvo_id text,
            alvo_rotulo text,
            secao text,
            descricao text NOT NULL CHECK (char_length(descricao) BETWEEN 10 AND 2000),
            contato text CHECK (contato IS NULL OR char_length(contato) <= 200),
            pagina text CHECK (pagina IS NULL OR char_length(pagina) <= 500),
            status text NOT NULL DEFAULT 'NOVO' CHECK (status IN ('NOVO', 'EM_ANALISE', 'CORRIGIDO', 'DESCARTADO'))
        )
        """
    )
    op.execute("CREATE INDEX ix_relato_erro_status ON etl.relato_erro (status, criado_em DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE etl.relato_erro")
