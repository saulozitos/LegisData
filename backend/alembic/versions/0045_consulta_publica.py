"""Consultas públicas do Participe (Votações): foto diária no banco.

A tela lia as consultas direto dos portais do Senado e da Câmara, num cache em memória de 1 hora: só atualizava quando alguém
visitava, esvaziava a cada reinício da API e fazia dezenas de chamadas externas na primeira visita. Agora um job diário
(`etl.pipelines.cidadania_atualizacao`, pelo timer do cadastro) coleta e grava aqui, e a API só lê o banco. `coletado_em` é a
hora da última coleta que viu a matéria; a tela mostra a data mais recente. Os portais não publicam início nem fim da votação
popular, então `primeira_coleta_em` (quando a coleta diária viu a matéria pela primeira vez) e `encerrada_em` (quando viu que ela
deixou de estar aberta) são datas OBSERVADAS pelo LegisData, e a tela as rotula assim. `data_apresentacao` é a oficial. Matéria aberta que deixou de aparecer no portal
numa coleta bem-sucedida é marcada como encerrada, nunca apagada.

Revision ID: 0045
Revises: 0044
"""

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE leg.consulta_publica (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            casa text NOT NULL CHECK (casa IN ('Senado', 'Câmara')),
            id_externo text NOT NULL,
            sigla_projeto text NOT NULL,
            ementa text NOT NULL,
            link_oficial_votacao text NOT NULL,
            link_tramitacao_oficial text,
            em_votacao_aberta boolean NOT NULL,
            votos_sim integer CHECK (votos_sim IS NULL OR votos_sim >= 0),
            votos_nao integer CHECK (votos_nao IS NULL OR votos_nao >= 0),
            tema text,
            status text,
            autor text,
            data_apresentacao date,
            destaque boolean NOT NULL DEFAULT false,
            fonte_dados text NOT NULL CHECK (fonte_dados IN ('tempo_real', 'curadoria')),
            coletado_em timestamptz NOT NULL DEFAULT now(),
            primeira_coleta_em timestamptz NOT NULL DEFAULT now(),
            encerrada_em timestamptz,
            UNIQUE (casa, id_externo)
        )
        """
    )
    op.execute("CREATE INDEX ix_consulta_publica_aberta ON leg.consulta_publica (em_votacao_aberta, coletado_em DESC)")
    op.execute("GRANT SELECT ON leg.consulta_publica TO legisdata_leitura")


def downgrade() -> None:
    op.execute("DROP TABLE leg.consulta_publica")
