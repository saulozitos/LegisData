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
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from etl.pipelines.loader_helpers import descricao_do_erro
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

logger = logging.getLogger("CargaEconomica")

from etl.pipelines.financas_loader import CHAVES_ESTATICAS, fontes_do_timer  # noqa: E402

# (chave, nome exibido, módulo com `carregar(engine)`, chave da carga de que depende). A entrada pode ser "módulo:função"
# quando a carga não é o `carregar(engine)` do módulo.
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
# Quais cargas de finanças (de `financas_loader.CARGAS`) cada modo roda; None = todas. Um só mapa: o deploy, o
# `run_etl --load-economia` e os testes leem daqui, e a decisão de qual modo usar vem de `modo_de_semeadura`.
#   completa    - o git semeia CEAP, emendas e as estáticas;
#   sem_emendas - o git semeia a CEAP e as estáticas (as emendas já são do timer);
#   sem_ceap    - o git semeia as emendas e as estáticas (a CEAP já é do timer);
#   estaticas   - só remuneração, patrimônio, doações e certidões;
#   nenhuma     - nada de finanças.
FINANCAS_POR_MODO: Dict[str, Optional[Tuple[str, ...]]] = {
    "completa": None,
    "sem_emendas": ("ceap",) + CHAVES_ESTATICAS,
    "sem_ceap": ("emendas",) + CHAVES_ESTATICAS,
    "estaticas": CHAVES_ESTATICAS,
    "nenhuma": (),
}
MODOS_DO_DEPLOY = tuple(FINANCAS_POR_MODO)
# Falha dessa carga não derruba o deploy quando o `fin` já tem dados (a API nova segue servindo o que está lá).
TOLERADAS_NO_DEPLOY = ("financas",)
# O que cada fonte do timer guarda no `fin`: a fonte "tem dado" se todas as tabelas dela têm linhas.
TABELAS_DA_CEAP = ("despesa_cota", "despesa_cota_fornecedor", "despesa_cota_resumo")
TABELAS_DAS_EMENDAS = ("emenda",)


def sql_fin_tem(tabelas: Iterable[str], operador: str = "and") -> str:
    """A consulta "o `fin` tem dados nestas tabelas?": `and` pede todas, `or` basta uma. O deploy.sh repete estas consultas."""
    return f" {operador} ".join(f"exists(select 1 from fin.{t})" for t in tabelas)


SQL_FIN_TEM_CEAP = sql_fin_tem(TABELAS_DA_CEAP)
SQL_FIN_TEM_EMENDAS = sql_fin_tem(TABELAS_DAS_EMENDAS)
SQL_FIN_TEM_ALGUM_DADO = sql_fin_tem(TABELAS_DA_CEAP + TABELAS_DAS_EMENDAS, "or")


def modo_de_semeadura(tem_ceap: bool, tem_emendas: bool, ceap_do_timer: bool, emendas_do_timer: bool) -> Optional[str]:
    """
    Qual fonte o git precisa semear. Uma fonte só fica de fora quando o `fin` tem dado dela E o timer a assumiu (carregou
    dela uma extração fresca): fora disso o único dado que existe é o retrato do git. Devolve o modo ("completa",
    "sem_emendas", "sem_ceap") ou None quando nada precisa ser semeado. O `decidir_financas` do deploy.sh repete esta
    tabela (um teste confere as 16 combinações).
    """
    semear_ceap = not (tem_ceap and ceap_do_timer)
    semear_emendas = not (tem_emendas and emendas_do_timer)
    if semear_ceap and semear_emendas:
        return "completa"
    if semear_ceap:
        return "sem_emendas"
    if semear_emendas:
        return "sem_ceap"
    return None


def chaves_do_modo(modo: str) -> List[str]:
    """As cargas de um modo: séries, mandatos, composição e PNAD sempre; "financas" salvo no modo "nenhuma"."""
    if modo not in FINANCAS_POR_MODO:
        raise ValueError(f"modo de finanças desconhecido: {modo!r} (esperado um de {MODOS_DO_DEPLOY})")
    return [c for c, *_ in CARGAS if c != "financas" or modo != "nenhuma"]


def plano_do_modo(modo: str) -> Dict[str, Any]:
    """Os argumentos de `carregar_tudo` para um modo (as cargas e, dentro de "financas", quais fontes)."""
    return {"chaves": chaves_do_modo(modo), "chaves_financas": FINANCAS_POR_MODO[modo]}


def estado_do_fin(engine: Engine) -> Tuple[bool, bool]:
    """(tem CEAP, tem emendas) no `fin`. Sem o schema `fin`, (False, False)."""
    with engine.connect() as conexao:
        if not conexao.execute(text("select to_regclass('fin.emenda') is not null")).scalar():
            return False, False
        return (
            bool(conexao.execute(text(f"select {SQL_FIN_TEM_CEAP}")).scalar()),
            bool(conexao.execute(text(f"select {SQL_FIN_TEM_EMENDAS}")).scalar()),
        )


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
    ao_confirmar: Optional[Callable[[Any, str, Any], None]] = None,
    chaves_financas: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    Executa as cargas (as `chaves`, ou todas) e devolve o resultado de cada uma; levanta RuntimeError no fim.

    Sem `chaves`, o modo das finanças vem do banco (`modo_de_semeadura`): só se semeia do git a fonte que o `fin` ainda
    não tem ou que o timer ainda não assumiu; o resto fica só com as cargas estáticas. `recarregar_ceap_e_emendas` força o
    modo "completa" (por exemplo, depois de regerar os arquivos à mão). `chaves_financas` limita as fontes dentro da
    carga "financas" (um plano de `plano_do_modo`). `ao_confirmar(conn, chave, resultado)` roda dentro da transação de cada
    fonte das finanças (é por onde o `fin` registra de onde veio o dado).

    Uma carga em `toleradas` que falha não levanta: o erro é registrado no log e devolvido como `{"erro": ...}` no
    resultado dela. O deploy usa isso para as finanças: a API nova continua servindo o que já está em `fin` em vez de
    deixar o checkout no compose novo com os contêineres antigos no ar.
    """
    aceitas = set(toleradas)
    if chaves is None:
        if recarregar_ceap_e_emendas:
            modo: Optional[str] = "completa"
        else:
            tem_ceap, tem_emendas = estado_do_fin(engine)
            do_timer = fontes_do_timer(engine) if (tem_ceap or tem_emendas) else set()
            modo = modo_de_semeadura(tem_ceap, tem_emendas, "ceap" in do_timer, "emendas" in do_timer)
        modo = modo or "estaticas"
        plano = plano_do_modo(modo)
        chaves, chaves_financas = plano["chaves"], plano["chaves_financas"]
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
            if chave == "financas":
                resultados[chave] = _carga_de(modulo)(engine, chaves=chaves_financas, ao_confirmar=ao_confirmar)
            else:
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
