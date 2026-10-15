"""Schemas, extensões, referência (UF, cargos, circunscrições), controle de ETL e parâmetros de metodologia.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UFS = [
    ("AC", "Acre", "NORTE", 12),
    ("AL", "Alagoas", "NORDESTE", 27),
    ("AP", "Amapá", "NORTE", 16),
    ("AM", "Amazonas", "NORTE", 13),
    ("BA", "Bahia", "NORDESTE", 29),
    ("CE", "Ceará", "NORDESTE", 23),
    ("DF", "Distrito Federal", "CENTRO_OESTE", 53),
    ("ES", "Espírito Santo", "SUDESTE", 32),
    ("GO", "Goiás", "CENTRO_OESTE", 52),
    ("MA", "Maranhão", "NORDESTE", 21),
    ("MT", "Mato Grosso", "CENTRO_OESTE", 51),
    ("MS", "Mato Grosso do Sul", "CENTRO_OESTE", 50),
    ("MG", "Minas Gerais", "SUDESTE", 31),
    ("PA", "Pará", "NORTE", 15),
    ("PB", "Paraíba", "NORDESTE", 25),
    ("PR", "Paraná", "SUL", 41),
    ("PE", "Pernambuco", "NORDESTE", 26),
    ("PI", "Piauí", "NORDESTE", 22),
    ("RJ", "Rio de Janeiro", "SUDESTE", 33),
    ("RN", "Rio Grande do Norte", "NORDESTE", 24),
    ("RS", "Rio Grande do Sul", "SUL", 43),
    ("RO", "Rondônia", "NORTE", 11),
    ("RR", "Roraima", "NORTE", 14),
    ("SC", "Santa Catarina", "SUL", 42),
    ("SP", "São Paulo", "SUDESTE", 35),
    ("SE", "Sergipe", "NORDESTE", 28),
    ("TO", "Tocantins", "NORTE", 17),
]

# (codigo, nome, poder, esfera, casa_tipo, eletivo, sistema, duracao_anos, titular, ordem)
CARGOS = [
    ("PRESIDENTE", "Presidente da República", "EXECUTIVO", "FEDERAL", None, True, "MAJORITARIO", 4, None, 1),
    (
        "VICE_PRESIDENTE",
        "Vice-Presidente da República",
        "EXECUTIVO",
        "FEDERAL",
        None,
        True,
        "MAJORITARIO",
        4,
        "PRESIDENTE",
        2,
    ),
    ("MINISTRO_DE_ESTADO", "Ministro de Estado", "EXECUTIVO", "FEDERAL", None, False, None, None, None, 3),
    ("SENADOR", "Senador", "LEGISLATIVO", "FEDERAL", "SENADO", True, "MAJORITARIO", 8, None, 4),
    ("DEPUTADO_FEDERAL", "Deputado Federal", "LEGISLATIVO", "FEDERAL", "CAMARA", True, "PROPORCIONAL", 4, None, 5),
    ("GOVERNADOR", "Governador", "EXECUTIVO", "ESTADUAL", None, True, "MAJORITARIO", 4, None, 6),
    ("VICE_GOVERNADOR", "Vice-Governador", "EXECUTIVO", "ESTADUAL", None, True, "MAJORITARIO", 4, "GOVERNADOR", 7),
    ("SECRETARIO_ESTADUAL", "Secretário Estadual", "EXECUTIVO", "ESTADUAL", None, False, None, None, None, 8),
    (
        "DEPUTADO_ESTADUAL",
        "Deputado Estadual",
        "LEGISLATIVO",
        "ESTADUAL",
        "ASSEMBLEIA",
        True,
        "PROPORCIONAL",
        4,
        None,
        9,
    ),
    (
        "DEPUTADO_DISTRITAL",
        "Deputado Distrital",
        "LEGISLATIVO",
        "DISTRITAL",
        "ASSEMBLEIA",
        True,
        "PROPORCIONAL",
        4,
        None,
        10,
    ),
]

FONTES = [
    (
        "CAMARA_API",
        "API de Dados Abertos da Câmara (v2)",
        "Câmara dos Deputados",
        "https://dadosabertos.camara.leg.br/api/v2",
        "JSON",
        "DIARIA",
    ),
    (
        "CAMARA_CSV",
        "Arquivos anuais em lote da Câmara",
        "Câmara dos Deputados",
        "https://dadosabertos.camara.leg.br/arquivos/",
        "CSV",
        "DIARIA",
    ),
    (
        "CAMARA_PORTAL",
        "Portal da Câmara (presença e remuneração)",
        "Câmara dos Deputados",
        "https://www.camara.leg.br/deputados/",
        "HTML",
        "DIARIA",
    ),
    (
        "SENADO_API",
        "API de Dados Abertos do Senado",
        "Senado Federal",
        "https://legis.senado.leg.br/dadosabertos",
        "JSON",
        "DIARIA",
    ),
    (
        "TSE",
        "Dados Abertos do TSE",
        "Tribunal Superior Eleitoral",
        "https://dadosabertos.tse.jus.br/dataset/",
        "CSV",
        "POR_ELEICAO",
    ),
    (
        "PORTAL_TRANSPARENCIA",
        "Portal da Transparência",
        "Controladoria-Geral da União",
        "https://portaldatransparencia.gov.br/download-de-dados/",
        "CSV",
        "MENSAL",
    ),
    (
        "BCB_SGS",
        "Sistema Gerenciador de Séries Temporais",
        "Banco Central do Brasil",
        "https://api.bcb.gov.br/dados/serie/",
        "JSON",
        "DIARIA",
    ),
    (
        "IBGE_SIDRA",
        "SIDRA / API de Agregados",
        "IBGE",
        "https://servicodados.ibge.gov.br/api/v3/agregados",
        "JSON",
        "TRIMESTRAL",
    ),
    (
        "DATAJUD",
        "API Pública do DataJud",
        "Conselho Nacional de Justiça",
        "https://api-publica.datajud.cnj.jus.br/",
        "JSON",
        "DIARIA",
    ),
    ("CURADORIA", "Curadoria manual do projeto", "LegisData", None, "MANUAL", "SOB_DEMANDA"),
    ("LEGADO", "Schema legado (public) do LegisData", "LegisData", None, "SQL", "UNICA"),
]


def _q(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def upgrade() -> None:
    for schema in ("ref", "core", "param", "etl", "stg", "api"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    for extension in ("btree_gist", "pg_trgm", "unaccent"):
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension} SCHEMA public")

    # unaccent() não é IMMUTABLE: o invólucro permite colunas geradas e índices sobre nomes normalizados
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ref.normalizar_texto(texto text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS $$
            SELECT lower(btrim(regexp_replace(public.unaccent('public.unaccent'::regdictionary, texto), '\\s+', ' ', 'g')))
        $$
        """
    )

    # ── ref ──────────────────────────────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE ref.uf (
            sigla char(2) PRIMARY KEY,
            nome text NOT NULL,
            regiao text NOT NULL CHECK (regiao IN ('NORTE','NORDESTE','CENTRO_OESTE','SUDESTE','SUL')),
            codigo_ibge smallint NOT NULL UNIQUE
        )
        """
    )
    values = ", ".join(f"({_q(s)}, {_q(n)}, {_q(r)}, {c})" for s, n, r, c in UFS)
    op.execute(f"INSERT INTO ref.uf (sigla, nome, regiao, codigo_ibge) VALUES {values}")

    op.execute(
        """
        CREATE TABLE ref.casa_legislativa (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codigo text NOT NULL UNIQUE,
            nome text NOT NULL,
            tipo text NOT NULL CHECK (tipo IN ('CAMARA','SENADO','ASSEMBLEIA','CONGRESSO')),
            esfera text NOT NULL CHECK (esfera IN ('FEDERAL','ESTADUAL','DISTRITAL','MUNICIPAL')),
            uf char(2) REFERENCES ref.uf(sigla)
        )
        """
    )
    op.execute(
        """
        INSERT INTO ref.casa_legislativa (codigo, nome, tipo, esfera, uf) VALUES
            ('CAMARA_DOS_DEPUTADOS', 'Câmara dos Deputados', 'CAMARA', 'FEDERAL', NULL),
            ('SENADO_FEDERAL', 'Senado Federal', 'SENADO', 'FEDERAL', NULL),
            ('CONGRESSO_NACIONAL', 'Congresso Nacional', 'CONGRESSO', 'FEDERAL', NULL)
        """
    )
    op.execute(
        """
        INSERT INTO ref.casa_legislativa (codigo, nome, tipo, esfera, uf)
        SELECT CASE WHEN sigla = 'DF' THEN 'CLDF' ELSE 'AL_' || sigla END,
               CASE WHEN sigla = 'DF' THEN 'Câmara Legislativa do Distrito Federal'
                    ELSE 'Assembleia Legislativa de ' || nome END,
               'ASSEMBLEIA',
               CASE WHEN sigla = 'DF' THEN 'DISTRITAL' ELSE 'ESTADUAL' END,
               sigla
        FROM ref.uf
        """
    )

    op.execute(
        """
        CREATE TABLE ref.cargo (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codigo text NOT NULL UNIQUE,
            nome text NOT NULL,
            poder text NOT NULL CHECK (poder IN ('EXECUTIVO','LEGISLATIVO')),
            esfera text NOT NULL CHECK (esfera IN ('FEDERAL','ESTADUAL','DISTRITAL','MUNICIPAL')),
            casa_tipo text CHECK (casa_tipo IN ('CAMARA','SENADO','ASSEMBLEIA')),
            eletivo boolean NOT NULL,
            sistema_eleitoral text CHECK (sistema_eleitoral IN ('MAJORITARIO','PROPORCIONAL')),
            duracao_anos smallint CHECK (duracao_anos > 0),
            cargo_titular_id smallint REFERENCES ref.cargo(id),
            ordem smallint NOT NULL,
            CHECK (poder = 'LEGISLATIVO' OR casa_tipo IS NULL),
            CHECK (eletivo OR sistema_eleitoral IS NULL)
        )
        """
    )
    for codigo, nome, poder, esfera, casa, eletivo, sistema, duracao, titular, ordem in CARGOS:
        titular_sql = f"(SELECT id FROM ref.cargo WHERE codigo = {_q(titular)})" if titular else "NULL"
        op.execute(
            "INSERT INTO ref.cargo (codigo, nome, poder, esfera, casa_tipo, eletivo, sistema_eleitoral, duracao_anos,"
            f" cargo_titular_id, ordem) VALUES ({_q(codigo)}, {_q(nome)}, {_q(poder)}, {_q(esfera)}, {_q(casa)},"
            f" {_q(eletivo)}, {_q(sistema)}, {_q(duracao)}, {titular_sql}, {ordem})"
        )

    op.execute(
        """
        CREATE TABLE ref.circunscricao (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            tipo text NOT NULL CHECK (tipo IN ('BR','UF')),
            uf char(2) REFERENCES ref.uf(sigla),
            CHECK ((tipo = 'BR' AND uf IS NULL) OR (tipo = 'UF' AND uf IS NOT NULL)),
            UNIQUE NULLS NOT DISTINCT (tipo, uf)
        )
        """
    )
    op.execute("INSERT INTO ref.circunscricao (tipo, uf) VALUES ('BR', NULL)")
    op.execute("INSERT INTO ref.circunscricao (tipo, uf) SELECT 'UF', sigla FROM ref.uf")

    # ── etl ──────────────────────────────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE etl.fonte (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codigo text NOT NULL UNIQUE,
            nome text NOT NULL,
            orgao text NOT NULL,
            url_base text,
            formato text NOT NULL,
            periodicidade text NOT NULL,
            licenca text,
            exige_autenticacao boolean NOT NULL DEFAULT false,
            observacao text
        )
        """
    )
    for codigo, nome, orgao, url, formato, periodicidade in FONTES:
        op.execute(
            "INSERT INTO etl.fonte (codigo, nome, orgao, url_base, formato, periodicidade) VALUES "
            f"({_q(codigo)}, {_q(nome)}, {_q(orgao)}, {_q(url)}, {_q(formato)}, {_q(periodicidade)})"
        )
    op.execute(
        """
        CREATE TABLE etl.execucao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fonte_id smallint REFERENCES etl.fonte(id),
            estagio text NOT NULL CHECK (estagio IN ('EXTRAIR','CARREGAR','MERGE','DERIVAR','VALIDAR','TUDO','LEGADO')),
            iniciado_em timestamptz NOT NULL DEFAULT now(),
            finalizado_em timestamptz,
            status text NOT NULL DEFAULT 'EXECUTANDO' CHECK (status IN ('EXECUTANDO','OK','COM_ALERTA','ERRO')),
            linhas_lidas integer,
            linhas_gravadas integer,
            linhas_rejeitadas integer,
            parametros jsonb,
            erro text
        )
        """
    )
    op.execute(
        """
        CREATE TABLE etl.arquivo_bruto (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            execucao_id bigint REFERENCES etl.execucao(id),
            url text NOT NULL,
            parametros jsonb,
            sha256 char(64) NOT NULL,
            bytes bigint NOT NULL,
            http_status smallint,
            caminho text NOT NULL,
            baixado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (fonte_id, sha256)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE etl.rejeito (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            execucao_id bigint REFERENCES etl.execucao(id),
            recurso text NOT NULL,
            chave_natural text,
            motivo text NOT NULL,
            payload jsonb,
            criado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE etl.verificacao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            execucao_id bigint REFERENCES etl.execucao(id),
            nome text NOT NULL,
            passou boolean NOT NULL,
            detalhe jsonb,
            criado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    # ── param ────────────────────────────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE param.metodologia (
            id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            codigo text NOT NULL,
            versao smallint NOT NULL,
            descricao text,
            vigente_de date NOT NULL DEFAULT current_date,
            vigente_ate date,
            UNIQUE (codigo, versao)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE param.peso (
            metodologia_id smallint NOT NULL REFERENCES param.metodologia(id) ON DELETE CASCADE,
            dimensao text NOT NULL,
            chave text NOT NULL,
            valor numeric(12,4) NOT NULL,
            PRIMARY KEY (metodologia_id, dimensao, chave)
        )
        """
    )


def downgrade() -> None:
    for schema in ("param", "etl", "ref"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
