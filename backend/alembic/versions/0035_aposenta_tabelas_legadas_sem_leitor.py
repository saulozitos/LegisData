"""Aposenta as tabelas legadas do `public` que nenhuma rota, serviço nem ponte lê mais.

Os dados delas já vivem em `fin` (remuneração, patrimônio, CEAP, emendas, certidões, doações, processos) e em `eco`
(séries, resumo macroeconômico, desempenho dos mandatos, indicadores sociais, repasses e eleições por UF), e o ETL que
as alimentava saiu. A ponte do legado para `core` e `leg` só lê `politicos`, `partidos_politicos`, `filiacoes_partidarias`,
`mandatos`, `membros_gabinete`, `proposicoes` e as tabelas de votação e presença, que ficam até o novo ETL assumir.

Os dados são regeneráveis a partir das fontes, mas a estrutura não volta por esta revisão: o `downgrade` levanta erro,
como o da 0034. Para voltar além daqui, restaure o backup que o deploy faz antes das migrações (`docs/DEPLOY_AUTOMATICO.md`).

Revision ID: 0035
Revises: 0034
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

TABELAS = (
    "remuneracoes_politicos",
    "declaracoes_patrimonio",
    "despesas_cota_parlamentar",
    "emendas_parlamentares",
    "certidoes_judiciais",
    "doacoes_campanha",
    "processos_judiciais",
    "historico_mandatos",
    "pontos_dados_indicadores",
    "series_indicadores",
    "resumos_macroeconomicos_anuais",
    "mandatos_performance_economica",
    "analises_impacto_politica",
    "indicadores_sociais_anuais",
    "indicadores_sociais_uf",
    "resultados_eleicoes_presidenciais_uf",
    "repasses_federais_uf",
)
TIPOS = ("categoriaindicadorenum", "periodicidadeindicadorenum", "unidademedidaenum")


def upgrade() -> None:
    for tabela in TABELAS:
        op.execute(f"DROP TABLE IF EXISTS public.{tabela} CASCADE")
    for tipo in TIPOS:
        op.execute(f"DROP TYPE IF EXISTS public.{tipo}")


def downgrade() -> None:
    raise NotImplementedError(
        "Migração 0035 irreversível: as 17 tabelas aposentadas não voltam com o schema original. "
        "Restaure o backup feito pelo deploy antes das migrações."
    )
