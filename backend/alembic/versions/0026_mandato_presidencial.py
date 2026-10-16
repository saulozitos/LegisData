"""Metadados dos mandatos presidenciais em `core` e corte da linha presidencial em 1995.

- `core.mandato_presidencial`: identificador público (`slug`, o mesmo `id_mandato` que a API já usa), rótulo do
  mandato ("Lula 2"), vice, como o mandato começou e situação. Uma linha por mandato de `PRESIDENTE`.
- `core.marco_governo`: marcos econômicos do mandato, em ordem.
- `core.mandato.papel`: descrição livre do papel de quem foi nomeado ("Superministro da Economia").
- Itamar Franco (1992-1995) sai: a janela dos dados começa em 1995-01-01 e a linha presidencial exibida começa em
  Fernando Henrique Cardoso (decisões D8 e confirmação de 2026-10-15). Sai também do legado, senão a ponte
  `etl.sincronizar_legado()` o recriaria na próxima execução.

Os identificadores só são criados para mandatos que já existem em `core.mandato` (depois do `--load-db`); a carga
`--load-economia` falha se o catálogo trouxer um mandato sem identificador.

Os textos (vice, motivo, marcos) vêm do arquivo curado `presidentes_historico.json` pela carga
`etl.pipelines.presidencia_loader`; a migração só cria a estrutura e os identificadores.

Irreversível nos dados: o `downgrade` recria a estrutura, mas não restaura o que foi apagado ou renomeado. Faça backup antes
de aplicar (`pg_dump`).

Revision ID: 0026
Revises: 0025
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

# (início do mandato, slug, rótulo)
MANDATOS = [
    ("1995-01-01", "fhc-1995", "FHC 1"),
    ("1999-01-01", "fhc-1999", "FHC 2"),
    ("2003-01-01", "lula-2003", "Lula 1"),
    ("2007-01-01", "lula-2007", "Lula 2"),
    ("2011-01-01", "dilma-2011", "Dilma 1"),
    ("2015-01-01", "dilma-2015", "Dilma 2"),
    ("2016-08-31", "temer-2016", None),
    ("2019-01-01", "bolsonaro-2019", None),
    ("2023-01-01", "lula-2023", "Lula 3"),
]


ROTULO = r" \((FHC|Lula|Dilma) [0-9]\)$"


def upgrade() -> None:
    op.execute(
        """
        CREATE TEMP TABLE itamar AS
        SELECT m.pessoa_id FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
        WHERE c.codigo = 'PRESIDENTE' AND m.inicio < DATE '1995-01-01'
        """
    )
    # O rótulo do mandato ("Lula 2") fica em `mandato_presidencial.rotulo`; o nome da pessoa não o carrega.
    op.execute(f"UPDATE core.pessoa SET nome_exibicao = regexp_replace(nome_exibicao, '{ROTULO}', '')")
    op.execute(f"UPDATE core.pessoa_nome SET nome = regexp_replace(nome, '{ROTULO}', '') WHERE tipo = 'ELEITORAL'")
    op.execute(f"UPDATE public.politicos SET \"nomeEleitoral\" = regexp_replace(\"nomeEleitoral\", '{ROTULO}', '')")
    op.execute(
        """
        DELETE FROM public.mandatos
        WHERE cargo::text = 'PRESIDENTE' AND "dataInicio" < DATE '1995-01-01'
        """
    )
    # Ministros nomeados por Itamar saem junto (o legado já os removeu em cascata a partir de `public.mandatos`).
    ITAMAR = """SELECT m.id FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
                 WHERE c.codigo = 'PRESIDENTE' AND m.inicio < DATE '1995-01-01'"""
    for tabela in ("core.mandato_legado", "core.mandato_situacao", "core.mandato_partido"):
        op.execute(
            f"DELETE FROM {tabela} WHERE mandato_id IN (SELECT id FROM core.mandato WHERE nomeado_por_mandato_id IN ({ITAMAR}))"
        )
    op.execute(f"DELETE FROM core.mandato WHERE nomeado_por_mandato_id IN ({ITAMAR})")
    op.execute(
        """
        DELETE FROM core.mandato_legado WHERE mandato_id IN (
            SELECT m.id FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
            WHERE c.codigo = 'PRESIDENTE' AND m.inicio < DATE '1995-01-01')
        """
    )
    op.execute(
        """
        DELETE FROM core.mandato_situacao WHERE mandato_id IN (
            SELECT m.id FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id
            WHERE c.codigo = 'PRESIDENTE' AND m.inicio < DATE '1995-01-01')
        """
    )
    op.execute(
        """
        DELETE FROM core.mandato m USING ref.cargo c
        WHERE c.id = m.cargo_id AND c.codigo = 'PRESIDENTE' AND m.inicio < DATE '1995-01-01'
        """
    )
    # Itamar Franco sem nenhum mandato restante: sai o cadastro dele no legado e no schema novo.
    op.execute(
        "DELETE FROM public.politicos WHERE id IN (SELECT uid FROM core.pessoa WHERE id IN (SELECT pessoa_id FROM itamar)) "
        'AND NOT EXISTS (SELECT 1 FROM public.mandatos m WHERE m."politicoId" = politicos.id)'
    )
    sem_mandato = "id IN (SELECT pessoa_id FROM itamar) AND NOT EXISTS (SELECT 1 FROM core.mandato m WHERE m.pessoa_id = pessoa.id)"
    for tabela in ("core.pessoa_nome", "core.pessoa_identificador"):
        op.execute(f"DELETE FROM {tabela} WHERE pessoa_id IN (SELECT id FROM core.pessoa WHERE {sem_mandato})")
    op.execute(f"DELETE FROM core.pessoa WHERE {sem_mandato}")
    op.execute("DROP TABLE itamar")
    op.execute("ALTER TABLE core.mandato ADD COLUMN papel text")
    op.execute(
        """
        CREATE TABLE core.mandato_presidencial (
            mandato_id bigint PRIMARY KEY REFERENCES core.mandato(id) ON DELETE CASCADE,
            slug text NOT NULL UNIQUE,
            rotulo text,
            vice_texto text,
            motivo_inicio text,
            status text CHECK (status IN ('CONCLUIDO', 'IMPEACHMENT', 'TITULAR_ATIVO', 'RENUNCIA', 'FALECIMENTO'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE core.marco_governo (
            mandato_id bigint NOT NULL REFERENCES core.mandato(id) ON DELETE CASCADE,
            ordem smallint NOT NULL,
            texto text NOT NULL,
            PRIMARY KEY (mandato_id, ordem)
        )
        """
    )
    for inicio, slug, rotulo in MANDATOS:
        rotulo_sql = "NULL" if rotulo is None else "'" + rotulo + "'"
        op.execute(
            "INSERT INTO core.mandato_presidencial (mandato_id, slug, rotulo) "
            f"SELECT m.id, '{slug}', {rotulo_sql} FROM core.mandato m JOIN ref.cargo c ON c.id = m.cargo_id "
            f"WHERE c.codigo = 'PRESIDENTE' AND m.inicio = DATE '{inicio}'"
        )


def downgrade() -> None:
    op.execute("ALTER TABLE core.mandato DROP COLUMN papel")
    op.execute("DROP TABLE core.marco_governo")
    op.execute("DROP TABLE core.mandato_presidencial")
