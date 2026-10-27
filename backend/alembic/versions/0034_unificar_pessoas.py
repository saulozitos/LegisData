"""Unificação dos cadastros duplicados de uma mesma pessoa: `core.unificar_pessoas` e `core.unificar_duplicadas`.

O cadastro público de um político (o `uid` que o dossiê e a API usam) veio do legado, e o histórico da Câmara e do Senado
criou outro cadastro para a mesma pessoa, que ficou com o identificador oficial (`core.pessoa_identificador` é único por
tipo e valor). As finanças, a presença e boa parte do histórico estão nesse segundo cadastro, e só o identificador que o
cadastro público declara faz a ligação entre os dois.

- `core.unificar_pessoas(manter, apagar)` passa para `manter` tudo o que aponta para `apagar` (nomes, identificadores,
  mandatos, filiações, autorias, votos, presença, finanças...: toda chave estrangeira para `core.pessoa`, descoberta no
  catálogo, então tabela nova entra sozinha), completa os campos vazios de `manter` com os de `apagar` e apaga `apagar`.
  O mesmo mandato nos dois cadastros (mesmo cargo e início, ou a mesma chave natural) vira um só, e o que depende dele
  (presença, situação, partido) passa para o de `manter`. A linha de `apagar` que colidiria com uma de `manter` (mesma
  filiação, mesmo nome...) é descartada: vale a de `manter`. `core.mover_referencias` tenta mover a tabela inteira de
  uma vez e só volta linha a linha quando há colisão.
- `core.unificar_duplicadas()` acha os pares pelo legado: o cadastro do `uid` de cada político de `public.politicos` e o
  cadastro, que não é de outro político do legado, dono do seu ID da Câmara ou do Senado. Devolve quantos pares uniu.
  A sincronização do legado a chama depois de cada carga, até a Fase 9 tirar o legado; o novo ETL resolve a pessoa pelo
  identificador na carga e não cria a duplicata.

O `uid` público sobrevive: o cadastro mantido é o do legado. A migração já unifica o que existe.

Revision ID: 0034
Revises: 0033
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

MOVER_REFERENCIAS = """
CREATE FUNCTION core.mover_referencias(p_tabela regclass, p_de bigint, p_para bigint) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    fk record;
    linha tid;
BEGIN
    -- toda tabela comum (as partições, não a tabela particionada) com chave estrangeira de uma coluna para p_tabela
    FOR fk IN
        SELECT DISTINCT c.conrelid::regclass AS tabela, a.attname AS coluna
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid AND t.relkind = 'r'
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        WHERE c.contype = 'f' AND c.confrelid = p_tabela AND array_length(c.conkey, 1) = 1
    LOOP
        BEGIN
            EXECUTE format('UPDATE %s SET %I = $1 WHERE %I = $2', fk.tabela, fk.coluna, fk.coluna)
                USING p_para, p_de;
        EXCEPTION WHEN unique_violation OR exclusion_violation THEN
            -- colisão: linha a linha; a que colide com uma já existente em p_para é descartada
            FOR linha IN EXECUTE format('SELECT ctid FROM %s WHERE %I = $1', fk.tabela, fk.coluna) USING p_de
            LOOP
                BEGIN
                    EXECUTE format('UPDATE %s SET %I = $1 WHERE ctid = $2', fk.tabela, fk.coluna)
                        USING p_para, linha;
                EXCEPTION WHEN unique_violation OR exclusion_violation THEN
                    EXECUTE format('DELETE FROM %s WHERE ctid = $1', fk.tabela) USING linha;
                END;
            END LOOP;
        END;
    END LOOP;
END $$
"""

UNIFICAR_PESSOAS = """
CREATE FUNCTION core.unificar_pessoas(p_manter bigint, p_apagar bigint) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    mand record;
BEGIN
    IF p_manter = p_apagar THEN
        RETURN;
    END IF;
    -- o mesmo mandato nos dois cadastros (mesmo cargo e início, ou a mesma chave natural) vira um só: o que depende
    -- do mandato do cadastro a apagar (presença, situação, partido...) passa para o do cadastro mantido
    FOR mand IN
        SELECT DISTINCT ON (y.id) y.id AS de, x.id AS para
        FROM core.mandato y
        JOIN core.mandato x ON x.pessoa_id = p_manter AND x.cargo_id = y.cargo_id
         AND (x.inicio = y.inicio
              OR (x.eleicao_id IS NOT DISTINCT FROM y.eleicao_id AND x.numero_mandato = y.numero_mandato
                  AND x.orgao_nome IS NOT DISTINCT FROM y.orgao_nome))
        WHERE y.pessoa_id = p_apagar
        ORDER BY y.id, x.id
    LOOP
        PERFORM core.mover_referencias('core.mandato'::regclass, mand.de, mand.para);
        DELETE FROM core.mandato WHERE id = mand.de;
    END LOOP;

    PERFORM core.mover_referencias('core.pessoa'::regclass, p_apagar, p_manter);

    UPDATE core.pessoa m SET
        data_nascimento = coalesce(m.data_nascimento, d.data_nascimento),
        data_falecimento = coalesce(m.data_falecimento, d.data_falecimento),
        sexo = coalesce(m.sexo, d.sexo),
        municipio_nascimento = coalesce(m.municipio_nascimento, d.municipio_nascimento),
        uf_nascimento = coalesce(m.uf_nascimento, d.uf_nascimento),
        foto_midia_id = coalesce(m.foto_midia_id, d.foto_midia_id),
        biografia = coalesce(m.biografia, d.biografia),
        email = coalesce(m.email, d.email),
        gabinete_sala = coalesce(m.gabinete_sala, d.gabinete_sala),
        gabinete_telefone = coalesce(m.gabinete_telefone, d.gabinete_telefone),
        redes_sociais = coalesce(m.redes_sociais, d.redes_sociais)
    FROM core.pessoa d WHERE m.id = p_manter AND d.id = p_apagar;
    DELETE FROM core.pessoa WHERE id = p_apagar;
END $$
"""

UNIFICAR_DUPLICADAS = """
CREATE FUNCTION core.unificar_duplicadas() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    par record;
    unidos integer := 0;
BEGIN
    IF to_regclass('public.politicos') IS NULL THEN
        RETURN 0;
    END IF;
    FOR par IN
        SELECT DISTINCT x.id AS manter, i.pessoa_id AS apagar
        FROM public.politicos p
        JOIN core.pessoa x ON x.uid = p.id
        JOIN core.pessoa_identificador i
          ON (i.tipo = 'CAMARA_ID' AND i.valor = p."camaraId"::text)
          OR (i.tipo = 'SENADO_ID' AND i.valor = p."senadoId"::text)
        WHERE i.pessoa_id <> x.id
          AND NOT EXISTS (SELECT 1 FROM core.pessoa y JOIN public.politicos q ON q.id = y.uid WHERE y.id = i.pessoa_id)
        ORDER BY 1, 2
    LOOP
        -- o cadastro a apagar pode já ter sido unido a outro par (ID da Câmara e do Senado em cadastros diferentes)
        IF EXISTS (SELECT 1 FROM core.pessoa WHERE id = par.apagar)
           AND EXISTS (SELECT 1 FROM core.pessoa WHERE id = par.manter) THEN
            PERFORM core.unificar_pessoas(par.manter, par.apagar);
            unidos := unidos + 1;
        END IF;
    END LOOP;
    RETURN unidos;
END $$
"""


def upgrade() -> None:
    op.execute(MOVER_REFERENCIAS)
    op.execute(UNIFICAR_PESSOAS)
    op.execute(UNIFICAR_DUPLICADAS)
    op.execute("SELECT core.unificar_duplicadas()")


def downgrade() -> None:
    op.execute("DROP FUNCTION core.unificar_duplicadas()")
    op.execute("DROP FUNCTION core.unificar_pessoas(bigint, bigint)")
    op.execute("DROP FUNCTION core.mover_referencias(regclass, bigint, bigint)")
