"""ETL direto: sem staging nem fusão em SQL, com data de corte por fonte e o CPF só como HMAC.

O carregamento é direto: o Python baixa e normaliza, e uma transação por recurso grava em `core`/`leg`/`fin` com
`INSERT ... ON CONFLICT` pela chave natural (identificador oficial da pessoa, número/ano da proposição, id da votação). Esta
migração tira do banco o que existia para preservar identificadores de um banco em uso e que o banco novo, refeito do zero, não
precisa:

- o schema `stg` inteiro (planas e congeladas do legado);
- as funções `etl.preparar_*`, `etl.merge_*` e auxiliares (ficam `aplicar_linhagens`, `resolver_partido_presenca` e
  `verificar_pesos`, que não dependem de staging) e `core.unificar_duplicadas` (a carga acha a pessoa pelo identificador oficial
  antes de criar outra, então a duplicata não nasce; `core.unificar_pessoas`, a união em si, fica);
- as pontes `core.mandato_legado`, `leg.votacao_legado` e a coluna `leg.autoria.legado_id`;
- a obrigatoriedade de `leg.votacao.aprovada`: a sessão cujo resultado a fonte não informa fica com `NULL` (antes virava
  "rejeitada", dado inventado, ou perdia os votos).

Entram a fonte `PIPELINE` (dona da linha de execução da esteira inteira, `etl.execucao` estágio `TUDO`; não é fonte de dados),
`etl.corte` (a data até a qual cada recurso já foi baixado), as colunas `sigla` e `nome` em `ref.partido_semente` (os nomes e
metadados dos partidos saem do código Python e passam a viver no banco) e os tipos de identificador `CURADORIA_ID` (presidentes
e ministros, que vêm de arquivo curado com fonte registrada) e `CPF_HMAC`.

`CPF_HMAC`: o CPF nunca é guardado, só o HMAC-SHA256 dele com uma chave secreta (`CPF_HMAC_KEY`). O CPF das fontes oficiais
(detalhe do deputado na API da Câmara; `consulta_cand` do TSE) liga a mesma pessoa mesmo quando o nome muda entre as fontes. Sem
a chave ninguém desfaz o valor gravado (um hash simples seria quebrado por força bruta: são só 10^9 CPFs possíveis). Quem perder
a chave perde só a capacidade de ligar CPFs novos aos antigos.

Os dados são regeneráveis a partir das fontes oficiais: não há volta (`downgrade` recusa), como na 0035.

Revision ID: 0039
Revises: 0038
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

FUNCOES_QUE_FICAM = ("aplicar_linhagens", "resolver_partido_presenca", "verificar_pesos")

# (sigla, nome, espectro, ideologia, lema, número eleitoral, logo): o que `dados_partidos.py` mantinha em código
PARTIDOS = """
INSERT INTO ref.partido_semente (sigla_normalizada, sigla, nome, espectro, ideologia, lema, numero_eleitoral, logo_url)
SELECT DISTINCT ON (ref.normalizar_texto(v.sigla)) ref.normalizar_texto(v.sigla), v.sigla, v.nome, v.espectro, v.ideologia, v.lema, v.numero, v.logo
FROM (VALUES
    ('AGIR', NULL, 'CENTRO', NULL, NULL, NULL, NULL),
    ('AVANTE', 'Avante', 'CENTRO', 'Humanismo cívico / Municipalismo', 'O Brasil precisa seguir avante', 70, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f9/Avante_70_%28Brasil%29_logo.svg/250px-Avante_70_%28Brasil%29_logo.svg.png'),
    ('CIDADANIA', 'Cidadania', 'CENTRO', 'Social-liberalismo / Terceira via', 'Construindo cidadania plena e oportunidades', 23, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/9/9e/Cidadania_%28Brasil%29_logo_%28variant_1%29.svg/250px-Cidadania_%28Brasil%29_logo_%28variant_1%29.svg.png'),
    ('DC', NULL, 'DIREITA', 'Democracia cristã / Conservadorismo social', 'Deus, pátria e família', 27, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ed/Logomarca_Democracia_Crist%C3%A3.svg/250px-Logomarca_Democracia_Crist%C3%A3.svg.png'),
    ('DEM', 'Democratas', 'CENTRO_DIREITA', 'Liberalismo / Conservadorismo liberal', 'A favor do Brasil', 25, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Democratas_%28Brazil%29_logo_%282018-2022%29_%28horizontal%29.svg/250px-Democratas_%28Brazil%29_logo_%282018-2022%29_%28horizontal%29.svg.png'),
    ('MDB', 'Movimento Democrático Brasileiro', 'CENTRO', 'Centrismo / Ponto de equilíbrio democrático', 'O partido que equilibra o Brasil', 15, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ef/Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg/250px-Movimento_Democr%C3%A1tico_Brasileiro_%282017%29.svg.png'),
    ('MISSÃO', NULL, 'CENTRO_DIREITA', 'Liberalismo econômico / Renovação política', 'Missão pelo futuro do Brasil', 99, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/67/Partido_Miss%C3%A3o_logo_%28light%29.svg/250px-Partido_Miss%C3%A3o_logo_%28light%29.svg.png'),
    ('NOVO', 'Partido Novo', 'DIREITA', 'Liberalismo clássico / Estado mínimo', 'Menos governo, mais liberdade individual', 30, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d3/Partido_Novo_logo_%282023%29.svg/250px-Partido_Novo_logo_%282023%29.svg.png'),
    ('PATRI', 'Patriota', 'DIREITA', NULL, NULL, NULL, NULL),
    ('PATRIOTA', 'Patriota', 'DIREITA', 'Conservadorismo / Nacionalismo', 'Brasil acima de tudo', 51, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f9/Logomarca_do_Partido_Patriota.png/250px-Logomarca_do_Partido_Patriota.png'),
    ('PC DO B', 'Partido Comunista do Brasil', 'ESQUERDA', NULL, NULL, NULL, NULL),
    ('PCB', NULL, 'ESQUERDA', NULL, NULL, NULL, NULL),
    ('PCdoB', 'Partido Comunista do Brasil', 'ESQUERDA', 'Comunismo democrático / Antimperialismo', 'Pela soberania nacional e o socialismo', 65, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/b/b2/Logomarca_do_Partido_Comunista_do_Brasil.png/250px-Logomarca_do_Partido_Comunista_do_Brasil.png'),
    ('PCO', NULL, 'ESQUERDA', NULL, NULL, NULL, NULL),
    ('PDC', NULL, NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/65/Bandeirapdc85melhorada.png/250px-Bandeirapdc85melhorada.png'),
    ('PDS', 'Partido Democrático Social', NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a9/Partido_Democr%C3%A1tico_Social_logo.svg/250px-Partido_Democr%C3%A1tico_Social_logo.svg.png'),
    ('PDT', 'Partido Democrático Trabalhista', 'CENTRO_ESQUERDA', 'Trabalhismo brizolista / Nacionalismo desenvolvimentista', 'A educação emancipa, o trabalho dignifica', 12, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/1f/Bandeira.PDT.png/250px-Bandeira.PDT.png'),
    ('PEN', 'Partido Ecológico Nacional', NULL, NULL, NULL, NULL, NULL),
    ('PFL', 'Partido da Frente Liberal', 'CENTRO_DIREITA', 'Liberalismo conservador', 'Construindo o futuro', NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/e7/Partido_da_Frente_Liberal_logo_%281985-2005%29.svg/250px-Partido_da_Frente_Liberal_logo_%281985-2005%29.svg.png'),
    ('PHS', 'Partido Humanista da Solidariedade', NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/75/Logo_-_Partido_Humanista_da_Solidariedade.png/250px-Logo_-_Partido_Humanista_da_Solidariedade.png'),
    ('PL', 'Partido Liberal', 'DIREITA', 'Conservadorismo social / Liberalismo econômico', 'Deus, Pátria, Família e Liberdade', 22, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/12/Partido_Liberal_%28Brazil%29_logo.svg/250px-Partido_Liberal_%28Brazil%29_logo.svg.png'),
    ('PMB', NULL, 'DIREITA', NULL, NULL, NULL, NULL),
    ('PMDB', 'Partido do Movimento Democrático Brasileiro', 'CENTRO', 'Centrismo / Democracia partidária', 'O partido do Brasil', NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/c/cc/PMDB_2000_a_2017.svg/250px-PMDB_2000_a_2017.svg.png'),
    ('PMN', 'Partido da Mobilização Nacional', 'CENTRO', NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dd/PMN_logo.svg/250px-PMN_logo.svg.png'),
    ('PODE', 'Podemos', 'CENTRO', 'Democracia direta / Centrismo liberal', 'Juntos podemos transformar o Brasil', 20, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2d/Podemos_%28Brasil%29_logo.svg/250px-Podemos_%28Brasil%29_logo.svg.png'),
    ('PODEMOS', NULL, 'CENTRO', 'Democracia direta / Centrismo liberal', 'Juntos podemos transformar o Brasil', NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/2d/Podemos_%28Brasil%29_logo.svg/250px-Podemos_%28Brasil%29_logo.svg.png'),
    ('PP', 'Progressistas', 'CENTRO_DIREITA', 'Centro-direita / Pragmatismo de desenvolvimento', 'O futuro se constrói com trabalho e progresso', 11, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/87/Progressistas_%28Brazil%29_logo.svg/250px-Progressistas_%28Brazil%29_logo.svg.png'),
    ('PPB', 'Partido Progressista Brasileiro', 'CENTRO_DIREITA', NULL, NULL, NULL, NULL),
    ('PPR', 'Partido Progressista Reformador', 'CENTRO_DIREITA', NULL, NULL, NULL, NULL),
    ('PPS', 'Partido Popular Socialista', NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d3/Logomarca_do_Partido_Popular_Socialista.png/250px-Logomarca_do_Partido_Popular_Socialista.png'),
    ('PR', 'Partido da República', NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/fe/Logomarca_do_Partido_da_Rep%C3%BAblica.png/250px-Logomarca_do_Partido_da_Rep%C3%BAblica.png'),
    ('PRB', 'Partido Republicano Brasileiro', 'CENTRO_DIREITA', NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a2/Logomarca_do_Partido_Republicano_Brasileiro_%282012%E2%80%932019%29.png/250px-Logomarca_do_Partido_Republicano_Brasileiro_%282012%E2%80%932019%29.png'),
    ('PRD', 'Partido Renovação Democrática', 'CENTRO_DIREITA', 'Conservadorismo democrático', 'Renovação e ordem institucional', NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/dc/Partido_Renova%C3%A7%C3%A3o_Democr%C3%A1tica_logo.svg/250px-Partido_Renova%C3%A7%C3%A3o_Democr%C3%A1tica_logo.svg.png'),
    ('PRONA', NULL, NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/c/ca/Partido_de_Reedifica%C3%A7%C3%A3o_da_Ordem_Nacional_logo_%282004%E2%80%932006%29.png/250px-Partido_de_Reedifica%C3%A7%C3%A3o_da_Ordem_Nacional_logo_%282004%E2%80%932006%29.png'),
    ('PROS', 'Partido Republicano da Ordem Social', 'CENTRO', 'Centrismo / Reformismo social', 'Por um Brasil justo e fraterno', 90, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/e/ee/Logomarca_do_Partido_Republicano_da_Ordem_Social_%28PROS%29%2C_do_Brasil.png/250px-Logomarca_do_Partido_Republicano_da_Ordem_Social_%28PROS%29%2C_do_Brasil.png'),
    ('PRP', 'Partido Republicano Progressista', NULL, NULL, NULL, NULL, NULL),
    ('PRTB', 'Partido Renovador Trabalhista Brasileiro', 'DIREITA', 'Trabalhismo participativo / Conservadorismo', 'Coragem para transformar', 28, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/d/d5/Logomarca_do_Partido_Renovador_Trabalhista_Brasileiro_2.png/250px-Logomarca_do_Partido_Renovador_Trabalhista_Brasileiro_2.png'),
    ('PSB', 'Partido Socialista Brasileiro', 'CENTRO_ESQUERDA', 'Socialismo democrático / Progressismo', 'Igualdade e liberdade construídas com justiça', 40, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/1/19/Partido_Socialista_Brasileiro_logo.png/250px-Partido_Socialista_Brasileiro_logo.png'),
    ('PSC', 'Partido Social Cristão', 'CENTRO_DIREITA', 'Democracia cristã / Conservadorismo cristão', 'O ser humano em primeiro lugar', NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/a9/PSC_logo%28cortado%29.png/250px-PSC_logo%28cortado%29.png'),
    ('PSD', 'Partido Social Democrático', 'CENTRO', 'Pragmatismo de centro / Municipalismo', 'Nem direita, nem esquerda: a favor do Brasil', 55, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/0/0c/PSD_Brazil_logo.svg/250px-PSD_Brazil_logo.svg.png'),
    ('PSDB', 'Partido da Social Democracia Brasileira', 'CENTRO', 'Social-democracia clássica / Terceira via', 'Por um Brasil moderno, justo e eficiente', 45, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/2/22/Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg/250px-Logo_of_the_Brazilian_Social_Democracy_Party_%282023%29.svg.png'),
    ('PSDC', NULL, NULL, NULL, NULL, NULL, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/aa/Bandeira_do_Partido_Social_Democrata_Crist%C3%A3o.svg/250px-Bandeira_do_Partido_Social_Democrata_Crist%C3%A3o.svg.png'),
    ('PSL', 'Partido Social Liberal', 'DIREITA', 'Conservadorismo / Liberalismo', 'Mais Brasil, menos Brasília', 17, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c2/Partido_Social_Liberal_logo.svg/250px-Partido_Social_Liberal_logo.svg.png'),
    ('PSOL', 'Partido Socialismo e Liberdade', 'ESQUERDA', 'Socialismo democrático / Ecossocialismo', 'Por um Brasil para a maioria trabalhadora', 50, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/f/f4/Logo_PSOL_roxo.svg/250px-Logo_PSOL_roxo.svg.png'),
    ('PSTU', NULL, 'ESQUERDA', NULL, NULL, NULL, NULL),
    ('PT', 'Partido dos Trabalhadores', 'ESQUERDA', 'Social-democracia / Trabalhismo democrático', 'O Brasil da esperança e da justiça social', 13, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/c/c3/PT_%28Brazil%29_logo_2021.svg/250px-PT_%28Brazil%29_logo_2021.svg.png'),
    ('PTB', 'Partido Trabalhista Brasileiro', 'DIREITA', 'Trabalhismo / Conservadorismo', 'A força do trabalhador', 14, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/6/6a/Logomarca_Partido_Trabalhista_Brasileiro.png/250px-Logomarca_Partido_Trabalhista_Brasileiro.png'),
    ('PV', 'Partido Verde', 'CENTRO_ESQUERDA', 'Ecologismo / Desenvolvimento sustentável', 'Paz, ecologia e justiça socioambiental', 43, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/4/46/Logomarca_do_Partido_Verde.svg/250px-Logomarca_do_Partido_Verde.svg.png'),
    ('REDE', 'Rede Sustentabilidade', 'CENTRO_ESQUERDA', 'Sustentabilidade ética / Progressismo cívico', 'Conectar pessoas pela ética na política', 18, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/39/Rede_Sustentabilidade_logo.svg/250px-Rede_Sustentabilidade_logo.svg.png'),
    ('REPUBLICANOS', 'Republicanos', 'CENTRO_DIREITA', 'Conservadorismo cristão / Municipalismo', 'Defendendo os valores da família e o desenvolvimento', 10, 'https://thumb.wikimedia.org/wikipedia/pt/thumb/0/0d/Republicanos_logo.png/250px-Republicanos_logo.png'),
    ('S.PART.', 'Sem Partido', NULL, NULL, NULL, NULL, NULL),
    ('SOLIDARIEDADE', 'Solidariedade', 'CENTRO', 'Trabalhismo social / Sindicalismo plural', 'Solidariedade com o trabalhador e o desenvolvimento', 77, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/77/Solidariedade_77_%28Brasil%29_logo.svg/250px-Solidariedade_77_%28Brasil%29_logo.svg.png'),
    ('UNIAO', NULL, 'CENTRO_DIREITA', NULL, NULL, NULL, NULL),
    ('UNIÃO', 'União Brasil', 'CENTRO_DIREITA', 'Liberalismo / Conservadorismo liberal', 'Coragem para mudar, união para governar', 44, 'https://thumb.wikimedia.org/wikipedia/commons/thumb/7/73/Uni%C3%A3o_Brasil_logo.svg/250px-Uni%C3%A3o_Brasil_logo.svg.png'),
    ('UP', NULL, 'ESQUERDA', NULL, NULL, NULL, NULL)
) AS v(sigla, nome, espectro, ideologia, lema, numero, logo)
ORDER BY ref.normalizar_texto(v.sigla), v.nome NULLS LAST, v.sigla
ON CONFLICT (sigla_normalizada) DO UPDATE SET
    sigla = EXCLUDED.sigla,
    nome = coalesce(EXCLUDED.nome, ref.partido_semente.nome),
    espectro = coalesce(ref.partido_semente.espectro, EXCLUDED.espectro),
    ideologia = coalesce(ref.partido_semente.ideologia, EXCLUDED.ideologia),
    lema = coalesce(ref.partido_semente.lema, EXCLUDED.lema),
    numero_eleitoral = coalesce(ref.partido_semente.numero_eleitoral, EXCLUDED.numero_eleitoral),
    logo_url = coalesce(ref.partido_semente.logo_url, EXCLUDED.logo_url)
"""


def upgrade() -> None:
    op.execute(
        "INSERT INTO etl.fonte (codigo, nome, orgao, formato, periodicidade, observacao) VALUES "
        "('PIPELINE', 'Esteira do ETL (execução completa)', 'LegisData', 'N/A', 'SOB_DEMANDA', "
        "'Linha de execução da rodada inteira; não é fonte de dados') ON CONFLICT (codigo) DO NOTHING"
    )
    op.execute(
        """
        CREATE TABLE etl.corte (
            fonte text NOT NULL,
            recurso text NOT NULL,
            ultima_data date,
            ultima_execucao_id bigint REFERENCES etl.execucao(id),
            atualizado_em timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (fonte, recurso)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE etl.corte IS 'Até que data cada recurso de cada fonte já foi baixado e gravado; "
        "só avança quando a transação de gravação confirma'"
    )
    op.execute("ALTER TABLE ref.partido_semente ADD COLUMN IF NOT EXISTS sigla text")
    op.execute("ALTER TABLE ref.partido_semente ADD COLUMN IF NOT EXISTS nome text")
    op.get_bind().exec_driver_sql(PARTIDOS.replace("%", "%%"))
    op.execute("UPDATE ref.partido_semente SET sigla = upper(sigla_normalizada) WHERE sigla IS NULL")
    op.execute("ALTER TABLE ref.partido_semente ALTER COLUMN sigla SET NOT NULL")

    op.execute("ALTER TABLE core.pessoa_identificador DROP CONSTRAINT pessoa_identificador_tipo_check")
    op.execute(
        "ALTER TABLE core.pessoa_identificador ADD CONSTRAINT pessoa_identificador_tipo_check "
        "CHECK (tipo = ANY (ARRAY['CAMARA_ID', 'SENADO_ID', 'TSE_ID', 'DATAJUD_ID', 'CURADORIA_ID', 'CPF_HMAC']))"
    )

    # resultado da votação que a fonte não informa é desconhecido (NULL), não "rejeitada"
    op.execute("ALTER TABLE leg.votacao ALTER COLUMN aprovada DROP NOT NULL")
    op.execute("DROP FUNCTION IF EXISTS core.unificar_duplicadas()")
    op.execute("DROP TABLE IF EXISTS core.mandato_legado")
    op.execute("DROP TABLE IF EXISTS leg.votacao_legado")
    op.execute("ALTER TABLE leg.autoria DROP COLUMN IF EXISTS legado_id")
    op.execute("DROP SCHEMA IF EXISTS stg CASCADE")
    lista = ", ".join(f"'{nome}'" for nome in FUNCOES_QUE_FICAM)
    op.get_bind().exec_driver_sql(
        "DO $$ DECLARE f record; BEGIN "
        "FOR f IN SELECT p.oid::regprocedure AS assinatura FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        f"WHERE n.nspname = 'etl' AND p.proname NOT IN ({lista}) "
        "LOOP EXECUTE 'DROP FUNCTION ' || f.assinatura; END LOOP; END $$"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "irreversível: o ETL direto não guarda staging nem as pontes do legado; refaça o banco a partir das fontes"
    )
