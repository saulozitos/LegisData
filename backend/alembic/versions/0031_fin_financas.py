"""Schema `fin`: finanças e fiscalização dos parlamentares (CEAP, emendas, remuneração, patrimônio, doações, certidões).

Todas as tabelas ligam a `core.pessoa`; só a emenda aceita `pessoa_id` nulo, porque o autor pode ser uma bancada, uma
comissão, o relator-geral ou um parlamentar de mandato anterior que não existe em `core` (nesses casos o nome oficial
da fonte fica em `autor_texto`, nunca se força o vínculo com outra pessoa).

- `fin.despesa_cota`: CEAP por pessoa, ano e tipo de despesa (total real; estorno entra negativo).
- `fin.despesa_cota_fornecedor` e `fin.despesa_cota_resumo`: maiores fornecedores e quantidade de notas por pessoa. O
  mesmo fornecedor é identificado pelo CNPJ ou, sem ele, pelo nome (`grupo`, coluna gerada): a regra mora só no schema.
  A quantidade de notas de um fornecedor pode ser nula (a fonte não informou).
  CPF de fornecedor nunca é gravado: só CNPJ (14 dígitos) (decisão D3). O documento do doador só aceita CNPJ ou a
  máscara de CPF do TSE (`***.NNN.NNN-**`).
- `fin.emenda`: uma linha por emenda, localidade e função, com o tipo de autor já classificado. O código pode faltar
  (a fonte publica emendas de comissão de 2019 "sem informação"); o valor entra do mesmo jeito, para o total bater.
- `fin.remuneracao`: folha mensal do parlamentar; campo que a fonte não informa fica nulo (nunca zero). `cota_ceap`,
  `auxilio_moradia` e `outros_beneficios` existem para quando houver fonte oficial mensal; a carga atual só traz o bruto e
  o líquido, então essas três ficam nulas e o dossiê as mostra como indisponíveis.
- `fin.emenda.pessoa_id` usa `ON DELETE RESTRICT`: emenda identificada exige a pessoa (CHECK), então a unificação de
  pessoas duplicadas precisa religar as emendas à pessoa canônica antes de apagar a duplicada.
- `fin.declaracao_patrimonio`, `fin.doacao_campanha` e `fin.certidao`: dados do TSE.

Cada linha aponta para `etl.fonte` (decisão D7). Os dados começam em 1995 (decisão D8). A carga vem do ETL, que lê os
arquivos oficiais; as tabelas do legado (`public.*`) continuam existindo até a limpeza da Fase 9.

Revision ID: 0031
Revises: 0030
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

TABELAS = (
    "certidao",
    "doacao_campanha",
    "declaracao_patrimonio",
    "remuneracao",
    "emenda",
    "despesa_cota_resumo",
    "despesa_cota_fornecedor",
    "despesa_cota",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA fin")

    op.execute(
        """
        CREATE TABLE fin.despesa_cota (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            ano smallint NOT NULL CHECK (ano >= 1995),
            tipo_despesa text NOT NULL,
            valor_liquido numeric(14,2) NOT NULL,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (pessoa_id, ano, tipo_despesa)
        )
        """
    )
    op.execute("CREATE INDEX ix_despesa_cota_ano ON fin.despesa_cota (ano)")
    op.execute("CREATE INDEX ix_despesa_cota_tipo ON fin.despesa_cota (tipo_despesa)")

    op.execute(
        """
        CREATE TABLE fin.despesa_cota_fornecedor (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            nome text NOT NULL,
            cnpj char(14) CHECK (cnpj IS NULL OR cnpj ~ '^[0-9]{14}$'),
            valor_total numeric(14,2) NOT NULL,
            notas integer CHECK (notas >= 0),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            grupo text GENERATED ALWAYS AS (coalesce(cnpj::text, 'nome:' || nome)) STORED,
            UNIQUE (pessoa_id, grupo)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE fin.despesa_cota_resumo (
            pessoa_id bigint PRIMARY KEY REFERENCES core.pessoa(id) ON DELETE CASCADE,
            total_notas integer NOT NULL CHECK (total_notas >= 0),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE fin.emenda (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            pessoa_id bigint REFERENCES core.pessoa(id) ON DELETE RESTRICT,
            autor_texto text NOT NULL,
            autor_codigo text,
            tipo_autor text NOT NULL
                CHECK (tipo_autor IN ('INDIVIDUAL','BANCADA_ESTADUAL','COMISSAO_INSTITUCIONAL','RELATOR_GERAL')),
            autor_situacao text NOT NULL
                CHECK (autor_situacao IN ('IDENTIFICADO','NAO_CADASTRADO','HOMONIMO_NAO_DESAMBIGUADO','INSTITUCIONAL')),
            ano smallint NOT NULL CHECK (ano >= 1995),
            codigo_emenda text,
            tipo_emenda text NOT NULL,
            valor_empenhado numeric(16,2) NOT NULL,
            valor_pago numeric(16,2) NOT NULL,
            localidade_destino text NOT NULL,
            uf char(2) REFERENCES ref.uf(sigla),
            funcao text,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            CHECK ((autor_situacao = 'IDENTIFICADO') = (pessoa_id IS NOT NULL)),
            UNIQUE NULLS NOT DISTINCT (autor_texto, codigo_emenda, ano, tipo_emenda, localidade_destino, funcao)
        )
        """
    )
    # busca por trecho do nome, sem acento nem caixa: a regra fica num lugar só para as consultas da API
    op.execute(
        """
        CREATE FUNCTION ref.contem_texto(texto text, trecho text) RETURNS boolean
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$
            SELECT strpos(ref.normalizar_texto(texto), ref.normalizar_texto(trecho)) > 0
        $$
        """
    )
    op.execute("CREATE INDEX ix_emenda_pessoa ON fin.emenda (pessoa_id) WHERE pessoa_id IS NOT NULL")
    op.execute("CREATE INDEX ix_emenda_ano ON fin.emenda (ano)")
    op.execute("CREATE INDEX ix_emenda_uf ON fin.emenda (uf)")
    op.execute("CREATE INDEX ix_emenda_autor_codigo ON fin.emenda (autor_codigo)")

    op.execute(
        """
        CREATE TABLE fin.remuneracao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            ano smallint NOT NULL CHECK (ano >= 1995),
            mes smallint NOT NULL CHECK (mes BETWEEN 1 AND 12),
            salario_bruto numeric(12,2) NOT NULL,
            salario_liquido numeric(12,2),
            cota_ceap numeric(12,2),
            auxilio_moradia numeric(12,2),
            outros_beneficios numeric(12,2),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (pessoa_id, ano, mes)
        )
        """
    )
    op.execute("CREATE INDEX ix_remuneracao_ano ON fin.remuneracao (ano)")

    op.execute(
        """
        CREATE TABLE fin.declaracao_patrimonio (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            ano_eleicao smallint NOT NULL CHECK (ano_eleicao >= 1995),
            valor_declarado numeric(15,2) NOT NULL,
            quantidade_bens integer CHECK (quantidade_bens IS NULL OR quantidade_bens >= 0),
            detalhes text,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (pessoa_id, ano_eleicao)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE fin.doacao_campanha (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            ano_eleicao smallint NOT NULL CHECK (ano_eleicao >= 1995),
            doador_nome text NOT NULL,
            doador_documento text CHECK (
                doador_documento IS NULL
                OR doador_documento ~ '^[*]{3}[.][0-9]{3}[.][0-9]{3}-[*]{2}$'
                OR doador_documento ~ '^([0-9]{14}|[0-9]{2}[.][0-9]{3}[.][0-9]{3}/[0-9]{4}-[0-9]{2})$'
            ),
            valor numeric(15,2) NOT NULL,
            tipo_receita text,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_doacao_campanha_pessoa_ano ON fin.doacao_campanha (pessoa_id, ano_eleicao)")

    op.execute(
        """
        CREATE TABLE fin.certidao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            orgao text NOT NULL,
            tipo text NOT NULL,
            situacao text NOT NULL,
            detalhes text,
            numero_processo text,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (pessoa_id, orgao, tipo)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS ref.contem_texto(text, text)")
    for tabela in TABELAS:
        op.execute(f"DROP TABLE fin.{tabela}")
    op.execute("DROP SCHEMA fin")
