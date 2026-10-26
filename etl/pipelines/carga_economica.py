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
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from etl.pipelines.loader_helpers import descricao_do_erro
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

logger = logging.getLogger("CargaEconomica")

from etl.config import CHAVES_ESTATICAS  # noqa: E402
from etl.pipelines.semeadura_das_financas import (  # noqa: E402,F401 - reexportadas: os testes e o deploy leem daqui
    SQL_FIN_TEM_ALGUM_DADO,
    SQL_FIN_TEM_CEAP,
    SQL_FIN_TEM_EMENDAS,
    TABELAS_DA_CEAP,
    TABELAS_DAS_EMENDAS,
    estado_do_fin,
    fontes_do_timer,
    modo_de_semeadura,
    sql_fin_tem,
)

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
#   estaticas   - só remuneração, patrimônio, doações, certidões e processos;
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


def chaves_do_modo(modo: str) -> List[str]:
    """As cargas de um modo: séries, mandatos, composição e PNAD sempre; "financas" salvo no modo "nenhuma"."""
    if modo not in FINANCAS_POR_MODO:
        raise ValueError(f"modo de finanças desconhecido: {modo!r} (esperado um de {MODOS_DO_DEPLOY})")
    return [c for c, *_ in CARGAS if c != "financas" or modo != "nenhuma"]


def plano_do_modo(modo: str, ao_confirmar: Optional[Callable[[Any, str, Any], None]] = None) -> Dict[str, Any]:
    """
    Os argumentos de `carregar_tudo` para um modo: as cargas e as opções da carga de finanças (quais fontes rodam e, se
    dado, o gancho `ao_confirmar` que registra de onde veio o dado).
    """
    chaves = chaves_do_modo(modo)  # valida o modo
    if modo == "nenhuma":  # a carga de finanças não roda: nada a configurar nela
        return {"chaves": chaves, "opcoes": {}}
    opcoes_financas: Dict[str, Any] = {"chaves": FINANCAS_POR_MODO[modo]}
    if ao_confirmar is not None:
        opcoes_financas["ao_confirmar"] = ao_confirmar
    return {"chaves": chaves, "opcoes": {"financas": opcoes_financas}}


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
    opcoes: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Executa as cargas (as `chaves`, ou todas) e devolve o resultado de cada uma; levanta RuntimeError no fim.

    Sem `chaves`, o modo das finanças vem do banco (`modo_de_semeadura`): só se semeia do git a fonte que o `fin` ainda
    não tem ou que o timer ainda não assumiu; o resto fica só com as cargas estáticas. `recarregar_ceap_e_emendas` força o
    modo "completa" (por exemplo, depois de regerar os arquivos à mão). `opcoes` é um dicionário por carga com os argumentos
    nomeados que ela recebe depois do `engine` (hoje só a de finanças: `chaves`, as fontes que rodam, e `ao_confirmar`, o
    gancho que roda na transação de cada fonte e registra de onde veio o dado). Com `chaves` explícitas que incluem
    "financas", as fontes precisam vir em `opcoes["financas"]["chaves"]` (senão rodariam todas, inclusive CEAP e emendas
    do git); sem `chaves`, quem decide as fontes é o modo, e pedi-las em `opcoes` é erro, não é ignorado em silêncio. Também
    é erro `opcoes` de uma carga que não existe ou que não roda nesta chamada (o gancho seria descartado).

    Uma carga em `toleradas` que falha não levanta: o erro é registrado no log e devolvido como `{"erro": ...}` no
    resultado dela. O deploy usa isso para as finanças: a API nova continua servindo o que já está em `fin` em vez de
    deixar o checkout no compose novo com os contêineres antigos no ar.
    """
    aceitas = set(toleradas)
    opcoes_pedidas = {chave: dict(valores) for chave, valores in (opcoes or {}).items()}
    conhecidas = {chave for chave, *_ in CARGAS}
    if set(opcoes_pedidas) - conhecidas:
        raise ValueError(
            f"opcoes de carga desconhecida: {sorted(set(opcoes_pedidas) - conhecidas)} (esperado {sorted(conhecidas)})"
        )
    pedidas_pelo_chamador = set(opcoes_pedidas)
    if chaves is None:
        if "chaves" in opcoes_pedidas.get("financas", {}):
            raise ValueError("sem `chaves`, as fontes das finanças vêm do modo; não passe opcoes['financas']['chaves']")
        if recarregar_ceap_e_emendas:
            modo: Optional[str] = "completa"
        else:
            tem_ceap, tem_emendas = estado_do_fin(engine)
            do_timer = fontes_do_timer(engine) if (tem_ceap or tem_emendas) else set()
            modo = modo_de_semeadura(tem_ceap, tem_emendas, "ceap" in do_timer, "emendas" in do_timer)
        modo = modo or "estaticas"
        plano = plano_do_modo(modo)
        chaves = plano["chaves"]
        for chave, valores in plano["opcoes"].items():
            opcoes_pedidas[chave] = {**valores, **opcoes_pedidas.get(chave, {})}
        logger.info("Finanças em modo '%s'", modo)
    escolhidas = set(chaves)
    if pedidas_pelo_chamador - escolhidas:
        # um gancho de uma carga que não roda seria descartado em silêncio (e a posse da fonte não seria revogada)
        raise ValueError(f"opcoes para cargas que não rodam: {sorted(pedidas_pelo_chamador - escolhidas)}")
    if "financas" in escolhidas and "chaves" not in opcoes_pedidas.get("financas", {}):
        raise ValueError("a carga de finanças exige opcoes['financas']['chaves'] (as fontes que rodam; None = todas)")
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
            resultados[chave] = _carga_de(modulo)(engine, **opcoes_pedidas.get(chave, {}))
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
