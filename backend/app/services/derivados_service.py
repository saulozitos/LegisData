"""
Derivados pré-calculados do legislativo (`leg.mv_autoria_pontuada_unica` e `leg.mv_coautoria_par`).

O ETL os refaz no fim de cada carga (`etl.utils.manutencao.posprocessar_carga`). Quem lê uma dessas visões materializadas
chama `garantir_atualizados` antes, como rede de segurança: se alguma tabela de que o cálculo depende mudou desde a
última vez, a função do banco refaz as duas; senão não faz nada. Os gatilhos que marcam a mudança ficam no banco
(migração 0037), então nenhuma escrita precisa lembrar de avisar.

A atualização roda numa conexão própria, não na sessão da requisição: assim ela não confirma (nem expira os objetos de)
a transação do chamador, e uma trava que a atualização espere não prende a sessão dele. Se uma carga estiver em
andamento, a função desiste depressa e a leitura usa a visão como está (último dado confirmado).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def garantir_atualizados(db: Session) -> bool:
    """Refaz os derivados se estiverem velhos (devolve True quando refez; False se não precisava ou não deu para esperar)."""
    bind = db.get_bind()
    motor = bind.engine
    with motor.begin() as conexao:
        return bool(conexao.execute(text("SELECT leg.atualizar_derivados()")).scalar())
