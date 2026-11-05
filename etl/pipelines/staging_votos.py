"""
Gravação dos votos nominais em `stg.votos_parlamentares` por COPY.

É o maior volume da carga (mais de um milhão de linhas): o ORM gravava linha a linha e o `executemany` em lotes de 2 mil
ainda custava minutos. Aqui os votos de um lote vão por COPY para uma tabela temporária e entram na tabela de staging num
único INSERT ... ON CONFLICT DO NOTHING, na MESMA transação do cursor recebido (a da sessão da carga). O par
(sessão, político) é único: um voto já gravado nunca é sobrescrito nem duplicado, igual ao comportamento anterior.
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

from etl.utils.copia import copiar_linhas

COLUNAS = ["sessao_id", "politico_id", "partido_id", "voto"]

# (sessao_id, politico_id, partido_id ou None, voto)
LinhaDeVoto = Tuple[Any, Any, Optional[Any], str]


@dataclass(frozen=True)
class ContagemDeVotos:
    """
    Contagem de votos de uma carga. `lidas` = votos que a fonte trouxe; `rejeitadas` = os que não viraram linha (sem
    sessão, sem político ou com opção desconhecida); `gravadas` = linhas entregues a `gravar_votos`, ou seja, inseridas
    mais as que já estavam (a carga é idempotente). Uma linha repetida (no lote, ou no plenário e no histórico) conta
    uma vez em cada entrega, então `gravadas` pode passar o número de linhas distintas do staging; o que fecha é
    `lidas == gravadas + rejeitadas`.

    `arquivos_ignorados` = arquivos de votos que a carga pulou inteiros (ilegíveis, sem proveniência ou incompletos).
    Os votos deles não dá para contar, então não entram em `lidas`; a execução sai `COM_ALERTA` quando há algum, para a
    perda não passar por `OK`.
    """

    lidas: int = 0
    gravadas: int = 0
    rejeitadas: int = 0
    arquivos_ignorados: int = 0

    def __add__(self, outra: "ContagemDeVotos") -> "ContagemDeVotos":
        return ContagemDeVotos(
            self.lidas + outra.lidas,
            self.gravadas + outra.gravadas,
            self.rejeitadas + outra.rejeitadas,
            self.arquivos_ignorados + outra.arquivos_ignorados,
        )

    def como_contadores(self) -> Dict[str, int]:
        """Os contadores do resumo de `carregar_votacoes` (as chaves ficam definidas só aqui e em `de_contadores`)."""
        return {
            "votos_lidos": self.lidas,
            "votos_gravados": self.gravadas,
            "votos_descartados": self.rejeitadas,
            "arquivos_ignorados": self.arquivos_ignorados,
        }

    @classmethod
    def de_contadores(cls, contadores: Dict[str, int]) -> "ContagemDeVotos":
        return cls(
            lidas=contadores["votos_lidos"],
            gravadas=contadores["votos_gravados"],
            rejeitadas=contadores["votos_descartados"],
            arquivos_ignorados=contadores["arquivos_ignorados"],
        )


def gravar_votos(cursor: Any, linhas: Iterable[LinhaDeVoto]) -> Tuple[int, int]:
    """
    Grava os votos e devolve `(inseridos, ja_existentes)`. Linhas repetidas dentro do mesmo lote (mesma sessão e mesmo
    político) contam como já existentes: vale a primeira.
    """
    # Uma tabela temporária por transação, reaproveitada a cada chamada: criar e apagar uma por lote esgota a tabela de
    # travas do Postgres (`max_locks_per_transaction`) quando a mesma transação grava milhares de lotes.
    cursor.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _voto "
        "(sessao_id uuid, politico_id uuid, partido_id uuid, voto text, ordem serial) ON COMMIT DROP"
    )
    lidas = copiar_linhas(cursor, "_voto", COLUNAS, linhas)
    inseridos = 0
    if lidas:
        cursor.execute(
            'INSERT INTO stg.votos_parlamentares (id, "sessaoVotacaoId", "politicoId", "partidoId", voto, created_at) '
            "SELECT gen_random_uuid(), sessao_id, politico_id, partido_id, voto::votoopcaoenum, now() "
            "FROM (SELECT DISTINCT ON (sessao_id, politico_id) * FROM _voto ORDER BY sessao_id, politico_id, ordem) v "
            'ON CONFLICT ("sessaoVotacaoId", "politicoId") DO NOTHING'
        )
        inseridos = max(cursor.rowcount, 0)
    cursor.execute("TRUNCATE _voto")
    return inseridos, lidas - inseridos
