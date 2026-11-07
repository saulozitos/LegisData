"""Proposições dos arquivos da API da Câmara e do Senado (`proposicoes_2023.json`, `proposicoes_senado.json`)."""

from pathlib import Path
from typing import Any, List, Optional, Tuple

from etl.carga.base import Resultado, contagem_de, criar_rejeitos, executar_sql, ler_rejeitos, tabela_temporaria
from etl.carga.pessoas import _data, _texto
from etl.pipelines.loader_helpers import classify_proposition_impact, inteiro
from etl.utils.datafiles import load_json

URL_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"
URL_SENADO = "http://legis.senado.leg.br/dadosabertos/materia/{}"
COLUNAS = {
    "linha": "int",
    "casa": "text",
    "ext_id": "int",
    "tipo": "text",
    "numero": "int",
    "ano": "int",
    "titulo": "text",
    "ementa": "text",
    "area": "text",
    "data_apresentacao": "date",
    "url_oficial": "text",
    "reforma": "boolean",
    "executivo": "boolean",
    "autor_nome": "text",
    "autor_camara_id": "int",
    "eixo": "text",
    "eixos": "text",
}


def _linhas(
    data_dir: Path, arquivo: str, casa: str, chave_id: str, allow_unverified: bool
) -> Tuple[List[List[Any]], int, int]:
    """(linhas, lidas, sem_id). Autoria só vale com a fonte registrada (ou com `allow_unverified`)."""
    linhas: List[List[Any]] = []
    lidas = sem_id = 0
    for p in load_json(Path(data_dir) / arquivo, []) or []:
        lidas += 1
        if not isinstance(p, dict) or not inteiro(p.get(chave_id)):
            sem_id += 1
            continue
        ext_id = inteiro(p[chave_id])
        tipo = (_texto(p.get("tipo")) or "").upper()
        numero, ano = inteiro(p.get("numero")), inteiro(p.get("ano"))
        titulo, ementa = _texto(p.get("titulo")), _texto(p.get("ementa"))
        confiavel = bool(p.get("autor_fonte")) or allow_unverified
        executivo = bool(p.get("iniciativa_executivo", False))
        autor = _texto(p.get("autor_nome")) if confiavel else None
        if autor is None and executivo:
            autor = "Poder Executivo"
        eixo, eixos = classify_proposition_impact(tipo, numero or 0, ano or 0, titulo or "", ementa or "")
        linhas.append(
            [
                lidas,
                casa,
                ext_id,
                tipo,
                numero,
                ano,
                titulo,
                ementa,
                _texto(p.get("area_tematica")),
                _data(p.get("data_apresentacao")),
                _texto(p.get("url_oficial")) or (URL_CAMARA if casa == "CAMARA" else URL_SENADO).format(ext_id),
                bool(p.get("is_reforma_estrutural", False)),
                executivo,
                autor,
                (inteiro(p.get("autor_camara_id")) or None) if confiavel and casa == "CAMARA" else None,
                eixo,
                eixos,
            ]
        )
    return linhas, lidas, sem_id


def carregar_proposicoes(cursor: Any, data_dir: Path, allow_unverified: bool) -> Optional[Resultado]:
    camara, lidas_c, sem_c = _linhas(data_dir, "proposicoes_2023.json", "CAMARA", "camara_id", allow_unverified)
    senado, lidas_s, sem_s = _linhas(data_dir, "proposicoes_senado.json", "SENADO", "senado_id", allow_unverified)
    linhas = [[n, *linha[1:]] for n, linha in enumerate(camara + senado, start=1)]
    criar_rejeitos(cursor)
    tabela_temporaria(cursor, "_in_prop", COLUNAS, linhas)
    executar_sql(cursor, "proposicoes")
    rejeitos = ler_rejeitos(cursor)
    if sem_c + sem_s:
        rejeitos["SEM_ID_OU_FORMATO_LEGADO"] = sem_c + sem_s
    return Resultado(contagem_de(lidas_c + lidas_s, rejeitos))
