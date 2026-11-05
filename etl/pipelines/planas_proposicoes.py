"""
Tabelas planas das proposições (`stg.camara_proposicao_api`, `stg.senado_proposicao_api`): uma linha por registro dos arquivos
`proposicoes_2023.json` e `proposicoes_senado.json`, com os valores que dependem só da própria linha (tipo, título, ementa,
eixo de impacto, autor que a fonte atesta). A que proposição e a que político cada registro corresponde é decisão da função SQL
`etl.preparar_proposicoes`, na fusão.

A autoria só vale quando a fonte a atesta (`autor_fonte`): arquivos legados atribuíam autor por rodízio quando a API falhava,
e sem proveniência não dá para separar o real do fabricado. Registro sem id da casa, ou fora do formato, é rejeitado aqui.
"""

import logging
from pathlib import Path
from typing import Any, List, Tuple

from etl.pipelines.loader_helpers import _to_date, classify_proposition_impact
from etl.pipelines.planas_cadastro import _gravar, _texto
from etl.pipelines.staging_proposicoes import URL_CAMARA, URL_SENADO, tipo_proposicao
from etl.utils.datafiles import load_json
from etl.utils.execucao import Contagem

logger = logging.getLogger("PlanasProposicoes")

COLUNAS_CAMARA = [
    "camara_id",
    "tipo",
    "numero",
    "ano",
    "titulo",
    "ementa",
    "area_tematica",
    "data_apresentacao",
    "reforma_estrutural",
    "iniciativa_executivo",
    "autor_nome",
    "autor_camara_id",
    "url_oficial",
    "eixo",
    "eixos",
]
COLUNAS_SENADO = [
    "senado_id",
    "tipo",
    "numero",
    "ano",
    "titulo",
    "ementa",
    "area_tematica",
    "data_apresentacao",
    "autor_nome",
    "autor_senado_id",
    "url_oficial",
    "eixo",
    "eixos",
]


def _data(valor: Any) -> Any:
    convertida = _to_date(valor)
    return convertida.isoformat() if convertida else None


def linhas_camara(data_dir: Path, allow_unverified: bool, contagem: Contagem) -> Tuple[List[List[Any]], int]:
    """As proposições da Câmara e quantas tiveram a autoria ignorada por falta de proveniência."""
    linhas: List[List[Any]] = []
    ignorados = 0
    for p in load_json(data_dir / "proposicoes_2023.json", []) or []:
        contagem.ler()
        cid = p.get("camara_id")
        if not cid:
            contagem.rejeitar("SEM_ID")
            continue
        contagem.gravar()
        tipo = (p.get("tipo") or "PL").upper()
        numero, ano = int(p.get("numero") or 0), int(p.get("ano") or 2023)
        titulo = p.get("titulo") or f"{tipo} {numero}/{ano}"
        ementa = p.get("ementa") or ""
        eixo, eixos = classify_proposition_impact(tipo, numero, ano, titulo, ementa)
        if p.get("autor_fonte") or allow_unverified:
            autor = p.get("autor_nome") or ("Poder Executivo" if p.get("iniciativa_executivo") else None)
            autor_id = p.get("autor_camara_id")
        else:
            autor = "Poder Executivo" if p.get("iniciativa_executivo") else None
            autor_id = None
            ignorados += 1
        linhas.append(
            [
                cid,
                tipo_proposicao(tipo),
                numero,
                ano,
                titulo,
                ementa[:1000] if ementa else "Sem ementa disponível",
                _texto(p.get("area_tematica")),
                _data(p.get("data_apresentacao")),
                "true" if p.get("is_reforma_estrutural", False) else "false",
                "true" if p.get("iniciativa_executivo", False) else "false",
                autor,
                autor_id or None,
                p.get("url_oficial") or URL_CAMARA.format(cid),
                eixo,
                eixos,
            ]
        )
    return linhas, ignorados


def linhas_senado(data_dir: Path, allow_unverified: bool, contagem: Contagem) -> Tuple[List[List[Any]], int]:
    linhas: List[List[Any]] = []
    ignorados = 0
    for p in load_json(data_dir / "proposicoes_senado.json", []) or []:
        contagem.ler()
        if not isinstance(p, dict):  # arquivo legado em formato {id: {...}} ou lista de ids
            contagem.rejeitar("FORMATO_LEGADO")
            continue
        sid = p.get("senado_id")
        if not sid:
            contagem.rejeitar("SEM_ID")
            continue
        contagem.gravar()
        tipo = (p.get("tipo") or "PL").upper()
        numero, ano = int(p.get("numero") or 0), int(p.get("ano") or 2023)
        titulo = p.get("titulo") or f"{tipo} {numero}/{ano}"
        ementa = p.get("ementa") or "Sem ementa disponível"
        eixo, eixos = classify_proposition_impact(tipo, numero, ano, titulo, ementa)
        if p.get("autor_fonte") or allow_unverified:
            autor = p.get("autor_nome")
        else:
            autor = None
            ignorados += 1
        linhas.append(
            [
                sid,
                tipo_proposicao(tipo),
                numero,
                ano,
                titulo,
                ementa[:1000],
                _texto(p.get("area_tematica")),
                _data(p.get("data_apresentacao")),
                autor,
                (p.get("autor_senado_id") if autor else None) or None,
                p.get("url_oficial") or URL_SENADO.format(sid),
                eixo,
                eixos,
            ]
        )
    return linhas, ignorados


def gravar_planas_proposicoes(cursor: Any, data_dir: Path, execucao_id: Any, allow_unverified: bool) -> Contagem:
    """Grava as duas tabelas planas e devolve a contagem de registros (rejeitados: `SEM_ID`, `FORMATO_LEGADO`)."""
    contagem = Contagem()
    camara, ig_c = linhas_camara(data_dir, allow_unverified, contagem)
    senado, ig_s = linhas_senado(data_dir, allow_unverified, contagem)
    _gravar(cursor, "stg.camara_proposicao_api", COLUNAS_CAMARA, camara, execucao_id)
    _gravar(cursor, "stg.senado_proposicao_api", COLUNAS_SENADO, senado, execucao_id)
    if ig_c + ig_s:
        logger.warning(
            "-> Autoria de %d proposições ignorada por falta de proveniência (arquivo legado). Reexecute a extração "
            "(--camara/--senado) ou use --allow-unverified para carregá-las mesmo assim.",
            ig_c + ig_s,
        )
    return contagem
