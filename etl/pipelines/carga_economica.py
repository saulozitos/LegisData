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
from typing import Any, Dict, Iterable, List, Optional, Tuple

from etl.pipelines.loader_helpers import descricao_do_erro
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
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
    ("financas_estaticas", "Finanças sem CEAP e emendas (fin)", "etl.pipelines.financas_estaticas", None),
)
# Qual carga de finanças cada modo roda. Um só mapa: o deploy, o `run_etl --load-economia` e os testes leem daqui.
FINANCAS_POR_MODO: Dict[str, Optional[str]] = {
    "completa": "financas",
    "estaticas": "financas_estaticas",
    "nenhuma": None,
}
MODOS_DO_DEPLOY = tuple(FINANCAS_POR_MODO)
# Falha dessas cargas não derruba o deploy quando o `fin` já tem dados (a API nova segue servindo o que está lá).
TOLERADAS_NO_DEPLOY = tuple(c for c in FINANCAS_POR_MODO.values() if c)
_SQL_FIN_TEM_CEAP_E_EMENDAS = (
    "select exists(select 1 from fin.emenda) and exists(select 1 from fin.despesa_cota) "
    "and exists(select 1 from fin.despesa_cota_fornecedor) and exists(select 1 from fin.despesa_cota_resumo)"
)


def chaves_do_deploy(modo: str) -> List[str]:
    """
    As cargas que o deploy executa. Séries, mandatos, composição e PNAD sempre; as finanças conforme o `modo`:
    "completa" (o `fin` está vazio: semeia tudo dos arquivos do git), "estaticas" (só remuneração, patrimônio, doações e
    certidões, porque CEAP e emendas vêm do timer diário e não podem voltar ao retrato do git) ou "nenhuma".
    """
    if modo not in FINANCAS_POR_MODO:
        raise ValueError(f"modo de finanças do deploy desconhecido: {modo!r} (esperado um de {MODOS_DO_DEPLOY})")
    financas = FINANCAS_POR_MODO[modo]
    return [c for c, *_ in CARGAS if c not in FINANCAS_POR_MODO.values() or c == financas]


def fin_tem_ceap_e_emendas(engine: Engine) -> bool:
    """True se `fin` já guarda CEAP (despesas, fornecedores e resumos) e emendas: o que a atualização diária mantém."""
    with engine.connect() as conexao:
        return bool(conexao.execute(text(_SQL_FIN_TEM_CEAP_E_EMENDAS)).scalar())


def carregar_tudo(
    engine: Engine,
    chaves: Optional[Iterable[str]] = None,
    toleradas: Iterable[str] = (),
    recarregar_ceap_e_emendas: bool = False,
) -> Dict[str, Any]:
    """
    Executa as cargas (as `chaves`, ou todas) e devolve o resultado de cada uma; levanta RuntimeError no fim.

    Sem `chaves`, as finanças dependem do banco: com CEAP e emendas já no `fin` só as cargas estáticas rodam (os arquivos
    do git estão atrás da atualização diária e recarregá-los desfaria o trabalho dela); com o `fin` vazio, semeia tudo.
    `recarregar_ceap_e_emendas` força a carga completa (por exemplo, depois de regerar os arquivos à mão).

    Uma carga em `toleradas` que falha não levanta: o erro é registrado no log e devolvido como `{"erro": ...}` no
    resultado dela. O deploy usa isso para as finanças: a API nova continua servindo o que já está em `fin` em vez de
    deixar o checkout no compose novo com os contêineres antigos no ar.
    """
    aceitas = set(toleradas)
    if chaves is None:
        modo = "completa" if recarregar_ceap_e_emendas or not fin_tem_ceap_e_emendas(engine) else "estaticas"
        chaves = chaves_do_deploy(modo)
        logger.info("Finanças em modo '%s'", modo)
    escolhidas = set(chaves)
    nomes = {chave: nome for chave, nome, _, _ in CARGAS}
    resultados: Dict[str, Any] = {}
    falhas = []
    falharam = set()
    for chave, nome, modulo, depende_de in CARGAS:
        if chave not in escolhidas:
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
