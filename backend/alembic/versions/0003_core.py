"""Núcleo de identidade e vida política: mídia, pessoa, partido, filiação, eleição, mandato e situações.

Decisões: sem CPF (D3); chaves bigint + uid público (D2); períodos como daterange com EXCLUDE (sem sobreposição).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION core.touch_atualizado_em() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.atualizado_em = now();
            RETURN NEW;
        END $$
        """
    )

    op.execute(
        """
        CREATE TABLE core.midia (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tipo text NOT NULL CHECK (tipo IN ('LOGO_PARTIDO','FOTO_PESSOA')),
            url_origem text NOT NULL,
            sha256 char(64),
            caminho text,
            mime text,
            largura integer,
            altura integer,
            licenca text,
            fonte_id smallint REFERENCES etl.fonte(id),
            baixada_em timestamptz,
            UNIQUE (tipo, url_origem)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE core.pessoa (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            nome_exibicao text NOT NULL,
            data_nascimento date,
            data_falecimento date,
            sexo text,
            municipio_nascimento text,
            uf_nascimento char(2) REFERENCES ref.uf(sigla),
            foto_midia_id bigint REFERENCES core.midia(id),
            biografia text,
            email text,
            gabinete_sala text,
            gabinete_telefone text,
            redes_sociais jsonb,
            possui_processos_declarados boolean NOT NULL DEFAULT false,
            criado_em timestamptz NOT NULL DEFAULT now(),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            CHECK (data_falecimento IS NULL OR data_nascimento IS NULL OR data_falecimento >= data_nascimento)
        )
        """
    )
    op.execute("CREATE INDEX ix_pessoa_nome_exibicao ON core.pessoa (ref.normalizar_texto(nome_exibicao))")
    op.execute(
        "CREATE TRIGGER trg_pessoa_atualizado BEFORE UPDATE ON core.pessoa "
        "FOR EACH ROW EXECUTE FUNCTION core.touch_atualizado_em()"
    )

    op.execute(
        """
        CREATE TABLE core.pessoa_nome (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            tipo text NOT NULL CHECK (tipo IN ('CIVIL','ELEITORAL','PARLAMENTAR','HISTORICO','GRAFIA_FONTE')),
            nome text NOT NULL,
            nome_normalizado text GENERATED ALWAYS AS (ref.normalizar_texto(nome)) STORED,
            fonte_id smallint REFERENCES etl.fonte(id),
            vigencia daterange,
            UNIQUE (pessoa_id, tipo, nome_normalizado)
        )
        """
    )
    op.execute("CREATE INDEX ix_pessoa_nome_trgm ON core.pessoa_nome USING gin (nome_normalizado gin_trgm_ops)")
    op.execute("CREATE INDEX ix_pessoa_nome_pessoa ON core.pessoa_nome (pessoa_id)")

    # Sem CPF: decisão D3. O tipo de identificador é um conjunto fechado de ids públicos das fontes oficiais.
    op.execute(
        """
        CREATE TABLE core.pessoa_identificador (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            tipo text NOT NULL CHECK (tipo IN ('CAMARA_ID','SENADO_ID','TSE_ID','DATAJUD_ID')),
            valor text NOT NULL,
            confianca numeric(3,2) NOT NULL DEFAULT 1.00 CHECK (confianca BETWEEN 0 AND 1),
            verificado_por text NOT NULL DEFAULT 'AUTOMATICO' CHECK (verificado_por IN ('AUTOMATICO','MANUAL')),
            criado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (fonte_id, tipo, valor)
        )
        """
    )
    op.execute("CREATE INDEX ix_pessoa_identificador_pessoa ON core.pessoa_identificador (pessoa_id)")

    op.execute(
        """
        CREATE TABLE core.pessoa_candidata_duplicidade (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_a_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            pessoa_b_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            similaridade numeric(4,3) NOT NULL,
            motivo text NOT NULL,
            situacao text NOT NULL DEFAULT 'PENDENTE' CHECK (situacao IN ('PENDENTE','MESMA_PESSOA','PESSOAS_DISTINTAS')),
            decidido_em timestamptz,
            CHECK (pessoa_a_id < pessoa_b_id),
            UNIQUE (pessoa_a_id, pessoa_b_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE core.partido (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            sigla text NOT NULL UNIQUE,
            sigla_normalizada text GENERATED ALWAYS AS (ref.normalizar_texto(sigla)) STORED UNIQUE,
            nome text NOT NULL,
            numero_eleitoral integer UNIQUE,
            data_fundacao date,
            data_extincao date,
            cor_hex char(7) CHECK (cor_hex ~ '^#[0-9a-fA-F]{6}$'),
            logo_midia_id bigint REFERENCES core.midia(id),
            ideologia_texto text,
            lema text,
            criado_em timestamptz NOT NULL DEFAULT now(),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            CHECK (data_extincao IS NULL OR data_fundacao IS NULL OR data_extincao >= data_fundacao)
        )
        """
    )
    op.execute(
        "CREATE TRIGGER trg_partido_atualizado BEFORE UPDATE ON core.partido "
        "FOR EACH ROW EXECUTE FUNCTION core.touch_atualizado_em()"
    )

    op.execute(
        """
        CREATE TABLE core.partido_alias (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            partido_id bigint NOT NULL REFERENCES core.partido(id) ON DELETE CASCADE,
            sigla_alias text NOT NULL,
            sigla_normalizada text GENERATED ALWAYS AS (ref.normalizar_texto(sigla_alias)) STORED UNIQUE,
            tipo text NOT NULL CHECK (tipo IN ('SIGLA_ANTIGA','GRAFIA_FONTE')),
            vigencia daterange
        )
        """
    )
    op.execute(
        """
        CREATE TABLE core.partido_sucessao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            partido_origem_id bigint NOT NULL REFERENCES core.partido(id) ON DELETE CASCADE,
            partido_destino_id bigint NOT NULL REFERENCES core.partido(id) ON DELETE CASCADE,
            tipo text NOT NULL CHECK (tipo IN ('RENOMEACAO','FUSAO','INCORPORACAO','SUCESSAO')),
            data date,
            fonte_id smallint REFERENCES etl.fonte(id),
            CHECK (partido_origem_id <> partido_destino_id),
            UNIQUE (partido_origem_id, partido_destino_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE core.partido_posicao_ideologica (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            partido_id bigint NOT NULL REFERENCES core.partido(id) ON DELETE CASCADE,
            escala text NOT NULL CHECK (escala IN ('ESPECTRO_5','ESCALA_1_10')),
            espectro text CHECK (espectro IN ('ESQUERDA','CENTRO_ESQUERDA','CENTRO','CENTRO_DIREITA','DIREITA')),
            valor numeric(4,2) CHECK (valor BETWEEN 1 AND 10),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            ano_referencia smallint,
            observacao text,
            CHECK ((escala = 'ESPECTRO_5' AND espectro IS NOT NULL AND valor IS NULL)
                   OR (escala = 'ESCALA_1_10' AND valor IS NOT NULL AND espectro IS NULL)),
            UNIQUE NULLS NOT DISTINCT (partido_id, escala, fonte_id, ano_referencia)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE core.eleicao (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            ano smallint NOT NULL,
            tipo text NOT NULL CHECK (tipo IN ('GERAL','MUNICIPAL')),
            data_primeiro_turno date,
            UNIQUE (ano, tipo)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE core.filiacao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            partido_id bigint NOT NULL REFERENCES core.partido(id),
            periodo daterange NOT NULL CHECK (NOT isempty(periodo) AND NOT lower_inf(periodo)),
            fim_inferido boolean NOT NULL DEFAULT false,
            motivo_saida text CHECK (motivo_saida IN ('MUDANCA_VOLUNTARIA','FUSAO_OU_INCORPORACAO','EXPULSAO',
                                                      'CRIACAO_DE_NOVA_LEGENDA','EXTINCAO_DO_PARTIDO')),
            uf char(2) REFERENCES ref.uf(sigla),
            fonte_id smallint REFERENCES etl.fonte(id),
            EXCLUDE USING gist (pessoa_id WITH =, periodo WITH &&)
        )
        """
    )
    op.execute("CREATE INDEX ix_filiacao_partido ON core.filiacao (partido_id)")
    op.execute("CREATE INDEX ix_filiacao_aberta ON core.filiacao (partido_id) WHERE upper_inf(periodo)")

    op.execute(
        """
        CREATE TABLE core.mandato (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id) ON DELETE CASCADE,
            cargo_id smallint NOT NULL REFERENCES ref.cargo(id),
            circunscricao_id smallint NOT NULL REFERENCES ref.circunscricao(id),
            eleicao_id smallint REFERENCES core.eleicao(id),
            partido_id bigint REFERENCES core.partido(id),  -- partido vigente na posse
            condicao text NOT NULL DEFAULT 'TITULAR' CHECK (condicao IN ('TITULAR','SUPLENTE','NOMEADO')),
            numero_mandato smallint NOT NULL DEFAULT 1,
            inicio date NOT NULL,
            fim date,
            motivo_encerramento text CHECK (motivo_encerramento IN ('CONCLUIDO','RENUNCIA','IMPEACHMENT','CASSACAO',
                                                                    'FALECIMENTO')),
            votos integer,
            percentual_votos numeric(5,2),
            coligacao text,
            orgao_nome text,
            funcao_destaque text,
            nomeado_por_mandato_id bigint REFERENCES core.mandato(id),
            fonte_id smallint REFERENCES etl.fonte(id),
            criado_em timestamptz NOT NULL DEFAULT now(),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            CHECK (fim IS NULL OR fim >= inicio),
            CONSTRAINT uq_mandato_natural
                UNIQUE NULLS NOT DISTINCT (pessoa_id, cargo_id, eleicao_id, numero_mandato, orgao_nome)
        )
        """
    )
    # Ponte transitória: ids do schema legado (mandatos e membros_gabinete) -> mandato novo.
    # Vários mandatos legados (um por partido) colapsam em um único mandato novo.
    op.execute(
        """
        CREATE TABLE core.mandato_legado (
            legado_id uuid PRIMARY KEY,
            tabela text NOT NULL CHECK (tabela IN ('mandatos','membros_gabinete')),
            mandato_id bigint NOT NULL REFERENCES core.mandato(id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX ix_mandato_legado_mandato ON core.mandato_legado (mandato_id)")
    op.execute("CREATE INDEX ix_mandato_pessoa ON core.mandato (pessoa_id)")
    op.execute("CREATE INDEX ix_mandato_partido ON core.mandato (partido_id)")
    op.execute("CREATE INDEX ix_mandato_cargo_inicio ON core.mandato (cargo_id, inicio)")
    op.execute(
        "CREATE TRIGGER trg_mandato_atualizado BEFORE UPDATE ON core.mandato "
        "FOR EACH ROW EXECUTE FUNCTION core.touch_atualizado_em()"
    )

    op.execute(
        """
        CREATE TABLE core.mandato_situacao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            mandato_id bigint NOT NULL REFERENCES core.mandato(id) ON DELETE CASCADE,
            situacao text NOT NULL CHECK (situacao IN ('EXERCICIO','AFASTADO_MINISTERIO','LICENCA','SUPLENCIA')),
            periodo daterange NOT NULL CHECK (NOT isempty(periodo) AND NOT lower_inf(periodo)),
            motivo text,
            substituto_mandato_id bigint REFERENCES core.mandato(id),
            fonte_id smallint REFERENCES etl.fonte(id),
            EXCLUDE USING gist (mandato_id WITH =, periodo WITH &&)
        )
        """
    )
    op.execute("CREATE INDEX ix_mandato_situacao_mandato ON core.mandato_situacao (mandato_id)")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS core CASCADE")
