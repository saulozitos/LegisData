"""Composição do Congresso por mandato presidencial, presidentes das Casas e produção legislativa do Executivo em `leg`.

Tira dos arquivos/constantes (`composicao_congresso.json`, `DADOS_HISTORICOS_EXECUTIVO`) os dados curados que alimentam o
IPLE e a tela de composição do Congresso:

- `leg.composicao_mandato`: por mandato e Casa, o total de cadeiras, a origem das bancadas (curadoria ou TSE) e o
  resultado da conferência com o TSE.
- `leg.bancada_mandato`: cadeiras de cada partido na Casa durante o mandato (`cadeiras`, curadoria ou TSE), os eleitos
  segundo o TSE (`cadeiras_tse`) e a classificação base/centro/oposição. A governabilidade é calculada destas linhas.
- `leg.presidencia_casa` e `leg.presidencia_casa_mandato`: quem presidiu a Câmara e o Senado e quais presidentes cada
  mandato lista (com o período, que varia de um mandato para outro).
- `leg.producao_executivo`: proposições do Executivo e vetos de cada mandato (insumo do IPLE).

Revision ID: 0028
Revises: 0027
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE leg.composicao_mandato (
            mandato_id bigint NOT NULL REFERENCES core.mandato(id) ON DELETE CASCADE,
            casa_id smallint NOT NULL REFERENCES ref.casa_legislativa(id),
            total_cadeiras smallint NOT NULL CHECK (total_cadeiras > 0),
            bancadas_origem text NOT NULL DEFAULT 'CURADORIA' CHECK (bancadas_origem IN ('CURADORIA', 'TSE')),
            tse_status text,
            tse_ano_legislatura smallint,
            tse_total_eleitos smallint,
            tse_total_esperado smallint,
            tse_conferido boolean,
            tse_nota text,
            tse_motivo text,
            tse_divergencias jsonb,
            observacao text,
            fonte_texto text,
            PRIMARY KEY (mandato_id, casa_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE leg.bancada_mandato (
            mandato_id bigint NOT NULL,
            casa_id smallint NOT NULL,
            partido_sigla text NOT NULL,
            cadeiras smallint CHECK (cadeiras >= 0),
            cadeiras_tse smallint CHECK (cadeiras_tse >= 0),
            alinhamento text CHECK (alinhamento IN ('BASE_GOVERNO', 'INDEPENDENTE_CENTRO', 'OPOSICAO', 'NAO_CLASSIFICADO')),
            cor_hex char(7),
            ordem smallint NOT NULL,
            PRIMARY KEY (mandato_id, casa_id, partido_sigla),
            FOREIGN KEY (mandato_id, casa_id) REFERENCES leg.composicao_mandato(mandato_id, casa_id) ON DELETE CASCADE,
            CHECK (cadeiras IS NOT NULL OR cadeiras_tse IS NOT NULL),
            CHECK (cadeiras IS NULL OR alinhamento IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE leg.presidencia_casa (
            id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            casa_id smallint NOT NULL REFERENCES ref.casa_legislativa(id),
            nome text NOT NULL,
            partido_sigla text,
            uf char(2) REFERENCES ref.uf(sigla),
            foto_url text,
            UNIQUE NULLS NOT DISTINCT (casa_id, nome, partido_sigla)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE leg.presidencia_casa_mandato (
            mandato_id bigint NOT NULL REFERENCES core.mandato(id) ON DELETE CASCADE,
            presidencia_id integer NOT NULL REFERENCES leg.presidencia_casa(id),
            ordem smallint NOT NULL,
            rotulo_periodo text NOT NULL,
            PRIMARY KEY (mandato_id, presidencia_id, rotulo_periodo)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE leg.producao_executivo (
            mandato_id bigint PRIMARY KEY REFERENCES core.mandato(id) ON DELETE CASCADE,
            proposicoes_executivo integer NOT NULL CHECK (proposicoes_executivo >= 0),
            proposicoes_aprovadas integer NOT NULL CHECK (proposicoes_aprovadas BETWEEN 0 AND proposicoes_executivo),
            vetos_apreciados integer NOT NULL CHECK (vetos_apreciados >= 0),
            vetos_mantidos integer NOT NULL CHECK (vetos_mantidos BETWEEN 0 AND vetos_apreciados),
            vetos_pendentes integer NOT NULL DEFAULT 0 CHECK (vetos_pendentes >= 0),
            oposicao_cadeiras_camara smallint,
            total_cadeiras_camara smallint,
            fonte_texto text NOT NULL
        )
        """
    )


def downgrade() -> None:
    for tabela in ("producao_executivo", "presidencia_casa_mandato", "presidencia_casa", "bancada_mandato", "composicao_mandato"):
        op.execute(f"DROP TABLE leg.{tabela}")
