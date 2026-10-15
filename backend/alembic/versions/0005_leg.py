"""Schema legislativo: proposição, autoria, votação unificada, voto, orientação e presença.

Unifica as duas representações legadas de votação (sessoes_votacao/votos_parlamentares e
votacoes_proposicao/votos_nominais) em leg.votacao/leg.voto. Janela de dados: a partir de 1995-01-01 (D8).

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TIPOS_PROPOSICAO = [
    ("PEC", "Proposta de Emenda à Constituição"),
    ("PL", "Projeto de Lei"),
    ("PLP", "Projeto de Lei Complementar"),
    ("MPV", "Medida Provisória"),
    ("PDL", "Projeto de Decreto Legislativo"),
    ("PR", "Projeto de Resolução"),
    ("PRC", "Projeto de Resolução do Congresso"),
    ("PDS", "Projeto de Decreto do Senado"),
    ("REQ", "Requerimento"),
    ("INC", "Indicação"),
    ("DECRETO_PRES", "Decreto Presidencial"),
    ("LEI_DELEGADA", "Lei Delegada"),
]
STATUS_TRAMITACAO = [
    ("APROVADA_E_SANCIONADA", "Aprovada e sancionada"),
    ("APROVADA_E_PROMULGADA", "Aprovada e promulgada"),
    ("APROVADO_PLENARIO", "Aprovada no plenário"),
    ("APROVADO_COMISSAO", "Aprovada em comissão"),
    ("VETADA_TOTAL", "Vetada totalmente"),
    ("VETADA_PARCIAL", "Vetada parcialmente"),
    ("REJEITADA", "Rejeitada"),
    ("EM_TRAMITACAO", "Em tramitação"),
    ("ARQUIVADA", "Arquivada"),
]
OPCOES_VOTO = [
    ("SIM", "Sim", True),
    ("NAO", "Não", True),
    ("ABSTENCAO", "Abstenção", True),
    ("OBSTRUCAO", "Obstrução", True),
    ("AUSENTE", "Ausente", False),
    ("ARTIGO_17", "Art. 17", False),
]
TIPOS_AUTORIA = ["AUTOR_PRINCIPAL", "RELATOR", "COAUTOR", "INSTITUCIONAL"]
TIPOS_DELIBERACAO = [
    ("COMISSAO", "Deliberação em comissão"),
    ("SIMBOLICA", "Votação simbólica"),
    ("NOMINAL", "Votação nominal"),
    ("SECRETA", "Votação secreta (apenas totais)"),
]
TIPOS_PRESENCA = [
    ("PRESENTE", True),
    ("AUSENCIA_JUSTIFICADA", False),
    ("AUSENCIA_NAO_JUSTIFICADA", False),
    ("LICENCA_MEDICA", False),
    ("MISSAO_OFICIAL", False),
]
ANO_INICIAL, ANO_FINAL = 1995, 2035


def _q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS leg")

    # ── referência ───────────────────────────────────────────────────────────────────────────────
    op.execute("CREATE TABLE ref.tipo_proposicao (codigo text PRIMARY KEY, nome text NOT NULL)")
    op.execute("CREATE TABLE ref.status_tramitacao (codigo text PRIMARY KEY, nome text NOT NULL)")
    op.execute(
        "CREATE TABLE ref.opcao_voto (codigo text PRIMARY KEY, rotulo text NOT NULL, tem_posicao boolean NOT NULL)"
    )
    op.execute("CREATE TABLE ref.tipo_autoria (codigo text PRIMARY KEY)")
    op.execute("CREATE TABLE ref.tipo_deliberacao (codigo text PRIMARY KEY, nome text NOT NULL)")
    op.execute("CREATE TABLE ref.tipo_presenca (codigo text PRIMARY KEY, presente boolean NOT NULL)")
    for codigo, nome in TIPOS_PROPOSICAO:
        op.execute(f"INSERT INTO ref.tipo_proposicao VALUES ({_q(codigo)}, {_q(nome)})")
    for codigo, nome in STATUS_TRAMITACAO:
        op.execute(f"INSERT INTO ref.status_tramitacao VALUES ({_q(codigo)}, {_q(nome)})")
    for codigo, rotulo, posicao in OPCOES_VOTO:
        op.execute(f"INSERT INTO ref.opcao_voto VALUES ({_q(codigo)}, {_q(rotulo)}, {str(posicao).upper()})")
    for codigo in TIPOS_AUTORIA:
        op.execute(f"INSERT INTO ref.tipo_autoria VALUES ({_q(codigo)})")
    for codigo, nome in TIPOS_DELIBERACAO:
        op.execute(f"INSERT INTO ref.tipo_deliberacao VALUES ({_q(codigo)}, {_q(nome)})")
    for codigo, presente in TIPOS_PRESENCA:
        op.execute(f"INSERT INTO ref.tipo_presenca VALUES ({_q(codigo)}, {str(presente).upper()})")

    # ── proposição e autoria ─────────────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE leg.proposicao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            id_camara integer UNIQUE,
            id_senado integer UNIQUE,
            tipo_codigo text NOT NULL REFERENCES ref.tipo_proposicao(codigo),
            numero integer NOT NULL,
            ano smallint NOT NULL CHECK (ano >= 1995),
            titulo text NOT NULL,
            ementa text NOT NULL,
            explicacao_ementa text,
            area_tematica text,
            data_apresentacao date NOT NULL CHECK (data_apresentacao >= DATE '1995-01-01'),
            data_sancao_promulgacao date,
            status_codigo text NOT NULL REFERENCES ref.status_tramitacao(codigo),
            url_texto_original text,
            url_oficial text,
            reforma_estrutural boolean NOT NULL DEFAULT false,
            iniciativa_executivo boolean NOT NULL DEFAULT false,
            autor_pessoa_id bigint REFERENCES core.pessoa(id),
            autor_nome text,
            eixo_impacto text,
            eixos_impacto text,
            ementa_tsv tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', coalesce(ementa, ''))) STORED,
            fonte_id smallint REFERENCES etl.fonte(id),
            criado_em timestamptz NOT NULL DEFAULT now(),
            atualizado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_proposicao_tipo_num_ano ON leg.proposicao (tipo_codigo, numero, ano)")
    op.execute("CREATE INDEX ix_proposicao_ano ON leg.proposicao (ano)")
    op.execute("CREATE INDEX ix_proposicao_autor ON leg.proposicao (autor_pessoa_id)")
    op.execute("CREATE INDEX ix_proposicao_ementa_tsv ON leg.proposicao USING gin (ementa_tsv)")
    op.execute(
        "CREATE TRIGGER trg_proposicao_atualizado BEFORE UPDATE ON leg.proposicao "
        "FOR EACH ROW EXECUTE FUNCTION core.touch_atualizado_em()"
    )

    op.execute(
        """
        CREATE TABLE leg.autoria (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            proposicao_id bigint NOT NULL REFERENCES leg.proposicao(id) ON DELETE CASCADE,
            pessoa_id bigint REFERENCES core.pessoa(id),
            nome_autor text NOT NULL,
            tipo_codigo text NOT NULL REFERENCES ref.tipo_autoria(codigo),
            ordem integer NOT NULL DEFAULT 1,
            legado_id uuid UNIQUE
        )
        """
    )
    op.execute("CREATE INDEX ix_autoria_pessoa_tipo ON leg.autoria (pessoa_id, tipo_codigo)")
    op.execute("CREATE INDEX ix_autoria_proposicao_ordem ON leg.autoria (proposicao_id, ordem)")

    # ── votação unificada ────────────────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE leg.votacao (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            uid uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            id_externo text UNIQUE,
            proposicao_id bigint NOT NULL REFERENCES leg.proposicao(id) ON DELETE CASCADE,
            casa_id smallint REFERENCES ref.casa_legislativa(id),
            data_hora timestamptz NOT NULL CHECK (data_hora >= TIMESTAMPTZ '1995-01-01'),
            titulo_pauta text,
            descricao text,
            tipo_deliberacao text NOT NULL REFERENCES ref.tipo_deliberacao(codigo),
            secreta boolean NOT NULL DEFAULT false,
            aprovada boolean NOT NULL,
            local_deliberacao text,
            nome_comissao text,
            link_ata text,
            relator_nome text,
            parecer_numero text,
            parecer_texto text,
            link_parecer text,
            resumo_decisao text,
            orientacao_governo text,
            -- placar informado pela fonte quando não há voto nominal (votação simbólica, secreta ou em comissão)
            total_sim_fonte integer,
            total_nao_fonte integer,
            total_abstencao_fonte integer,
            total_obstrucao_fonte integer,
            fonte_id smallint REFERENCES etl.fonte(id),
            criado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_votacao_proposicao ON leg.votacao (proposicao_id)")
    op.execute("CREATE INDEX ix_votacao_data ON leg.votacao USING brin (data_hora)")
    op.execute("CREATE INDEX ix_votacao_tipo ON leg.votacao (tipo_deliberacao)")

    op.execute(
        """
        CREATE TABLE leg.voto (
            votacao_id bigint NOT NULL REFERENCES leg.votacao(id) ON DELETE CASCADE,
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id),
            partido_id bigint REFERENCES core.partido(id),
            opcao_codigo text NOT NULL REFERENCES ref.opcao_voto(codigo),
            PRIMARY KEY (votacao_id, pessoa_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_voto_pessoa ON leg.voto (pessoa_id)")
    op.execute("CREATE INDEX ix_voto_partido ON leg.voto (partido_id)")
    op.execute("CREATE INDEX ix_voto_opcao ON leg.voto (opcao_codigo)")

    op.execute(
        """
        CREATE TABLE leg.orientacao (
            votacao_id bigint NOT NULL REFERENCES leg.votacao(id) ON DELETE CASCADE,
            bancada text NOT NULL,
            partido_id bigint REFERENCES core.partido(id),
            orientacao text NOT NULL CHECK (orientacao IN ('SIM','NAO','ABSTENCAO','OBSTRUCAO','LIBERADO')),
            PRIMARY KEY (votacao_id, bancada)
        )
        """
    )
    op.execute("CREATE INDEX ix_orientacao_partido ON leg.orientacao (partido_id)")

    op.execute(
        """
        CREATE TABLE leg.votacao_legado (
            legado_id uuid NOT NULL,
            tabela text NOT NULL CHECK (tabela IN ('sessoes_votacao','votacoes_proposicao')),
            votacao_id bigint NOT NULL REFERENCES leg.votacao(id) ON DELETE CASCADE,
            PRIMARY KEY (tabela, legado_id)
        )
        """
    )

    # ── presença (particionada por ano) ──────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE leg.presenca (
            pessoa_id bigint NOT NULL REFERENCES core.pessoa(id),
            casa_id smallint NOT NULL REFERENCES ref.casa_legislativa(id),
            data_sessao date NOT NULL CHECK (data_sessao >= DATE '1995-01-01'),
            tipo_codigo text NOT NULL REFERENCES ref.tipo_presenca(codigo),
            mandato_id bigint REFERENCES core.mandato(id),
            justificativa text,
            PRIMARY KEY (pessoa_id, casa_id, data_sessao)
        ) PARTITION BY RANGE (data_sessao)
        """
    )
    for ano in range(ANO_INICIAL, ANO_FINAL + 1):
        op.execute(
            f"CREATE TABLE leg.presenca_{ano} PARTITION OF leg.presenca "
            f"FOR VALUES FROM ('{ano}-01-01') TO ('{ano + 1}-01-01')"
        )
    op.execute("CREATE INDEX ix_presenca_data ON leg.presenca (data_sessao)")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS leg CASCADE")
    for tabela in (
        "tipo_presenca",
        "tipo_deliberacao",
        "tipo_autoria",
        "opcao_voto",
        "status_tramitacao",
        "tipo_proposicao",
    ):
        op.execute(f"DROP TABLE IF EXISTS ref.{tabela}")
