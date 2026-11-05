"""A fusão do cadastro não apaga mais o mandato que a presença (ou outro mandato) ainda referencia.

`etl.merge_cadastro` remove de `core.mandato` os mandatos da fonte LEGADO que deixaram de existir no staging
(`DELETE ... WHERE NOT EXISTS (... core.mandato_legado ...)`). Só que `leg.presenca.mandato_id`, `core.mandato.nomeado_por_mandato_id`
e `core.mandato_situacao.substituto_mandato_id` apontam para `core.mandato` sem `ON DELETE`: quando o staging perde um
mandato que uma presença já gravada usa, o `DELETE` estoura `presenca_mandato_id_fkey` e a carga inteira falha na fusão
(verificado ao carregar o staging atual sobre uma cópia do banco de desenvolvimento, que tinha presença e um staging mais
antigo).

Os dois `DELETE` passam a pular o mandato referenciado: ele fica em `core.mandato`, sem vínculo em `core.mandato_legado`, e
a próxima fusão tenta de novo (quando a referência sumir, ele sai). Preservar o dado é o lado seguro: apagar não é possível
sem perder a presença, e a presença é dado de fonte oficial. Enquanto fica, o mandato aparece na API e nas visões como
qualquer outro (o carregador registra no log quantos ficaram assim). Se o staging o recuperar, o upsert da 0020 reaproveita
a linha, sem duplicata; se a carga de presença reatribuir `mandato_id`, a fusão seguinte o remove.

A guarda de `nomeado_por_mandato_id` olha qualquer `core.mandato`, inclusive um nomeado órfão que o segundo `DELETE` apaga
na mesma fusão: nesse caso o mandato que o nomeou só sai na fusão seguinte. Convergir em uma execução exigiria reordenar os
dois `DELETE` (o dos nomeados roda depois do upsert deles); a troca de ordem foi descartada para manter o diff mínimo.

Como na 0036, o texto da função é lido do catálogo (não copiado), então o resto da lógica não muda; o `CREATE OR REPLACE`
mantém dono e concessões. O rebaixamento remove só as três condições acrescentadas.

Revision ID: 0038
Revises: 0037
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

ALVO = "AND NOT EXISTS (SELECT 1 FROM core.mandato_legado l WHERE l.mandato_id = c.id);"
GUARDA = (
    "AND NOT EXISTS (SELECT 1 FROM core.mandato_legado l WHERE l.mandato_id = c.id)\n"
    "        AND NOT EXISTS (SELECT 1 FROM leg.presenca p WHERE p.mandato_id = c.id)\n"
    "        AND NOT EXISTS (SELECT 1 FROM core.mandato n WHERE n.nomeado_por_mandato_id = c.id)\n"
    "        AND NOT EXISTS (SELECT 1 FROM core.mandato_situacao s WHERE s.substituto_mandato_id = c.id);"
)


def _trocar(origem: str, destino: str) -> None:
    conexao = op.get_bind()
    corpo = conexao.exec_driver_sql(
        "SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'etl' AND p.proname = 'merge_cadastro'"
    ).scalar_one()
    if corpo.count(origem) != 2:  # os dois DELETE de core.mandato (eletivos e nomeados)
        raise RuntimeError(
            f"etl.merge_cadastro difere do texto esperado (achei {corpo.count(origem)} trechos a trocar, esperava 2): "
            "a função foi editada fora das migrações? Confira a definição no catálogo antes de repetir."
        )
    conexao.exec_driver_sql(corpo.replace(origem, destino).replace("%", "%%"))  # sem interpretar ':' nem '%'


def upgrade() -> None:
    _trocar(ALVO, GUARDA)


def downgrade() -> None:
    _trocar(GUARDA, ALVO)
