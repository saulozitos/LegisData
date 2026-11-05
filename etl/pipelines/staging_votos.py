"""
Contagem de votos de uma carga. Os votos vão para as tabelas planas (`etl.pipelines.planas_votacoes`) e viram `leg.voto` na
fusão (`etl.preparar_votacoes_*`).
"""

from dataclasses import dataclass
from typing import Dict


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
