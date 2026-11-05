"""Sai `core.unificar_duplicadas`: a carga acha a pessoa pelo identificador oficial antes de criar uma nova.

A função existia porque o carregador do legado criava, para cada político, uma pessoa com o `uid` do legado e SEM o
identificador da Câmara ou do Senado (o `INSERT` do identificador batia no cadastro novo e não gravava); o cadastro novo, com
o identificador, ficava ao lado dele, e a fusão tinha de unir os dois a cada rodada (338 no banco de desenvolvimento, unidos
pela 0034). Desde a 0040 a pessoa é resolvida em `etl.preparar_cadastro` pelo identificador, em `core`, ANTES de qualquer
cadastro novo, e o `uid` que já existe nunca muda; um político que a fonte traz com um identificador já cadastrado entra na
fusão com o `uid` dessa pessoa. A duplicata não nasce mais, então a função não tem o que unir: com as tabelas relacionais de
`stg` fora, ela já devolvia 0 pelo seu próprio guarda (`to_regclass('stg.politicos') IS NULL`).

Prova (docs/PROXIMA_ENTREGA_NOVO_ETL.md, "Estado final"): a carga completa sobre uma cópia do banco de desenvolvimento deixa
`core.pessoa` (1.427 políticos), `core.pessoa_nome`, `core.pessoa_identificador` e `core.pessoa_candidata_duplicidade` iguais
às da carga anterior, duas rodadas seguidas; `test_carga_cadastro::test_pessoa_ja_cadastrada_pelo_id_oficial...` cobre o caso.
`core.unificar_pessoas` (a união em si, usada pela 0034 e por quem unir à mão) fica.

Revision ID: 0041
Revises: 0040
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

DEFINICAO = """
CREATE OR REPLACE FUNCTION core.unificar_duplicadas()
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
DECLARE
    par record;
    unidos integer := 0;
BEGIN
    -- sem as tabelas relacionais do legado (0040) não há o que unir
    RETURN 0;
END $function$
"""


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS core.unificar_duplicadas()")


def downgrade() -> None:
    # volta como função inofensiva: o corpo antigo lia `stg.politicos`, que a 0040 já tirou
    op.get_bind().exec_driver_sql(DEFINICAO.replace("%", "%%"))
    op.execute("REVOKE EXECUTE ON FUNCTION core.unificar_duplicadas() FROM PUBLIC")
