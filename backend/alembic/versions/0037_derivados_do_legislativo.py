"""Derivados pré-calculados do legislativo: pontuação de autoria e pares de coautoria.

Duas telas recalculavam a cada abertura o que só muda quando a carga muda: o ranking de autores somava a pontuação de
683 mil autorias (visão `leg.vw_autoria_pontuada_unica`, 7 s) e a rede de coautoria juntava as autorias duas a duas
(2,3 s de consulta mais a montagem do grafo). Aqui o resultado fica guardado em duas visões materializadas:

- `leg.mv_autoria_pontuada_unica`: o conteúdo de `leg.vw_autoria_pontuada_unica` (a visão continua sendo a fonte do cálculo);
- `leg.mv_coautoria_par`: uma linha por par de parlamentares e proposição de até 40 autores (acima disso é assinatura em
  massa, que a rede já excluía; sem o limite seriam 21 milhões de linhas), com os campos dos filtros da rede (tipo, ano,
  casa) e o número de autores da proposição.

Elas nunca ficam velhas sem aviso: gatilhos por comando em toda tabela de que o cálculo depende só marcam
`leg.pontuacao_controle.sujo`, e `leg.atualizar_derivados()` refaz as duas se, e só se, o sinalizador estiver ligado. O
ETL a chama no fim de cada carga (o primeiro leitor não paga o refresh) e quem lê a chama de novo antes de ler, como rede
de segurança. O sinalizador é desligado ANTES de refazer, na mesma transação, para que uma gravação que termine durante a
atualização ligue-o de novo (nenhuma mudança se perde). Quem escrever em `leg.autoria`, `leg.proposicao`, `param.peso`,
`param.metodologia`, `ref.tipo_proposicao`, `core.filiacao` ou `core.mandato` não precisa lembrar de nada. Uma MIGRAÇÃO
que mudar a definição de `leg.vw_autoria_pontuada(_unica)` ou de `param.vw_peso_vigente` não dispara gatilho de DML: ela
tem de terminar com `UPDATE leg.pontuacao_controle SET sujo = true`.

A leitura não fica presa. O gatilho trava a linha de controle até o fim da transação de quem escreve (o `ON CONFLICT`
trava mesmo quando o `WHERE` é falso), então uma carga longa em andamento seguraria todos os leitores. Por isso a função,
quando chamada por um leitor (`p_bloquear = false`, o padrão), tenta o bloqueio consultivo sem esperar e limita a espera
por qualquer trava a meio segundo (`lock_timeout`); se não conseguir, devolve `'ocupado'` e a leitura usa a visão como
está, que é consistente com o último dado confirmado. O refresh é `CONCURRENTLY` (os índices únicos `ux_mv_*` permitem):
ele não pede `ACCESS EXCLUSIVE`, então quem lê a visão durante o refresh não espera e o refresh não é barrado por um
leitor longo. O ETL chama com `p_bloquear = true` e espera longa (`'120s'`): ele aguarda a vez em vez de desistir.
A função devolve `'refeito'`, `'em_dia'` ou `'ocupado'`, para o ETL distinguir "não precisava" de "não consegui".

Quem executa é um papel sem login e sem superusuário, `legisdata_derivados`, dono das duas visões, da tabela de controle e
das duas funções (`SECURITY DEFINER`, `search_path` fixo, `EXECUTE` só para ele, para o dono da migração e para
`legisdata_leitura`). Assim a API pode usar `legisdata_leitura` e um defeito futuro no corpo da função não herda
superusuário. O papel só lê `leg.vw_autoria_pontuada_unica`, `leg.autoria` e `leg.proposicao`.

Revision ID: 0037
Revises: 0036
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

# Tabelas de que as duas visões dependem
DEPENDENCIAS = (
    "leg.autoria",
    "leg.proposicao",
    "param.peso",
    "param.metodologia",
    "ref.tipo_proposicao",
    "core.filiacao",
    "core.mandato",
)
BLOQUEIO_DA_ATUALIZACAO = 727_420_002
# Quanto uma leitura espera por uma trava antes de desistir de atualizar e usar a visão como está
ESPERA_DA_LEITURA = "500ms"
# Proposição com mais autores que isto é assinatura em massa e fica fora da rede (um teste confere que o código usa o mesmo
# limite: mudá-lo exige uma migração que refaça `leg.mv_coautoria_par`)
MAX_AUTORES_NA_REDE = 40


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legisdata_derivados') THEN
                CREATE ROLE legisdata_derivados NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
            END IF;
        END $$
        """
    )
    op.execute("CREATE MATERIALIZED VIEW leg.mv_autoria_pontuada_unica AS SELECT * FROM leg.vw_autoria_pontuada_unica")
    op.execute(
        "CREATE UNIQUE INDEX ux_mv_autoria_pontuada_unica ON leg.mv_autoria_pontuada_unica (pessoa_id, proposicao_id)"
    )
    op.execute(
        "CREATE INDEX ix_mv_autoria_pontuada_data ON leg.mv_autoria_pontuada_unica (pessoa_id, data_apresentacao)"
    )

    op.execute(
        f"""
        CREATE MATERIALIZED VIEW leg.mv_coautoria_par AS
        WITH autores AS (
            SELECT DISTINCT proposicao_id, pessoa_id FROM leg.autoria
            WHERE pessoa_id IS NOT NULL AND tipo_codigo <> 'INSTITUCIONAL'
        ), conjuntas AS (
            SELECT proposicao_id, count(*) AS n_autores FROM autores GROUP BY proposicao_id
            HAVING count(*) BETWEEN 2 AND {MAX_AUTORES_NA_REDE}
        )
        SELECT a.pessoa_id AS pessoa_a, b.pessoa_id AS pessoa_b, a.proposicao_id, c.n_autores,
               p.tipo_codigo, p.ano, p.id_camara IS NOT NULL AS da_camara, p.id_senado IS NOT NULL AS do_senado
        FROM conjuntas c
        JOIN autores a ON a.proposicao_id = c.proposicao_id
        JOIN autores b ON b.proposicao_id = c.proposicao_id AND a.pessoa_id < b.pessoa_id
        JOIN leg.proposicao p ON p.id = c.proposicao_id
        """
    )
    op.execute(f"COMMENT ON MATERIALIZED VIEW leg.mv_coautoria_par IS 'max_autores={MAX_AUTORES_NA_REDE}'")
    op.execute("CREATE UNIQUE INDEX ux_mv_coautoria_par ON leg.mv_coautoria_par (pessoa_a, pessoa_b, proposicao_id)")
    op.execute("CREATE INDEX ix_mv_coautoria_par_ano ON leg.mv_coautoria_par (ano)")

    op.execute(
        """
        CREATE TABLE leg.pontuacao_controle (
            id boolean PRIMARY KEY DEFAULT true CHECK (id),
            sujo boolean NOT NULL
        )
        """
    )
    op.execute("INSERT INTO leg.pontuacao_controle (id, sujo) VALUES (true, false)")
    op.execute(
        """
        CREATE FUNCTION leg.marcar_derivados_sujos() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            -- upsert: se a tabela de controle for esvaziada por fora, a linha volta ligada
            INSERT INTO leg.pontuacao_controle (id, sujo) VALUES (true, true)
            ON CONFLICT (id) DO UPDATE SET sujo = true WHERE NOT leg.pontuacao_controle.sujo;
            RETURN NULL;
        END $$
        """
    )
    for tabela in DEPENDENCIAS:
        nome = tabela.replace(".", "_")
        op.execute(
            f"CREATE TRIGGER trg_derivados_sujos_{nome} AFTER INSERT OR UPDATE OR DELETE ON {tabela} "
            "FOR EACH STATEMENT EXECUTE FUNCTION leg.marcar_derivados_sujos()"
        )
        op.execute(
            f"CREATE TRIGGER trg_derivados_sujos_truncate_{nome} AFTER TRUNCATE ON {tabela} "
            "FOR EACH STATEMENT EXECUTE FUNCTION leg.marcar_derivados_sujos()"
        )
    op.execute(
        f"""
        CREATE FUNCTION leg.atualizar_derivados(p_bloquear boolean DEFAULT false, p_espera text DEFAULT '{ESPERA_DA_LEITURA}')
        RETURNS text
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
        DECLARE
            v_antes text := current_setting('lock_timeout');
        BEGIN
            IF NOT coalesce((SELECT sujo FROM leg.pontuacao_controle), true) THEN
                RETURN 'em_dia';
            END IF;
            PERFORM set_config('lock_timeout', p_espera, true);
            BEGIN
                IF p_bloquear THEN
                    PERFORM pg_advisory_xact_lock({BLOQUEIO_DA_ATUALIZACAO});  -- espera até `p_espera`
                ELSIF NOT pg_try_advisory_xact_lock({BLOQUEIO_DA_ATUALIZACAO}) THEN
                    PERFORM set_config('lock_timeout', v_antes, true);
                    RETURN 'ocupado';  -- outra atualização em curso: serve a visão como está
                END IF;
                -- desliga antes de refazer: uma gravação que terminar durante a atualização liga o sinalizador de novo
                UPDATE leg.pontuacao_controle SET sujo = false WHERE sujo;
                IF NOT FOUND AND EXISTS (SELECT 1 FROM leg.pontuacao_controle) THEN
                    PERFORM set_config('lock_timeout', v_antes, true);
                    RETURN 'em_dia';  -- outra atualização acabou de refazer
                END IF;
                INSERT INTO leg.pontuacao_controle (id, sujo) VALUES (true, false) ON CONFLICT (id) DO NOTHING;
                REFRESH MATERIALIZED VIEW CONCURRENTLY leg.mv_autoria_pontuada_unica;
                REFRESH MATERIALIZED VIEW CONCURRENTLY leg.mv_coautoria_par;
            EXCEPTION WHEN lock_not_available THEN
                -- uma carga segura a linha de controle (ou outra atualização, o bloqueio): o bloco inteiro é desfeito
                -- (o sinalizador continua ligado) e a leitura usa a visão como está
                PERFORM set_config('lock_timeout', v_antes, true);
                RETURN 'ocupado';
            END;
            PERFORM set_config('lock_timeout', v_antes, true);
            RETURN 'refeito';
        END $$
        """
    )

    # o dono dos derivados não é superusuário: lê só o que o refresh precisa e não herda mais que isso
    op.execute("GRANT USAGE ON SCHEMA leg TO legisdata_derivados")
    op.execute("GRANT SELECT ON leg.vw_autoria_pontuada_unica, leg.autoria, leg.proposicao TO legisdata_derivados")
    op.execute("ALTER MATERIALIZED VIEW leg.mv_autoria_pontuada_unica OWNER TO legisdata_derivados")
    op.execute("ALTER MATERIALIZED VIEW leg.mv_coautoria_par OWNER TO legisdata_derivados")
    op.execute("ALTER TABLE leg.pontuacao_controle OWNER TO legisdata_derivados")
    op.execute("ALTER FUNCTION leg.marcar_derivados_sujos() OWNER TO legisdata_derivados")
    op.execute("ALTER FUNCTION leg.atualizar_derivados(boolean, text) OWNER TO legisdata_derivados")
    op.execute("REVOKE EXECUTE ON FUNCTION leg.atualizar_derivados(boolean, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION leg.atualizar_derivados(boolean, text) TO legisdata_leitura")
    op.execute(
        "GRANT SELECT ON leg.mv_autoria_pontuada_unica, leg.mv_coautoria_par, leg.pontuacao_controle "
        "TO legisdata_leitura"
    )


def downgrade() -> None:
    for tabela in DEPENDENCIAS:
        nome = tabela.replace(".", "_")
        op.execute(f"DROP TRIGGER IF EXISTS trg_derivados_sujos_{nome} ON {tabela}")
        op.execute(f"DROP TRIGGER IF EXISTS trg_derivados_sujos_truncate_{nome} ON {tabela}")
    op.execute("DROP FUNCTION leg.atualizar_derivados(boolean, text)")
    op.execute("DROP FUNCTION leg.marcar_derivados_sujos()")
    op.execute("DROP TABLE leg.pontuacao_controle")
    op.execute("DROP MATERIALIZED VIEW leg.mv_coautoria_par")
    op.execute("DROP MATERIALIZED VIEW leg.mv_autoria_pontuada_unica")
    # o papel fica (como o de leitura, pode ter privilégios em outros bancos do cluster); só perde o que recebeu aqui
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA leg FROM legisdata_derivados")
    op.execute("REVOKE USAGE ON SCHEMA leg FROM legisdata_derivados")
