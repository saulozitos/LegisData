"""Cobertura de proposições: tipos, situações da Câmara, entidades autoras, pesos IALP v3 e staging.

- ref: novos tipos de proposição (iniciativas legislativas da Câmara), status SEM_INFORMACAO e o mapa
  situação da Câmara -> status de tramitação (dado, não código). Situação sem mapa vira etl.rejeito.
- core.entidade: autores que não são pessoas (Poder Executivo, comissões, Mesa, liderança...) passam a ser
  registrados; leg.autoria ganha entidade, partido do autor (na data, segundo a fonte) e UF.
- IALP v3 = v2 + pesos dos novos tipos/status + peso reduzido para assinatura de apoio de quórum em PEC (0,05).
- stg.camara_*: tabelas de staging dos CSV anuais da Câmara.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

NOVOS_TIPOS = [
    ("PLN", "Projeto de Lei do Congresso Nacional", 2.0),
    ("PLS", "Projeto de Lei do Senado Federal", 2.0),
    ("PLC", "Projeto de Lei da Câmara dos Deputados (SF)", 2.0),
    ("PDC", "Projeto de Decreto Legislativo de Concessão/Renovação de Rádio e TV", 1.0),
    ("PDN", "Projeto de Decreto Legislativo (CN)", 1.0),
    ("PRN", "Projeto de Resolução do Congresso Nacional", 1.0),
    ("RIC", "Requerimento de Informação", 0.1),
    ("RCP", "Requerimento de Instituição de CPI", 0.1),
    ("RQC", "Requerimento de Convocação", 0.1),
]
PESO_APOIO_PEC = 0.05  # assinatura de PEC como coautor (apoio de quórum): 3,0 x 0,05 = 0,15 ponto

TIPOS_PROMULGADOS = ("PEC", "PDL", "PDC", "PRC", "PRN", "PDN", "PDS")

# descricao da situação na Câmara -> status de tramitação
SITUACOES = {
    "ARQUIVADA": [
        "Arquivada",
        "Aguardando Remessa ao Arquivo",
        "Enviada ao Arquivo",
        "Tramitação Finalizada",
        "Retirado pelo(a) Autor(a)",
        "Devolvida ao(à) Autor(a)",
        "Transformado em nova proposição",
    ],
    "REJEITADA": ["Perdeu a Eficácia", "Prejudicialidade", "Recusado"],
    "VETADA_TOTAL": ["Vetado totalmente"],
    # Hipótese registrada: o veto pendente de apreciação é tratado como parcial (a maioria dos vetos é parcial)
    "VETADA_PARCIAL": ["Aguardando Apreciação do Veto"],
    "APROVADO_PLENARIO": [
        "Aguardando Envio ao Senado Federal",
        "Aguardando Apreciação pelo Senado Federal",
        "Enviada ao Senado Federal",
        "Aguardando Sanção",
        "Aguardando Envio ao Executivo",
        "Aguardando Redação Final",
        "Aguardando Envio à Redação Final",
        "Aguardando Autógrafos na Mesa",
    ],
    "SEM_INFORMACAO": ["", "<Não Definido>", "Outros"],
    "EM_TRAMITACAO": [
        "Aguardando Providências Internas",
        "Tramitando em Conjunto",
        "Aguardando Designação de Relator(a)",
        "Pronta para Pauta",
        "Aguardando Parecer",
        "Aguardando Resposta",
        "Aguardando Despacho do Presidente da Câmara dos Deputados",
        "Aguardando Encaminhamento",
        "Aguardando Despacho do Presidente da Câmara dos Deputados (Chancela)",
        "Aguardando Autorização do Despacho",
        "Enviada ao Congresso Nacional",
        "Aguardando Designação - Aguardando Devolução de Relator(a) que deixou de ser Membro",
        "Aguardando Despacho do Presidente da Câmara dos Deputados (Autorização)",
        "Aguardando Despacho do Presidente da Câmara dos Deputados (Análise)",
        "Aguardando Deliberação de Recurso",
        "Aguardando Despacho - Requerimentos",
        "Aguardando Deliberação",
        "Aguardando Criação de Comissão Temporária",
        "Aguardando Definição Encaminhamento",
        "Aguardando Recurso",
        "Aguardando análise do Presidente da Câmara - (Decisão)",
        "Aguardando Despacho do Presidente",
        "Aguardando Apoiamento - Coleta de Assinaturas",
        "Aguardando Apoiamento - Conferência de Assinaturas",
        "Aguardando Análise de Parecer",
        "Ag. Análise de Inconstitucionalidade",
        "Aguardando Constituição de Comissão Temporária",
        "Aguardando Apensação",
        "Aguardando Conhecimento",
        "Aguardando Análise",
        "Comissão em funcionamento",
        "Aguardando Vistas",
        "Aguardando Encaminhamento à CCP para Publicação",
        "Tramitação Suspensa",
        "Enviada ao TCU",
        "Aguardando Elaboração do Parecer pelo(a) Relator(a)",
        "Desmembrada",
        "Encaminhada à Publicação",
        "Aguardando Leitura e Publicação",
        "Aguardando Recebimento",
        "Aguardando Solicitação de Relatoria na CMO",
        "Aguardando Notificação do(a) Representado(a)",
    ],
}

TIPOS_AUTOR = {
    "PESSOA_DEPUTADO": ["Deputado(a)"],
    "PESSOA_SENADOR": ["Senador(a)"],
    "COMISSAO": [
        "COMISSÃO PERMANENTE",
        "COMISSÃO ESPECIAL",
        "COMISSÃO PARLAMENTAR DE INQUÉRITO",
        "COMISSÃO MISTA PERMANENTE",
        "COMISSÃO MEDIDA PROVISÓRIA",
        "COMISSÃO EXTERNA",
        "SUBCOMISSÃO",
        "GRUPO DE TRABALHO",
        "MISTA ESPECIAL",
        "MISTA CPI",
        "PERMANENTE DO SENADO FEDERAL",
        "COMISSÃO DE SINDICÂNCIA",
    ],
    "PODER_EXECUTIVO": ["Órgão do Poder Executivo"],
    "PODER_JUDICIARIO": ["Órgão do Poder Judiciário"],
    "ORGAO_LEGISLATIVO": [
        "Órgão do Poder Legislativo",
        "Plenário Virtual CN",
        "Órgão da Câmara dos Deputados",
        "Órgão do Senado Federal",
    ],
    "MESA_DIRETORA": ["COMISSÃO DIRETORA"],
    "LIDERANCA": ["Liderança"],
    "BANCADA": ["Bancada"],
    "PARTIDO": ["Partido Político"],
    "SOCIEDADE_CIVIL": ["Sociedade Civil"],
    "MINISTERIO_PUBLICO": ["MPU - Ministério Público da União"],
    "DEFENSORIA": ["DPU - Defensoria Pública da União"],
    "CONSELHO": ["CONSELHO"],
    "OUTRO": ["Importação das proposições inativas"],
}

CSV_PROPOSICOES = [
    "id",
    "uri",
    "siglaTipo",
    "numero",
    "ano",
    "codTipo",
    "descricaoTipo",
    "ementa",
    "ementaDetalhada",
    "keywords",
    "dataApresentacao",
    "uriOrgaoNumerador",
    "uriPropAnterior",
    "uriPropPrincipal",
    "uriPropPosterior",
    "urlInteiroTeor",
    "urnFinal",
    "ultimoStatus_dataHora",
    "ultimoStatus_sequencia",
    "ultimoStatus_uriRelator",
    "ultimoStatus_idOrgao",
    "ultimoStatus_siglaOrgao",
    "ultimoStatus_uriOrgao",
    "ultimoStatus_regime",
    "ultimoStatus_descricaoTramitacao",
    "ultimoStatus_idTipoTramitacao",
    "ultimoStatus_descricaoSituacao",
    "ultimoStatus_idSituacao",
    "ultimoStatus_despacho",
    "ultimoStatus_apreciacao",
    "ultimoStatus_url",
]
CSV_AUTORES = [
    "idProposicao",
    "uriProposicao",
    "idDeputadoAutor",
    "uriAutor",
    "codTipoAutor",
    "tipoAutor",
    "nomeAutor",
    "siglaPartidoAutor",
    "uriPartidoAutor",
    "siglaUFAutor",
    "ordemAssinatura",
    "proponente",
]


def _q(valor) -> str:
    if valor is None:
        return "NULL"
    return "'" + str(valor).replace("'", "''") + "'"


def upgrade() -> None:
    # ── ref: tipos e status ──────────────────────────────────────────────────────────────────────
    for codigo, nome, _ in NOVOS_TIPOS:
        op.execute(f"INSERT INTO ref.tipo_proposicao VALUES ({_q(codigo)}, {_q(nome)})")
    op.execute("INSERT INTO ref.status_tramitacao VALUES ('SEM_INFORMACAO', 'Situação não informada pela fonte')")

    op.execute(
        """
        CREATE TABLE ref.situacao_camara (
            descricao text NOT NULL,
            tipo_codigo text REFERENCES ref.tipo_proposicao(codigo),
            status_codigo text NOT NULL REFERENCES ref.status_tramitacao(codigo),
            observacao text
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_situacao_camara ON ref.situacao_camara (descricao, coalesce(tipo_codigo, ''))")
    for status, descricoes in SITUACOES.items():
        for descricao in descricoes:
            obs = (
                "Hipótese: veto pendente tratado como parcial" if descricao == "Aguardando Apreciação do Veto" else None
            )
            op.execute(
                f"INSERT INTO ref.situacao_camara (descricao, status_codigo, observacao) "
                f"VALUES ({_q(descricao)}, {_q(status)}, {_q(obs)})"
            )
    op.execute(
        "INSERT INTO ref.situacao_camara (descricao, status_codigo) VALUES "
        "('Transformado em Norma Jurídica', 'APROVADA_E_SANCIONADA')"
    )
    for tipo in TIPOS_PROMULGADOS:
        op.execute(
            f"INSERT INTO ref.situacao_camara (descricao, tipo_codigo, status_codigo) VALUES "
            f"('Transformado em Norma Jurídica', {_q(tipo)}, 'APROVADA_E_PROMULGADA')"
        )

    op.execute(
        """
        CREATE TABLE ref.tipo_autor_camara (
            descricao text PRIMARY KEY,
            categoria text NOT NULL CHECK (categoria IN ('PESSOA_DEPUTADO','PESSOA_SENADOR','COMISSAO','PODER_EXECUTIVO',
                'PODER_JUDICIARIO','ORGAO_LEGISLATIVO','MESA_DIRETORA','LIDERANCA','BANCADA','PARTIDO','SOCIEDADE_CIVIL',
                'MINISTERIO_PUBLICO','DEFENSORIA','CONSELHO','OUTRO'))
        )
        """
    )
    for categoria, descricoes in TIPOS_AUTOR.items():
        for descricao in descricoes:
            op.execute(f"INSERT INTO ref.tipo_autor_camara VALUES ({_q(descricao)}, {_q(categoria)})")

    # ── core: entidades autoras e partidos fora do catálogo ──────────────────────────────────────
    op.execute(
        """
        CREATE TABLE core.entidade (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            categoria text NOT NULL,
            nome text NOT NULL,
            nome_normalizado text GENERATED ALWAYS AS (ref.normalizar_texto(nome)) STORED,
            criado_em timestamptz NOT NULL DEFAULT now(),
            UNIQUE (categoria, nome_normalizado)
        )
        """
    )
    op.execute("ALTER TABLE core.partido ADD COLUMN catalogo boolean NOT NULL DEFAULT true")
    op.execute(
        "COMMENT ON COLUMN core.partido.catalogo IS 'false: sigla criada a partir de uma fonte, sem cadastro oficial'"
    )

    # ── leg: proposição e autoria ────────────────────────────────────────────────────────────────
    op.execute("ALTER TABLE leg.proposicao ALTER COLUMN ementa DROP NOT NULL")
    op.execute("ALTER TABLE leg.proposicao ADD COLUMN situacao_fonte text, ADD COLUMN data_ultimo_status timestamptz")
    op.execute(
        """
        ALTER TABLE leg.autoria
            ADD COLUMN entidade_id bigint REFERENCES core.entidade(id),
            ADD COLUMN partido_id bigint REFERENCES core.partido(id),
            ADD COLUMN uf char(2) REFERENCES ref.uf(sigla),
            ADD COLUMN proponente boolean,
            ADD COLUMN tipo_autor_fonte text,
            ADD COLUMN fonte_id smallint REFERENCES etl.fonte(id),
            ADD CONSTRAINT ck_autoria_pessoa_ou_entidade CHECK (pessoa_id IS NULL OR entidade_id IS NULL)
        """
    )
    op.execute("CREATE INDEX ix_autoria_partido ON leg.autoria (partido_id)")
    op.execute("CREATE INDEX ix_autoria_entidade ON leg.autoria (entidade_id)")

    # ── param: IALP v3 (= v2 + novos tipos/status + peso de apoio de quórum) ─────────────────────
    bind = op.get_bind()
    bind.exec_driver_sql(
        "INSERT INTO param.metodologia (codigo, versao, descricao) VALUES ('IALP', 3, "
        "'IALP v2 + tipos de iniciativa da Câmara (PLN, PDC, RIC...), status SEM_INFORMACAO (1,0) e peso de apoio de "
        "quórum em PEC (coautor de PEC = 0,05 em vez de 0,2)')"
    )
    bind.exec_driver_sql(
        "INSERT INTO param.peso (metodologia_id, dimensao, chave, valor) "
        "SELECT (SELECT id FROM param.metodologia WHERE codigo = 'IALP' AND versao = 3), p.dimensao, p.chave, p.valor "
        "FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id WHERE m.codigo = 'IALP' AND m.versao = 2"
    )
    novos = [("PESO_TIPO", codigo, peso) for codigo, _, peso in NOVOS_TIPOS]
    novos.append(("PESO_STATUS", "SEM_INFORMACAO", 1.0))
    novos.append(("PESO_AUTORIA_POR_TIPO", "PEC:COAUTOR", PESO_APOIO_PEC))
    for dimensao, chave, valor in novos:
        bind.exec_driver_sql(
            "INSERT INTO param.peso (metodologia_id, dimensao, chave, valor) "
            "SELECT id, %s, %s, %s FROM param.metodologia WHERE codigo = 'IALP' AND versao = 3",
            (dimensao, chave, valor),
        )

    op.execute(
        """
        CREATE FUNCTION param.peso_opcional(p_metodologia text, p_dimensao text, p_chave text) RETURNS numeric
        LANGUAGE sql STABLE AS $$
            SELECT p.valor FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
            WHERE m.codigo = p_metodologia AND p.dimensao = p_dimensao AND p.chave = p_chave
              AND m.versao = (SELECT max(versao) FROM param.metodologia WHERE codigo = p_metodologia)
        $$
        """
    )

    # ── stg: staging dos CSV anuais da Câmara (texto puro, sem regra de negócio) ─────────────────
    colunas = ", ".join(f'"{c}" text' for c in CSV_PROPOSICOES)
    op.execute(f"CREATE UNLOGGED TABLE stg.camara_proposicao ({colunas})")
    colunas = ", ".join(f'"{c}" text' for c in CSV_AUTORES)
    op.execute(f"CREATE UNLOGGED TABLE stg.camara_autor ({colunas})")
    op.execute('CREATE INDEX ix_stg_camara_proposicao_id ON stg.camara_proposicao ("id")')
    op.execute('CREATE INDEX ix_stg_camara_autor_prop ON stg.camara_autor ("idProposicao")')

    # ── view de autoria pontuada: partido da fonte primeiro, com datas e período ─────────────────
    op.execute("DROP VIEW leg.vw_autoria_pontuada")
    op.execute(
        """
        CREATE VIEW leg.vw_autoria_pontuada AS
        SELECT a.id AS autoria_id, a.proposicao_id, a.pessoa_id, a.tipo_codigo AS tipo_autoria,
               p.tipo_codigo AS tipo_proposicao, p.status_codigo, p.data_apresentacao,
               p.id_camara IS NOT NULL AS da_camara, p.id_senado IS NOT NULL AS do_senado,
               coalesce(a.partido_id, f.partido_id,
                        (SELECT m.partido_id FROM core.mandato m
                          WHERE m.pessoa_id = a.pessoa_id AND m.partido_id IS NOT NULL
                            AND NOT EXISTS (SELECT 1 FROM core.filiacao x WHERE x.pessoa_id = a.pessoa_id)
                          ORDER BY m.inicio DESC LIMIT 1)) AS partido_id,
               (a.tipo_codigo = 'COAUTOR' AND p.tipo_codigo = 'PEC') AS apoio_quorum,
               param.peso_de('IALP', 'PESO_TIPO', p.tipo_codigo)
                 * coalesce(param.peso_opcional('IALP', 'PESO_AUTORIA_POR_TIPO', p.tipo_codigo || ':' || a.tipo_codigo),
                            param.peso_de('IALP', 'PESO_AUTORIA', a.tipo_codigo))
                 * param.peso_de('IALP', 'PESO_STATUS', p.status_codigo) AS pontos_ialp,
               param.peso_de('IALP', 'PESO_TIPO', p.tipo_codigo) AS pontos_relatoria
        FROM leg.autoria a
        JOIN leg.proposicao p ON p.id = a.proposicao_id
        LEFT JOIN core.filiacao f ON f.pessoa_id = a.pessoa_id AND f.periodo @> p.data_apresentacao
        WHERE a.tipo_codigo <> 'INSTITUCIONAL' AND (a.pessoa_id IS NOT NULL OR a.partido_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Migração de cobertura (0009) não é reversível.")
