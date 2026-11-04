"""
Catálogo de verificações de uma carga, como funções puras (sem banco): cada uma recebe o que foi medido e devolve uma
`Verificacao` com o nome, se passou e o detalhe que explica o resultado. Quem carrega mede, chama a verificação e grava o
resultado em `etl.verificacao`; aqui só se decide se a medida está dentro do esperado.

Valor desconhecido (`None`) nunca é tratado como zero: uma data ausente não está fora da janela, é desconhecida, e uma
contagem desconhecida não passa. O campo `diferenca` do detalhe é sempre `obtido - esperado`: positivo é sobra, negativo é
falta.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Hashable, Iterable, List, Optional

JANELA_INICIAL = date(1995, 1, 1)  # decisão D8: dados a partir de 1995-01-01
AMOSTRA_DO_DETALHE = 10  # quantos exemplos de problema o detalhe guarda


@dataclass(frozen=True)
class Verificacao:
    nome: str
    passou: bool
    detalhe: Dict[str, Any] = field(default_factory=dict)


def contagem_fecha(nome: str, lidas: Optional[int], gravadas: Optional[int], rejeitadas: Optional[int]) -> Verificacao:
    """Toda linha lida tem de ter sido gravada ou rejeitada com motivo. Contagem desconhecida não passa."""
    detalhe = {"lidas": lidas, "gravadas": gravadas, "rejeitadas": rejeitadas}
    if lidas is None or gravadas is None or rejeitadas is None:
        return Verificacao(nome, False, {**detalhe, "motivo": "contagem desconhecida"})
    return Verificacao(nome, lidas == gravadas + rejeitadas, {**detalhe, "diferenca": gravadas + rejeitadas - lidas})


def total_confere(nome: str, informado: Optional[int], obtido: Optional[int]) -> Verificacao:
    """O total que a própria fonte informa (ex.: votos de uma votação) bate com o que entrou. Sem total informado, não passa."""
    detalhe = {"informado": informado, "obtido": obtido}
    if informado is None or obtido is None:
        return Verificacao(nome, False, {**detalhe, "motivo": "total desconhecido"})
    return Verificacao(nome, informado == obtido, {**detalhe, "diferenca": obtido - informado})


def cobertura_minima(nome: str, obtido: Optional[int], esperado: Optional[int], minimo: float = 1.0) -> Verificacao:
    """Entrou ao menos `minimo` (fração) do esperado. Esperado zero só passa se nada foi obtido; medida desconhecida não passa."""
    if obtido is None or esperado is None:
        return Verificacao(nome, False, {"obtido": obtido, "esperado": esperado, "motivo": "medida desconhecida"})
    fracao = (obtido / esperado) if esperado else (1.0 if obtido == 0 else 0.0)
    return Verificacao(
        nome, fracao >= minimo, {"obtido": obtido, "esperado": esperado, "fracao": round(fracao, 6), "minimo": minimo}
    )


def sem_nulos(nome: str, campo: str, nulos: int) -> Verificacao:
    """Campo obrigatório sem nenhum valor ausente."""
    return Verificacao(nome, nulos == 0, {"campo": campo, "nulos": nulos})


def sem_duplicatas(nome: str, chaves: Iterable[Hashable]) -> Verificacao:
    """A chave natural não se repete na carga."""
    repetidas = [chave for chave, vezes in Counter(chaves).items() if vezes > 1]
    return Verificacao(
        nome,
        not repetidas,
        {"repetidas": len(repetidas), "amostra": [str(chave) for chave in repetidas[:AMOSTRA_DO_DETALHE]]},
    )


def dentro_da_janela(nome: str, datas: Iterable[Optional[date]], inicio: date = JANELA_INICIAL) -> Verificacao:
    """Nenhuma data anterior a `inicio`. Datas ausentes são contadas à parte e não reprovam: são desconhecidas."""
    antes: List[date] = []
    desconhecidas = 0
    total = 0
    for data in datas:
        total += 1
        if data is None:
            desconhecidas += 1
        elif data < inicio:
            antes.append(data)
    return Verificacao(
        nome,
        not antes,
        {
            "inicio": inicio.isoformat(),
            "total": total,
            "anteriores": len(antes),
            "desconhecidas": desconhecidas,
            "amostra": [d.isoformat() for d in sorted(antes)[:AMOSTRA_DO_DETALHE]],
        },
    )
