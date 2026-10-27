"""`eco.repasse_federal` e `eco.resultado_eleitoral_uf`, e a série de insegurança alimentar total.

Tira da API as últimas tabelas econômicas do `public` (`repasses_federais_uf`, `resultados_eleicoes_presidenciais_uf`) e
fecha a lacuna dos indicadores sociais, que já estavam em `eco.observacao` menos a insegurança alimentar total.

- `eco.repasse_federal`: transferências da União por UF e área no período de um mandato presidencial. O mandato é a chave
  estrangeira para `core.mandato_presidencial` (o `slug` público, como `lula-2023`, vem de lá); estado e região vêm de
  `ref.uf`, não são repetidos. Valor negativo existe (estorno), então não há CHECK de sinal. Início e fim do período são o
  primeiro dia do mês (o portal publica por mês); `parcial` diz se o portal cobre só parte do mandato (ele publica desde
  2014-01). Desconhecido é nulo, nunca zero.
- `eco.resultado_eleitoral_uf`: primeiro ou segundo colocado de uma eleição presidencial por UF, com o total de votos
  válidos quando a fonte (TSE) informa. Uma linha por (eleição, turno, UF). A eleição de 1994 entra, apesar de a janela de
  dados começar em 1995 (decisão D8): é a que elegeu o primeiro mandato da janela.
- `eco.serie`: `INSEGURANCA_ALIMENTAR_TOTAL_PCT`, o percentual de domicílios com insegurança alimentar em qualquer grau.

Revision ID: 0033
Revises: 0032
"""

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO eco.serie (codigo, nome, categoria, periodicidade, unidade, abrangencia, fonte_id, descricao)
        SELECT 'INSEGURANCA_ALIMENTAR_TOTAL_PCT', 'Domicílios com insegurança alimentar (qualquer grau)', 'FOME',
               'ANUAL', '%', 'BR', f.id, 'SIDRA t3017 e t9552.'
        FROM etl.fonte f WHERE f.codigo = 'IBGE_SIDRA'
        """
    )
    op.execute(
        """
        CREATE TABLE eco.repasse_federal (
            mandato_id bigint NOT NULL REFERENCES core.mandato_presidencial(mandato_id) ON DELETE CASCADE,
            uf char(2) NOT NULL REFERENCES ref.uf(sigla),
            area_tematica text NOT NULL CHECK (btrim(area_tematica) <> ''),
            ano_referencia smallint NOT NULL CHECK (ano_referencia >= 1995),
            valor_pago numeric(18, 2) NOT NULL,
            populacao_estimada integer CHECK (populacao_estimada > 0),
            valor_per_capita numeric(12, 2),
            periodo_inicio date CHECK (extract(day FROM periodo_inicio) = 1),
            periodo_fim date CHECK (extract(day FROM periodo_fim) = 1),
            meses_cobertos smallint CHECK (meses_cobertos > 0),
            parcial boolean,
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            carregado_em timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (mandato_id, uf, area_tematica),
            CHECK (periodo_fim IS NULL OR periodo_inicio IS NULL OR periodo_fim >= periodo_inicio)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE eco.resultado_eleitoral_uf (
            ano_eleicao smallint NOT NULL CHECK (ano_eleicao >= 1994),
            turno smallint NOT NULL CHECK (turno IN (1, 2)),
            uf char(2) NOT NULL REFERENCES ref.uf(sigla),
            mandato_id bigint REFERENCES core.mandato_presidencial(mandato_id) ON DELETE SET NULL,
            vencedor_nome text NOT NULL CHECK (btrim(vencedor_nome) <> ''),
            vencedor_partido text NOT NULL CHECK (btrim(vencedor_partido) <> ''),
            vencedor_votos_pct numeric(5, 2) NOT NULL CHECK (vencedor_votos_pct BETWEEN 0 AND 100),
            segundo_nome text NOT NULL CHECK (btrim(segundo_nome) <> ''),
            segundo_partido text NOT NULL CHECK (btrim(segundo_partido) <> ''),
            segundo_votos_pct numeric(5, 2) NOT NULL CHECK (segundo_votos_pct BETWEEN 0 AND 100),
            total_votos_validos integer CHECK (total_votos_validos >= 0),
            fonte_id smallint NOT NULL REFERENCES etl.fonte(id),
            carregado_em timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (ano_eleicao, turno, uf)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE eco.resultado_eleitoral_uf")
    op.execute("DROP TABLE eco.repasse_federal")
    op.execute(
        "DELETE FROM eco.observacao WHERE serie_id IN (SELECT id FROM eco.serie WHERE codigo = 'INSEGURANCA_ALIMENTAR_TOTAL_PCT')"
    )
    op.execute("DELETE FROM eco.serie WHERE codigo = 'INSEGURANCA_ALIMENTAR_TOTAL_PCT'")
