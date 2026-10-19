"""
Carga única dos dados econômicos e curados no Postgres: séries, mandatos presidenciais, composição do Congresso, PNAD e finanças
(CEAP, emendas, remuneração e dados do TSE).

É o ponto de entrada de `run_etl --load-economia` e do deploy automático (e, com `chaves`, da atualização diária,
que só recarrega séries e mandatos). As cargas são independentes: uma curadoria com problema não impede as demais, e os
erros são relatados juntos no fim. A composição só existe sobre os mandatos presidenciais já carregados, então é pulada
(com mensagem clara, sem erro em cascata) quando eles falham.
"""

import importlib
import logging
from typing import Any, Dict, Iterable, Optional, Tuple

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

logger = logging.getLogger("CargaEconomica")

# (chave, nome exibido, módulo com `carregar(engine)`, chave da carga de que depende)
CARGAS: Tuple[Tuple[str, str, str, Optional[str]], ...] = (
    ("series", "Séries (eco.observacao)", "etl.pipelines.economia_loader", None),
    ("presidencia", "Mandatos presidenciais", "etl.pipelines.presidencia_loader", None),
    (
        "composicao",
        "Composição do Congresso e produção do Executivo",
        "etl.pipelines.composicao_loader",
        "presidencia",
    ),
    ("pnad", "PNAD (classes sociais)", "etl.pipelines.pnad_loader", None),
    ("financas", "Finanças (fin)", "etl.pipelines.financas_loader", None),
)


def descricao_do_erro(exc: Exception) -> str:
    """
    Texto do erro que pode ir para o log e para a saída do deploy. O erro do Postgres traz um `DETAIL: Failing row
    contains (...)` com os valores da linha (o `hide_parameters` do engine não o esconde), então dele só saem o tipo, a
    mensagem principal e o nome da restrição (para erro de dado, classe 22, só o tipo, o SQLSTATE e a coluna). Os demais erros (as mensagens da própria carga) saem como são.
    """
    if isinstance(exc, DBAPIError):
        diag = getattr(exc.orig, "diag", None)
        sqlstate = getattr(exc.orig, "pgcode", None) or ""
        restricao = getattr(diag, "constraint_name", None)
        coluna = getattr(diag, "column_name", None)
        if sqlstate.startswith("22"):
            # erro de dado (classe 22): a mensagem principal costuma citar o valor ofendido, ex. `invalid input syntax
            # for type integer: "<valor>"`. Ficam o tipo, o SQLSTATE e, se houver, a coluna.
            return f"{type(exc).__name__}: erro de dado (SQLSTATE {sqlstate})" + (
                f" na coluna {coluna}" if coluna else ""
            )
        principal = getattr(diag, "message_primary", None) or "erro do banco"
        return f"{type(exc).__name__}: {principal}" + (f" (restrição {restricao})" if restricao else "")
    return str(exc)


def carregar_tudo(
    engine: Engine, chaves: Optional[Iterable[str]] = None, toleradas: Iterable[str] = ()
) -> Dict[str, Any]:
    """
    Executa as cargas (todas, ou só as `chaves`) e devolve o resultado de cada uma; levanta RuntimeError no fim.

    Uma carga em `toleradas` que falha não levanta: o erro é registrado no log e devolvido como `{"erro": ...}` no
    resultado dela. O deploy usa isso para as finanças: a API nova continua servindo o que já está em `fin` em vez de
    deixar o checkout no compose novo com os contêineres antigos no ar.
    """
    aceitas = set(toleradas)
    escolhidas = set(chaves) if chaves is not None else None
    nomes = {chave: nome for chave, nome, _, _ in CARGAS}
    resultados: Dict[str, Any] = {}
    falhas = []
    falharam = set()
    for chave, nome, modulo, depende_de in CARGAS:
        if escolhidas is not None and chave not in escolhidas:
            continue
        if depende_de in falharam:
            falhas.append(f"{nome}: não executada porque '{nomes[depende_de]}' falhou")
            falharam.add(chave)
            continue
        try:
            resultados[chave] = importlib.import_module(modulo).carregar(engine)
            logger.info("%s: %s", nome, resultados[chave])
        except Exception as exc:  # noqa: BLE001 - isolada de propósito; relatada abaixo
            descricao = descricao_do_erro(exc)
            # a pilha de um erro do banco repete a mensagem inteira, com os valores da linha: só ela é omitida
            logger.error("Carga '%s' falhou: %s", nome, descricao, exc_info=not isinstance(exc, DBAPIError))
            if chave in aceitas:
                resultados[chave] = {"erro": descricao}
                continue
            falhas.append(f"{nome}: {descricao}")
            falharam.add(chave)
    if falhas:
        raise RuntimeError("; ".join(falhas))
    return resultados
