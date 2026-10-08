"""Vínculo nome do autor (Portal da Transparência) -> parlamentar (Câmara/Senado).

Regra: somente correspondência EXATA do nome normalizado (sem acento, maiúsculo,
pontuação colapsada) e ÚNICA entre todos os parlamentares conhecidos. Qualquer
ambiguidade (homônimos, nome que bate com dois cadastros) resulta em "sem vínculo".
Nada de substring, similaridade ou remoção de títulos: um falso positivo atribuiria
dinheiro público à pessoa errada.
"""

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Parlamentar identificado por (casa, id): ("camara", 204554) ou ("senado", 5672)
ChaveParlamentar = Tuple[str, int]


def normalizar_nome(nome: Optional[str]) -> str:
    if not nome:
        return ""
    s = unicodedata.normalize("NFKD", str(nome))
    s = "".join(c for c in s if not unicodedata.combining(c)).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return " ".join(s.split())


def indexar_parlamentares(
    deputados: Iterable[dict], senadores: Iterable[dict]
) -> Dict[str, Set[ChaveParlamentar]]:
    """Índice nome_normalizado -> conjunto de parlamentares com esse nome
    (nome eleitoral OU nome civil)."""
    indice: Dict[str, Set[ChaveParlamentar]] = {}

    def _add(nome: Optional[str], chave: ChaveParlamentar):
        n = normalizar_nome(nome)
        if n:
            indice.setdefault(n, set()).add(chave)

    for d in deputados:
        cid = d.get("camara_id")
        if cid is None:
            continue
        chave = ("camara", int(cid))
        _add(d.get("nome_eleitoral"), chave)
        _add(d.get("nome_civil"), chave)
    for s in senadores:
        sid = s.get("senado_id")
        if sid is None:
            continue
        chave = ("senado", int(sid))
        _add(s.get("nome_eleitoral"), chave)
        _add(s.get("nome_civil"), chave)
    return indice


def casar_nome(nome_autor: str, indice: Dict[str, Set[ChaveParlamentar]]) -> Optional[ChaveParlamentar]:
    """Retorna o parlamentar se o nome bater exatamente com UM único cadastro."""
    candidatos = indice.get(normalizar_nome(nome_autor), set())
    if len(candidatos) == 1:
        return next(iter(candidatos))
    return None


CAMPOS_MAPA = [
    "codigo_autor_siafi", "nome_autor", "camara_id", "senado_id", "revisado",
    "uf_parlamentar", "uf_destino_predominante", "observacao",
]

# Nome da UF como aparece na coluna "UF" do CSV de emendas -> sigla
UF_POR_NOME = {
    "ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA",
    "CEARA": "CE", "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO",
    "MARANHAO": "MA", "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG",
    "PARA": "PA", "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI",
    "RIO DE JANEIRO": "RJ", "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS",
    "RONDONIA": "RO", "RORAIMA": "RR", "SANTA CATARINA": "SC", "SAO PAULO": "SP",
    "SERGIPE": "SE", "TOCANTINS": "TO",
}


def sigla_uf(nome_uf: Optional[str]) -> Optional[str]:
    """'SÃO PAULO' -> 'SP'; 'Múltiplo'/'Sem informação'/'Nacional' -> None."""
    n = normalizar_nome(nome_uf)
    if len(n) == 2 and n in UF_POR_NOME.values():
        return n
    return UF_POR_NOME.get(n)


def ufs_parlamentares(deputados: Iterable[dict], senadores: Iterable[dict]) -> Dict[ChaveParlamentar, str]:
    ufs: Dict[ChaveParlamentar, str] = {}
    for d in deputados:
        if d.get("camara_id") is not None and d.get("uf"):
            ufs[("camara", int(d["camara_id"]))] = str(d["uf"]).upper()
    for s in senadores:
        if s.get("senado_id") is not None and s.get("uf"):
            ufs[("senado", int(s["senado_id"]))] = str(s["uf"]).upper()
    return ufs


def uf_predominante(ufs_destino: Iterable[Optional[str]]) -> Optional[str]:
    """UF (sigla) mais frequente entre os destinos com UF definida; None se não houver
    ou se houver empate no topo."""
    cont: Dict[str, int] = {}
    for u in ufs_destino:
        s = sigla_uf(u)
        if s:
            cont[s] = cont.get(s, 0) + 1
    if not cont:
        return None
    ordenado = sorted(cont.items(), key=lambda kv: -kv[1])
    if len(ordenado) > 1 and ordenado[0][1] == ordenado[1][1]:
        return None
    return ordenado[0][0]


def uf_compativel(uf_parlamentar: Optional[str], uf_destino: Optional[str]) -> bool:
    """Checagem só de REJEIÇÃO: emendas individuais vão majoritariamente para o estado
    do autor. Se a UF predominante dos destinos é conhecida e difere da UF do
    parlamentar casado pelo nome, o vínculo é tratado como homônimo provável."""
    if not uf_parlamentar or not uf_destino:
        return True
    return uf_parlamentar.upper() == uf_destino.upper()


def propor_mapa(
    autores: Iterable[Tuple[str, str]],
    indice: Dict[str, Set[ChaveParlamentar]],
    ufs: Optional[Dict[ChaveParlamentar, str]] = None,
    destinos_por_autor: Optional[Dict[Tuple[str, str], Optional[str]]] = None,
) -> List[dict]:
    """Gera linhas do mapa autor->parlamentar para revisão humana (revisado=nao).

    destinos_por_autor: (codigo, nome) -> UF predominante dos destinos (sigla).
    """
    ufs = ufs or {}
    destinos_por_autor = destinos_por_autor or {}
    linhas = []
    for codigo, nome in sorted(set(autores), key=lambda t: (normalizar_nome(t[1]), t[0])):
        match = casar_nome(nome, indice)
        uf_dest = destinos_por_autor.get((codigo, nome))
        uf_parl = ufs.get(match) if match else None
        obs = ""
        n_cand = len(indice.get(normalizar_nome(nome), set()))
        if match is None:
            obs = "ambiguo" if n_cand > 1 else "sem_correspondencia"
        elif not uf_compativel(uf_parl, uf_dest):
            obs = "uf_divergente"
            match = None
        linhas.append({
            "codigo_autor_siafi": codigo,
            "nome_autor": nome,
            "camara_id": str(match[1]) if match and match[0] == "camara" else "",
            "senado_id": str(match[1]) if match and match[0] == "senado" else "",
            "revisado": "nao",
            "uf_parlamentar": uf_parl or "",
            "uf_destino_predominante": uf_dest or "",
            "observacao": obs,
        })
    return linhas


def resolver_mapa(
    linhas: Iterable[dict],
    indice: Dict[str, Set[ChaveParlamentar]],
    ufs: Optional[Dict[ChaveParlamentar, str]] = None,
    destinos_por_autor: Optional[Dict[Tuple[str, str], Optional[str]]] = None,
) -> Tuple[Dict[Tuple[str, str], ChaveParlamentar], Dict[str, int]]:
    """Decide quais linhas do mapa o loader pode usar.

    - revisado=sim: confia no camara_id/senado_id informado (revisão humana);
    - revisado=nao (ou vazio): só usa se o id preenchido for exatamente o resultado
      do casamento exato+único recalculado agora E a UF não divergir (impede edição
      manual não revisada e protege contra mudança nos cadastros desde a geração);
    - qualquer outro valor (ex.: "rejeitado"): ignora.
    Linhas com os dois ids, ou nenhum, nunca são usadas.

    A UF predominante dos destinos é recalculada a partir das emendas quando
    `destinos_por_autor` é informado (o loader faz isso); a coluna do CSV só é usada
    como alternativa.
    """
    ufs = ufs or {}
    usar: Dict[Tuple[str, str], ChaveParlamentar] = {}
    stats = {"revisado_sim": 0, "automatico": 0, "sem_vinculo": 0, "divergente": 0, "rejeitado": 0}

    def _uf_dest(codigo, nome, ln):
        if destinos_por_autor is not None and (codigo, nome) in destinos_por_autor:
            return destinos_por_autor[(codigo, nome)]
        return (ln.get("uf_destino_predominante") or "").strip() or None

    for ln in linhas:
        codigo = (ln.get("codigo_autor_siafi") or "").strip()
        nome = (ln.get("nome_autor") or "").strip()
        cam = (ln.get("camara_id") or "").strip()
        sen = (ln.get("senado_id") or "").strip()
        rev = (ln.get("revisado") or "nao").strip().lower()
        if rev not in ("sim", "nao", "não"):
            stats["rejeitado"] += 1
            continue
        if bool(cam) == bool(sen):
            stats["sem_vinculo"] += 1
            continue
        try:
            chave = ("camara", int(cam)) if cam else ("senado", int(sen))
        except ValueError:
            stats["sem_vinculo"] += 1
            continue
        if rev == "sim":
            usar[(codigo, nome)] = chave
            stats["revisado_sim"] += 1
        elif casar_nome(nome, indice) == chave and uf_compativel(ufs.get(chave), _uf_dest(codigo, nome, ln)):
            usar[(codigo, nome)] = chave
            stats["automatico"] += 1
        else:
            stats["divergente"] += 1
    return usar, stats


def destinos_por_autor(registros: Iterable[dict]) -> Dict[Tuple[str, str], Optional[str]]:
    """(codigo_autor_siafi, nome_autor) -> UF predominante dos destinos das emendas."""
    por_autor: Dict[Tuple[str, str], List[Optional[str]]] = {}
    for r in registros:
        por_autor.setdefault((r.get("codigo_autor_siafi") or "", r.get("nome_autor") or ""), []).append(r.get("uf"))
    return {k: uf_predominante(v) for k, v in por_autor.items()}
