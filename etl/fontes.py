"""
Catálogo das fontes do ETL para o comando por fonte e por estágio:

    python -m etl.run_etl --fonte votacoes --estagio carregar
    python -m etl.run_etl --fonte politicos --fonte filiacoes          # extrai e carrega as duas
    python -m etl.run_etl --listar-fontes

Cada fonte diz que etapas da esteira a extraem e que recursos da carga relacional (`etl.carga.orquestra.RECURSOS`) ou que etapa de
carga a levam ao banco. Reexecutar uma fonte não toca nas outras: cada recurso grava direto em `core`/`leg` pela chave natural
(identificador oficial), então a ordem dos recursos é a de `RECURSOS` e a repetição não duplica nada.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

ESTAGIOS = ("extrair", "carregar", "tudo")


@dataclass(frozen=True)
class Fonte:
    descricao: str
    extrair: Tuple[str, ...] = ()  # chaves de etapa de `run_etl` que extraem os arquivos
    carregar: Tuple[str, ...] = ()  # chaves de etapa de `run_etl` de carga própria (lote, histórico, presença...)
    recursos: Tuple[str, ...] = field(default=())  # recursos da carga relacional (`load_db`)


FONTES: Dict[str, Fonte] = {
    "partidos": Fonte("Partidos políticos (curadoria e siglas das fontes)", recursos=("partidos",)),
    "politicos": Fonte(
        "Presidentes, deputados e senadores",
        extrair=("camara", "senado", "votacoes", "senadores_basicos", "senadores_filiacoes", "cpf"),
        recursos=("partidos", "pessoas"),
    ),
    "filiacoes": Fonte(
        "Filiações partidárias (derivadas dos períodos de partido de cada mandato)", recursos=("filiacoes",)
    ),
    "mandatos": Fonte(
        "Mandatos de presidentes, deputados e senadores e gabinete presidencial (saem dos mesmos arquivos dos políticos)",
        extrair=("camara", "senado", "senadores_basicos", "senadores_filiacoes"),
        recursos=("partidos", "pessoas"),
    ),
    "proposicoes": Fonte("Proposições da Câmara e do Senado", extrair=("camara", "senado"), recursos=("proposicoes",)),
    "votacoes": Fonte(
        "Votações nominais em plenário e histórico (Câmara e Senado) e ex-parlamentares",
        extrair=("camara", "senado", "votacoes", "senadores_basicos", "senadores_filiacoes", "cpf"),
        recursos=("partidos", "pessoas", "votacoes"),
    ),
    "camara-bulk": Fonte(
        "Proposições e autores de todos os anos (CSV em lote da Câmara)",
        extrair=("camara_bulk",),
        carregar=("camara_bulk",),
    ),
    "camara-historico": Fonte(
        "Histórico de mandatos dos deputados (Câmara)", extrair=("camara_historico",), carregar=("camara_historico",)
    ),
    "presenca": Fonte("Presença em plenário", extrair=("presenca",), carregar=("load_presenca",)),
    "economia": Fonte(
        "Séries econômicas, mandatos presidenciais, composição do Congresso, PNAD e finanças",
        extrair=("economic", "composicao", "pnad", "ceap"),
        carregar=("load_economia",),
    ),
}


def resolver(fontes: Sequence[str], estagio: str = "tudo") -> Tuple[List[str], List[str]]:
    """
    As chaves de etapa de `run_etl` (na ordem do catálogo da esteira, sem repetir) e os recursos da carga relacional que as
    fontes pedidas exigem no estágio dado. `camara-bulk` e `camara-historico` extraem e carregam na mesma etapa.
    """
    if estagio not in ESTAGIOS:
        raise ValueError(f"estágio desconhecido: {estagio!r}; use um de {ESTAGIOS}")
    desconhecidas = [f for f in fontes if f not in FONTES]
    if desconhecidas:
        raise ValueError(f"fonte desconhecida: {desconhecidas}; use uma de {sorted(FONTES)}")
    chaves: List[str] = []
    recursos: List[str] = []
    for slug in fontes:
        fonte = FONTES[slug]
        if estagio in ("extrair", "tudo"):
            chaves += [c for c in fonte.extrair if c not in chaves]
        if estagio in ("carregar", "tudo"):
            chaves += [c for c in fonte.carregar if c not in chaves]
            recursos += [r for r in fonte.recursos if r not in recursos]
    if recursos and "load_db" not in chaves:
        chaves.append("load_db")
    return chaves, recursos
