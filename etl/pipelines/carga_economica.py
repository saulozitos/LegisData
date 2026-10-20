"""
Carga única dos dados econômicos e curados no Postgres: séries, mandatos presidenciais, composição do Congresso, PNAD e finanças
(CEAP, emendas, remuneração e dados do TSE).

É o ponto de entrada de `run_etl --load-economia` e do deploy automático (e, com `chaves`, de `economia_atualizacao`,
que só recarrega séries e mandatos; a atualização diária das finanças, `financas_atualizacao`, não passa por aqui). As cargas são independentes: uma curadoria com problema não impede as demais, e os
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
    # "módulo:função" quando a carga não é o `carregar(engine)` do módulo
    (
        "financas_estaticas",
        "Finanças sem CEAP e emendas (fin)",
        "etl.pipelines.financas_loader:carregar_estaticas",
        None,
    ),
    # semeadura parcial do deploy: uma das duas fontes do timer já é dele (o git não pode mais reescrevê-la)
    (
        "financas_sem_emendas",
        "Finanças sem as emendas (fin)",
        "etl.pipelines.financas_loader:carregar_sem_emendas",
        None,
    ),
    ("financas_sem_ceap", "Finanças sem a CEAP (fin)", "etl.pipelines.financas_loader:carregar_sem_ceap", None),
)
# Qual carga de finanças cada modo roda. Um só mapa: o deploy, o `run_etl --load-economia` e os testes leem daqui.
FINANCAS_POR_MODO: Dict[str, Optional[str]] = {
    "completa": "financas",
    "estaticas": "financas_estaticas",
    "sem_emendas": "financas_sem_emendas",
    "sem_ceap": "financas_sem_ceap",
    "nenhuma": None,
}
MODOS_DO_DEPLOY = tuple(FINANCAS_POR_MODO)
# Falha dessas cargas não derruba o deploy quando o `fin` já tem dados (a API nova segue servindo o que está lá).
TOLERADAS_NO_DEPLOY = tuple(c for c in FINANCAS_POR_MODO.values() if c)
# O que a atualização diária mantém: se todas têm linhas, o `fin` está semeado; se alguma tem, a API tem o que servir.
TABELAS_DA_CEAP_E_EMENDAS = ("emenda", "despesa_cota", "despesa_cota_fornecedor", "despesa_cota_resumo")


def sql_fin_tem_dados(operador: str) -> str:
    """A consulta "o `fin` tem dados?": `and` pede todas as tabelas, `or` basta uma. O deploy.sh repete esta consulta."""
    return f" {operador} ".join(f"exists(select 1 from fin.{t})" for t in TABELAS_DA_CEAP_E_EMENDAS)


def chaves_do_modo(modo: str) -> List[str]:
    """
    As cargas de um modo. Séries, mandatos, composição e PNAD sempre; as finanças conforme o `modo`: "completa" (o `fin`
    está vazio: semeia tudo dos arquivos do git), "estaticas" (só remuneração, patrimônio, doações e certidões, porque
    CEAP e emendas vêm do timer diário e não podem voltar ao retrato do git), "sem_emendas"/"sem_ceap" (as estáticas mais
    só uma das duas fontes do timer, quando a outra já é dele) ou "nenhuma". Vale para o deploy e para o
    `run_etl --load-economia`.
    """
    if modo not in FINANCAS_POR_MODO:
        raise ValueError(f"modo de finanças desconhecido: {modo!r} (esperado um de {MODOS_DO_DEPLOY})")
    financas = FINANCAS_POR_MODO[modo]
    return [c for c, *_ in CARGAS if c not in FINANCAS_POR_MODO.values() or c == financas]


def fin_tem_ceap_e_emendas(engine: Engine) -> bool:
    """True se `fin` já guarda CEAP (despesas, fornecedores e resumos) e emendas. Sem o schema `fin`, False."""
    with engine.connect() as conexao:
        if not conexao.execute(text("select to_regclass('fin.emenda') is not null")).scalar():
            return False
        return bool(conexao.execute(text(f"select {sql_fin_tem_dados('and')}")).scalar())


def falhas_toleradas(resultados: Dict[str, Any]) -> List[str]:
    """As cargas toleradas no deploy que falharam (resultado `{"erro": ...}`); o deploy as repete na execução seguinte."""
    return [
        chave
        for chave, resultado in resultados.items()
        if chave in TOLERADAS_NO_DEPLOY and isinstance(resultado, dict) and "erro" in resultado
    ]


def _carga_de(modulo: str) -> Any:
    """A função de carga de uma entrada de `CARGAS` ("módulo" => `carregar`; "módulo:função" => a função nomeada)."""
    nome_modulo, _, funcao = modulo.partition(":")
    return getattr(importlib.import_module(nome_modulo), funcao or "carregar")


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
        chaves = chaves_do_modo(modo)
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
            resultados[chave] = _carga_de(modulo)(engine)
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
