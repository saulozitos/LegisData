"""
Derivados pré-calculados do legislativo (`leg.mv_autoria_pontuada_unica` e `leg.mv_coautoria_par`).

Quem lê uma dessas visões materializadas chama `garantir_atualizados` antes: se alguma tabela de que o cálculo depende mudou
desde a última vez, a função do banco refaz as duas; senão não faz nada. Os gatilhos que marcam a mudança ficam no banco
(migração 0037), então nenhuma escrita precisa lembrar de avisar.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def garantir_atualizados(db: Session) -> bool:
    """Refaz os derivados se estiverem velhos (devolve True quando refez). Confirma a transação da atualização."""
    refeito = bool(db.execute(text("SELECT leg.atualizar_derivados()")).scalar())
    db.commit()  # a atualização é gravação: sem confirmar, o fim da requisição a desfaria
    return refeito
