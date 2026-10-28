"""
Derivados pré-calculados do legislativo (`leg.mv_autoria_pontuada_unica` e `leg.mv_coautoria_par`).

O ETL os refaz no fim de cada carga (`etl.utils.manutencao.posprocessar_carga`). Quem lê uma dessas visões materializadas
chama `garantir_atualizados` antes, como rede de segurança: se alguma tabela de que o cálculo depende mudou desde a
última vez, a função do banco refaz as duas; senão não faz nada. Os gatilhos que marcam a mudança ficam no banco
(migração 0037), então nenhuma escrita precisa lembrar de avisar.

Duas regras protegem a API:

- O sinalizador é lido na sessão do chamador (um SELECT sem trava), então no caso comum, derivado em dia, nenhuma
  conexão extra sai do pool.
- Só se o derivado estiver velho a atualização roda, numa conexão própria de um pool dedicado de uma conexão e espera
  curta: não confirma (nem expira os objetos de) a transação do chamador e, com várias requisições velhas ao mesmo tempo,
  só uma atualiza e as outras seguem com a visão como está. Qualquer falha vira aviso e a leitura continua com o último
  dado confirmado.
"""

import logging
import threading
from typing import Dict

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Quanto uma leitura espera por uma conexão livre do pool dedicado antes de seguir com a visão como está
ESPERA_POR_CONEXAO_SEGUNDOS = 1

_motores: Dict[str, Engine] = {}
_trava_dos_motores = threading.Lock()


def _motor_da_atualizacao(motor_principal: Engine) -> Engine:
    """Um pool de uma conexão, por banco, só para atualizar os derivados (nunca disputa o pool das requisições)."""
    chave = motor_principal.url.render_as_string(hide_password=False)
    with _trava_dos_motores:
        if chave not in _motores:
            _motores[chave] = create_engine(
                motor_principal.url,
                pool_size=1,
                max_overflow=0,
                pool_timeout=ESPERA_POR_CONEXAO_SEGUNDOS,
                pool_pre_ping=True,
            )
        return _motores[chave]


def derivados_velhos(db: Session) -> bool:
    """O sinalizador de mudança, lido na sessão do chamador. Sem a linha de controle, conta como velho."""
    return bool(db.execute(text("SELECT coalesce((SELECT sujo FROM leg.pontuacao_controle), true)")).scalar())


def garantir_atualizados(db: Session) -> bool:
    """Refaz os derivados se estiverem velhos. Devolve True só quando refez; nunca levanta por falha de atualização."""
    try:
        if not derivados_velhos(db):
            return False
        motor = _motor_da_atualizacao(db.get_bind().engine)
        with motor.begin() as conexao:
            return conexao.execute(text("SELECT leg.atualizar_derivados()")).scalar() == "refeito"
    except SQLAlchemyError as exc:
        logger.warning("Derivados do legislativo não atualizados; a leitura segue com a visão como está: %s", exc)
        return False
