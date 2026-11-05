"""
Etapa 5 da carga do staging: proposições da Câmara e do Senado (`stg.proposicoes`).

Cada casa é identificada pelo seu id externo: Câmara e Senado numeram por conta própria, então casar o PL do Senado com "o PL
de mesmo número/ano" sobrescrevia autor, eixo e área de uma proposição da Câmara diferente. A autoria só vale quando a fonte a
atesta (`autor_fonte`); o nome do autor vira político pelo `AuthorResolver` (id oficial, depois nome único), nunca por palpite.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from etl.pipelines import stg_tabela
from etl.pipelines.loader_helpers import AuthorResolver, _to_date, classify_proposition_impact
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json
from etl.utils.execucao import Contagem

ensure_backend_on_path()

from app.models.enums import TipoProposicaoEnum  # noqa: E402

logger = logging.getLogger("StagingProposicoes")

URL_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"
URL_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"


def tipo_proposicao(tipo_str: Optional[str]) -> str:
    """O nome do tipo no enum do banco; tipo desconhecido vira PL (como no carregador anterior)."""
    nome = (tipo_str or "PL").upper()
    return nome if nome in TipoProposicaoEnum.__members__ else "PL"


def carregar_proposicoes(
    proposicoes: stg_tabela.Tabela,
    politicos: stg_tabela.Tabela,
    data_dir: Path,
    deputy_map: Dict[int, Any],
    senator_map: Dict[int, Any],
    allow_unverified: bool = False,
) -> Tuple[Dict[int, Any], Contagem]:
    """
    Proposições da Câmara e do Senado. Devolve `({id da Câmara: id da proposição}, contagem)`; registro sem id externo é
    rejeitado (`SEM_ID`) e `gravadas` inclui as que já estavam.
    """
    contagem = Contagem()
    prop_map: Dict[int, Any] = {}
    resolver = AuthorResolver(list(politicos), deputy_map, senator_map)
    por_camara = {p.external_camara_id: p for p in proposicoes if p.external_camara_id is not None}
    por_senado = {p.external_senado_id: p for p in proposicoes if p.external_senado_id is not None}
    data_aproximada = autores_ignorados = 0

    def data_apresentacao(valor: Any, ano: int) -> date:
        nonlocal data_aproximada
        dt = _to_date(valor)
        if dt is None:
            # Coluna obrigatória; a fonte não informou. 1º de janeiro do ano da proposição é só um limite inferior —
            # contabilizado e logado, nunca apresentado como data real.
            data_aproximada += 1
            return date(ano, 1, 1)
        return dt

    # A. Câmara dos Deputados
    total_camara = 0
    for p in load_json(data_dir / "proposicoes_2023.json", []) or []:
        contagem.ler()
        cid = p.get("camara_id")
        if not cid:
            contagem.rejeitar("SEM_ID")
            continue
        contagem.gravar()
        prop = por_camara.get(cid)
        tipo_str = (p.get("tipo") or "PL").upper()
        numero, ano = int(p.get("numero") or 0), int(p.get("ano") or 2023)
        titulo = p.get("titulo") or f"{tipo_str} {numero}/{ano}"
        ementa = p.get("ementa") or ""
        eixo_princ, eixos_tags = classify_proposition_impact(tipo_str, numero, ano, titulo, ementa)

        # Autoria só é usada quando a fonte a atesta (`autor_fonte`). Arquivos legados atribuíam autor por round-robin
        # quando a API falhava: sem proveniência não dá para separar o real do fabricado.
        if p.get("autor_fonte") or allow_unverified:
            autor_nome = p.get("autor_nome") or ("Poder Executivo" if p.get("iniciativa_executivo") else None)
            autor_camara_id = p.get("autor_camara_id")
        else:
            autor_nome = "Poder Executivo" if p.get("iniciativa_executivo") else None
            autor_camara_id = None
            autores_ignorados += 1
        autor_pol_id = resolver.resolve(autor_nome, camara_id=autor_camara_id)
        setor = p.get("area_tematica")
        url_oficial = p.get("url_oficial") or URL_CAMARA.format(cid)

        if not prop:
            prop = proposicoes.nova(
                external_camara_id=cid,
                proposition_type=tipo_proposicao(tipo_str),
                number=numero,
                year=ano,
                title=titulo,
                summary=ementa[:1000] if ementa else "Sem ementa disponível",
                thematic_area=setor,
                presentation_date=data_apresentacao(p.get("data_apresentacao"), ano),
                status="EM_TRAMITACAO",
                is_structural_reform=bool(p.get("is_reforma_estrutural", False)),
                is_executive_initiative=bool(p.get("iniciativa_executivo", False)),
                impact_axis=eixo_princ,
                impact_tags=eixos_tags,
                author_name=autor_nome,
                author_politician_id=autor_pol_id,
                official_url=url_oficial,
            )
            por_camara[cid] = prop
        else:
            prop.impact_axis, prop.impact_tags = eixo_princ, eixos_tags
            if setor:
                prop.thematic_area = setor
            if not prop.official_url or "camara.leg.br" not in prop.official_url:
                prop.official_url = url_oficial
            if autor_nome:
                # Autoria conhecida na fonte: o vínculo é recalculado (inclusive para None), o que desfaz vínculos errados
                # gravados por regras antigas. Fonte sem autor não apaga vínculo existente.
                prop.author_name = autor_nome
                prop.author_politician_id = autor_pol_id
        prop_map[cid] = prop.id
        total_camara += 1

    # B. Senado Federal — identificado só por `external_senado_id`
    total_senado = 0
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
        prop = por_senado.get(sid)
        tipo_str = (p.get("tipo") or "PL").upper()
        num_val, ano_val = int(p.get("numero") or 0), int(p.get("ano") or 2023)
        titulo = p.get("titulo") or f"{tipo_str} {num_val}/{ano_val}"
        ementa = p.get("ementa") or "Sem ementa disponível"
        eixo_princ, eixos_tags = classify_proposition_impact(tipo_str, num_val, ano_val, titulo, ementa)

        if p.get("autor_fonte") or allow_unverified:
            autor_nome = p.get("autor_nome")
        else:
            autor_nome = None
            autores_ignorados += 1
        autor_pol_id = resolver.resolve(autor_nome, senado_id=p.get("autor_senado_id") if autor_nome else None)
        setor = p.get("area_tematica")
        url_oficial = p.get("url_oficial") or URL_SENADO.format(sid)

        if not prop:
            prop = proposicoes.nova(
                external_senado_id=sid,
                proposition_type=tipo_proposicao(tipo_str),
                number=num_val,
                year=ano_val,
                title=titulo,
                summary=ementa[:1000],
                thematic_area=setor,
                presentation_date=data_apresentacao(p.get("data_apresentacao"), ano_val),
                status="EM_TRAMITACAO",
                is_structural_reform=False,
                is_executive_initiative=False,
                impact_axis=eixo_princ,
                impact_tags=eixos_tags,
                author_name=autor_nome,
                author_politician_id=autor_pol_id,
                official_url=url_oficial,
            )
            por_senado[sid] = prop
        else:
            prop.impact_axis, prop.impact_tags = eixo_princ, eixos_tags
            if setor:
                prop.thematic_area = setor
            if not prop.official_url:
                prop.official_url = url_oficial
            if autor_nome:
                prop.author_name = autor_nome
                prop.author_politician_id = autor_pol_id
        total_senado += 1

    # Completa urlOficial e eixo ausentes (sem inventar área temática)
    for pr in proposicoes:
        if pr.impact_axis is not None and pr.official_url is not None:
            continue
        if not pr.impact_axis:
            pr.impact_axis, pr.impact_tags = classify_proposition_impact(
                TipoProposicaoEnum[pr.proposition_type].value, pr.number, pr.year, pr.title, pr.summary or ""
            )
        if not pr.official_url:
            if pr.external_camara_id:
                pr.official_url = URL_CAMARA.format(pr.external_camara_id)
            elif pr.external_senado_id:
                pr.official_url = URL_SENADO.format(pr.external_senado_id)

    if autores_ignorados:
        logger.warning(
            "-> Autoria de %d proposições ignorada por falta de proveniência (arquivo legado). Reexecute a extração "
            "(--camara/--senado) ou use --allow-unverified para carregá-las mesmo assim.",
            autores_ignorados,
        )
    if data_aproximada:
        logger.warning(
            "-> %d proposições sem data de apresentação na fonte (usado 1º de janeiro do ano).", data_aproximada
        )
    logger.info("-> %d proposições da Câmara e %d do Senado carregadas.", total_camara, total_senado)
    return prop_map, contagem
