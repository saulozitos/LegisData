"""Filiações partidárias: derivadas dos períodos de partido que as fontes oficiais já gravaram (sem arquivo digitado à mão)."""

from typing import Any

from etl.carga.base import Resultado, contagem_de, criar_rejeitos, escalar, executar_sql, ler_rejeitos


def derivar_filiacoes(cursor: Any) -> Resultado:
    """Refaz `core.filiacao` a partir de `core.mandato_partido` e do partido na posse de cada mandato."""
    criar_rejeitos(cursor)
    executar_sql(cursor, "filiacoes")
    # lidas = trechos de partido encontrados; o que não virou linha própria tem motivo (engolido ou unido ao vizinho)
    gravadas = int(escalar(cursor, "SELECT count(*) FROM core.filiacao"))
    rejeitos = ler_rejeitos(cursor)
    return Resultado(contagem_de(gravadas + sum(rejeitos.values()), rejeitos), extras={"filiacoes": gravadas})
