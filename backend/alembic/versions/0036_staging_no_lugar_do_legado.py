"""Staging: as tabelas de entrada do ETL saem do `public` e passam a viver no schema `stg`.

O ETL ainda grava o cadastro de partidos, políticos, filiações, mandatos, proposições, votações e presença em tabelas
relacionais de entrada, e as funções de fusão projetam essas tabelas em `core` e `leg`. Aquelas tabelas eram o "legado" do
`public`; agora são a camada de staging (`stg`), ao lado das tabelas `stg.camara_*`, e o `public` fica sem dado de
domínio. A API nunca lê o `stg`.

- As 13 tabelas de entrada vão para `stg` (`ALTER TABLE ... SET SCHEMA`: dados, chaves e índices vão juntos).
- As funções de fusão são reescritas para ler de `stg` e ganham nomes que dizem o que fazem:
  `etl.sincronizar_legado` vira `etl.merge_cadastro` e `etl.sincronizar_legado_leg` vira `etl.merge_legislativo`.
  O texto atual de cada função é lido do catálogo, não copiado de revisões antigas, então a lógica não muda.
- `public.log_execucao_cron`, criada antes só pelo DDL de partida da API, vira `etl.log_execucao_cron` (migração de verdade).
- Os ajustes de partida da API (valores de enumeração e colunas de orientação) entram aqui de forma idempotente e o DDL de
  partida sai do código. O saneamento da legenda MISSÃO que a API aplicava a cada subida não vem junto: o Partido Missão
  tem registro no TSE, a base não tem mandato nem filiação dessa sigla e o ETL a trata como qualquer outra legenda.
- A coluna `cpf` de `stg.politicos` sai: nenhum CPF é gravado (decisão D3) e ela nunca foi preenchida.
- Papel de leitura `legisdata_leitura` (sem login): só `SELECT` nos schemas que a API lê. A API pode usar um usuário
  com esse papel; o ETL e as migrações seguem com o dono.

Revision ID: 0036
Revises: 0035
"""

import re

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

TABELAS = (
    "politicos",
    "partidos_politicos",
    "filiacoes_partidarias",
    "mandatos",
    "membros_gabinete",
    "proposicoes",
    "proposicoes_autores",
    "sessoes_votacao",
    "votos_parlamentares",
    "registros_presenca",
    "votacoes_proposicao",
    "votos_nominais",
    "orientacoes_partidarias",
)
# (schema, nome atual, nome novo)
FUNCOES = (
    ("etl", "sincronizar_legado", "merge_cadastro"),
    ("etl", "sincronizar_legado_leg", "merge_legislativo"),
    ("etl", "merge_camara_bulk", "merge_camara_bulk"),
    ("etl", "merge_camara_historico", "merge_camara_historico"),
    ("core", "unificar_duplicadas", "unificar_duplicadas"),
)
SCHEMAS_DE_LEITURA = ("ref", "core", "leg", "eco", "fin", "param")

_TABELAS_RE = re.compile(r"\bpublic\.(%s)\b" % "|".join(TABELAS))


def _definicao(conn, esquema: str, nome: str) -> str:
    return conn.exec_driver_sql(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = %s AND p.proname = %s",
        (esquema, nome),
    ).scalar_one()


def _reescrever(fonte: str) -> str:
    novo = _TABELAS_RE.sub(r"stg.\1", fonte)
    return novo.replace("etl.sincronizar_legado_leg", "etl.merge_legislativo").replace(
        "etl.sincronizar_legado", "etl.merge_cadastro"
    )


def upgrade() -> None:
    conn = op.get_bind()
    op.execute("CREATE SCHEMA IF NOT EXISTS stg")

    # o catálogo ainda mostra `public.` nas funções: lê antes de mover as tabelas
    definicoes = {(e, n, novo): _definicao(conn, e, n) for e, n, novo in FUNCOES}

    for tabela in TABELAS:
        op.execute(f"ALTER TABLE public.{tabela} SET SCHEMA stg")
    op.execute("ALTER TABLE stg.politicos DROP COLUMN IF EXISTS cpf")

    for (esquema, antigo, novo), fonte in definicoes.items():
        corpo = _reescrever(fonte)
        if novo != antigo:
            corpo = corpo.replace(f"FUNCTION {esquema}.{antigo}(", f"FUNCTION {esquema}.{novo}(", 1)
        conn.exec_driver_sql(corpo.replace("%", "%%"))
        if novo != antigo:
            op.execute(f"DROP FUNCTION {esquema}.{antigo}()")
        # as funções de fusão escrevem em `core`/`leg`: só o dono as executa (o papel de leitura tem USAGE em `etl`)
        op.execute(f"REVOKE EXECUTE ON FUNCTION {esquema}.{novo}() FROM PUBLIC")

    # ajustes que a API aplicava ao subir (idempotentes)
    for valor in ("PR", "PRC", "PDS", "REQ", "INC"):
        op.execute(f"ALTER TYPE tipoproposicaoenum ADD VALUE IF NOT EXISTS '{valor}'")
    for valor in ("APROVADO_PLENARIO", "APROVADO_COMISSAO"):
        op.execute(f"ALTER TYPE statustramitacaoenum ADD VALUE IF NOT EXISTS '{valor}'")
    op.execute('ALTER TABLE stg.sessoes_votacao ADD COLUMN IF NOT EXISTS "orientacaoGoverno" VARCHAR(20)')
    op.execute('ALTER TABLE stg.sessoes_votacao ADD COLUMN IF NOT EXISTS "orientacoesBancadas" TEXT')

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS etl.log_execucao_cron (
            id uuid PRIMARY KEY,
            "dataExecucao" timestamptz DEFAULT CURRENT_TIMESTAMP,
            "statusExecucao" varchar(20) NOT NULL,
            "registrosAtualizados" integer NOT NULL DEFAULT 0,
            "tempoProcessamentoSegundos" integer NOT NULL DEFAULT 0,
            "erroMensagem" text,
            etapa varchar(50),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute('CREATE INDEX IF NOT EXISTS idx_cron_data ON etl.log_execucao_cron ("dataExecucao")')
    op.execute('CREATE INDEX IF NOT EXISTS idx_cron_status ON etl.log_execucao_cron ("statusExecucao")')
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.log_execucao_cron') IS NOT NULL THEN
                INSERT INTO etl.log_execucao_cron
                    (id, "dataExecucao", "statusExecucao", "registrosAtualizados", "tempoProcessamentoSegundos",
                     "erroMensagem", etapa)
                -- o texto cru da exceção (host, caminho, SQL) não entra na tabela que o papel de leitura enxerga: só
                -- sobrevive o formato `etapa: Classe` que o cron passou a registrar
                SELECT id, "dataExecucao", "statusExecucao", "registrosAtualizados", "tempoProcessamentoSegundos",
                       CASE WHEN "erroMensagem" IS NULL THEN NULL
                            WHEN "erroMensagem" ~ '^([a-zçãõáéíóúê]+: )?[A-Z][A-Za-z0-9_]*(; ([a-zçãõáéíóúê]+: )?[A-Z][A-Za-z0-9_]*)*$'
                                THEN "erroMensagem"
                            ELSE 'Falha registrada; o detalhe está no log do servidor.' END,
                       etapa
                FROM public.log_execucao_cron ON CONFLICT (id) DO NOTHING;
                DROP TABLE public.log_execucao_cron;
            END IF;
        END $$
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legisdata_leitura') THEN
                CREATE ROLE legisdata_leitura NOLOGIN;
            END IF;
        END $$
        """
    )
    for schema in SCHEMAS_DE_LEITURA:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO legisdata_leitura")
        op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO legisdata_leitura")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT ON TABLES TO legisdata_leitura")
    op.execute("GRANT USAGE ON SCHEMA etl TO legisdata_leitura")
    op.execute("GRANT SELECT ON etl.fonte, etl.log_execucao_cron TO legisdata_leitura")


def downgrade() -> None:
    conn = op.get_bind()
    definicoes = {(e, n, novo): _definicao(conn, e, novo) for e, n, novo in FUNCOES}
    for tabela in TABELAS:
        op.execute(f"ALTER TABLE stg.{tabela} SET SCHEMA public")
    for (esquema, antigo, novo), fonte in definicoes.items():
        corpo = re.sub(r"\bstg\.(%s)\b" % "|".join(TABELAS), r"public.\1", fonte)
        corpo = corpo.replace("etl.merge_legislativo", "etl.sincronizar_legado_leg").replace(
            "etl.merge_cadastro", "etl.sincronizar_legado"
        )
        if novo != antigo:
            corpo = corpo.replace(f"FUNCTION {esquema}.{novo}(", f"FUNCTION {esquema}.{antigo}(", 1)
        conn.exec_driver_sql(corpo.replace("%", "%%"))
        if novo != antigo:
            op.execute(f"DROP FUNCTION {esquema}.{novo}()")
    # a coluna `cpf` não volta: nenhum CPF é gravado (decisão D3) e nenhum leitor ou escritor a usa
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS public.log_execucao_cron (
            id uuid PRIMARY KEY,
            "dataExecucao" timestamptz DEFAULT CURRENT_TIMESTAMP,
            "statusExecucao" varchar(20) NOT NULL,
            "registrosAtualizados" integer NOT NULL DEFAULT 0,
            "tempoProcessamentoSegundos" integer NOT NULL DEFAULT 0,
            "erroMensagem" text,
            etapa varchar(50)
        )
        """
    )
    op.execute(
        """
        INSERT INTO public.log_execucao_cron
            (id, "dataExecucao", "statusExecucao", "registrosAtualizados", "tempoProcessamentoSegundos",
             "erroMensagem", etapa)
        SELECT id, "dataExecucao", "statusExecucao", "registrosAtualizados", "tempoProcessamentoSegundos",
               "erroMensagem", etapa
        FROM etl.log_execucao_cron ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute("DROP TABLE etl.log_execucao_cron")
    # o papel de leitura fica (pode ter privilégios em outros bancos do cluster), mas perde o que ganhou aqui, inclusive
    # os privilégios padrão sobre tabelas futuras
    op.execute("DROP OWNED BY legisdata_leitura")
