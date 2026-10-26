"""`fin.processo_judicial`: processos judiciais de uma pessoa, enriquecidos com os metadados oficiais do DataJud.

O DataJud (CNJ) só responde por número de processo e não expõe as partes. Por isso o vínculo entre a pessoa e o
processo nunca vem dele: vem de uma curadoria versionada, em que cada número traz o link da fonte oficial que liga o
processo à pessoa (`vinculo_url`, obrigatório). O DataJud entra depois, só para trazer classe, assuntos, órgão julgador,
datas e o último movimento (decisão D7). Nenhum desfecho é inferido: o que o tribunal registrou como último movimento é
o que o dossiê mostra, e a presunção de inocência é respeitada (sem pontuação nem classificação do processo).

- `numero_cnj` guarda o número no formato CNJ (`NNNNNNN-DD.AAAA.J.TR.OOOO`), o mesmo que o DataJud indexa sem pontuação.
- Campos que o DataJud não devolve ficam nulos (nunca zero nem texto inventado). A classe, porém, é obrigatória e não pode
  ser vazia: um processo sem classe oficial não entra. `assuntos` não aceita elemento nulo e o link é `https://` sem espaços
  (o ETL ainda exige domínio público e a ausência de CPF; o banco guarda o que passou por ele).
- `consultado_em` é o dia em que o DataJud foi consultado: o último movimento é o desse dia, não necessariamente o de hoje.
- Um mesmo processo pode ligar a mais de uma pessoa (litisconsórcio): a unicidade é por `(pessoa_id, numero_cnj)`.

Revision ID: 0032
Revises: 0031
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE fin.processo_judicial (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            numero_cnj text NOT NULL
                CHECK (numero_cnj ~ '^[0-9]{7}-[0-9]{2}\\.[0-9]{4}\\.[0-9]\\.[0-9]{2}\\.[0-9]{4}$'),
            tribunal text,
            grau text,
            classe text NOT NULL CHECK (btrim(classe) <> ''),
            assuntos text[] NOT NULL DEFAULT '{}' CHECK (array_position(assuntos, NULL) IS NULL),
            orgao_julgador text,
            data_ajuizamento date,
            ultimo_movimento text,
            data_ultimo_movimento date,
            total_movimentacoes integer CHECK (total_movimentacoes IS NULL OR total_movimentacoes >= 0),
            consultado_em date,
            vinculo_url text NOT NULL CHECK (vinculo_url ~ '^https://[^[:space:]]+$'),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (pessoa_id, numero_cnj)
        )
        """
    )
    op.execute("CREATE INDEX ix_processo_judicial_numero ON fin.processo_judicial (numero_cnj)")


def downgrade() -> None:
    op.execute("DROP TABLE fin.processo_judicial")
