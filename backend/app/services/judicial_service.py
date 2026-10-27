"""
Consolidação judicial do dossiê (Raio-X): junta os processos do DataJud (`fin.processo_judicial`) e as certidões do TSE
(`fin.certidao`) no contrato que a rota devolve. Funções puras sobre os dados que `financas_service` já leu, sem banco.
"""

from typing import Any, Dict, List

from app.services.financas_service import Certidao, Processo


def classe_e_assuntos(p: Processo) -> str:
    """ "Classe / Assunto 1, Assunto 2" (a classe sozinha quando o DataJud não trouxe assunto)."""
    return f"{p.classe} / {', '.join(p.assuntos)}" if p.assuntos else p.classe


def processo_detalhado(p: Processo) -> Dict[str, Any]:
    """
    Processo do DataJud no contrato do Raio-X: sem desfecho inferido, só o último movimento que o tribunal registrou e o
    dia em que o DataJud foi consultado (o andamento pode ter mudado depois). Dado que o DataJud não trouxe vai como None.
    """
    if p.ultimo_movimento:
        quando = f" ({p.data_ultimo_movimento})" if p.data_ultimo_movimento else ""
        situacao = f"Último movimento registrado no DataJud: {p.ultimo_movimento}{quando}."
    else:
        situacao = "Sem movimentação registrada no DataJud."
    if p.consultado_em:
        situacao += f" Consultado em {p.consultado_em}."
    return {
        "numero_processo": p.numero_processo,
        "tribunal": p.tribunal,
        "data_processo": p.data_processo,
        "classe_assunto": classe_e_assuntos(p),
        "descricao": f"Órgão julgador: {p.orgao_julgador}" if p.orgao_julgador else None,
        "situacao_juridica": situacao,
        "link_comprovacao": p.link_comprovacao,
        "status_resumo": f"DataJud · {p.grau}" if p.grau else "DataJud",
    }


def certidao_positiva(c: Certidao) -> bool:
    status = (c.status or "").lower()
    return "positiva" in status or "declarada" in status


def certidao_detalhada(c: Certidao) -> Dict[str, Any]:
    """
    Certidão positiva/declarada do TSE no mesmo contrato do processo do DataJud. O TSE declara o registro, não o
    andamento: a situação jurídica fica None (nada é inferido) e o front mostra "n/d".
    """
    return {
        "numero_processo": c.process_number,
        "tribunal": c.court_agency,
        "data_processo": c.issue_date,
        "classe_assunto": c.certificate_type,
        "descricao": c.details,
        "situacao_juridica": None,
        "link_comprovacao": c.proof_url,
        "status_resumo": "Declarado no TSE",
    }


def enriquecer_registros_judiciais(certidoes_db: List[Certidao], processos_db: List[Processo]) -> Dict[str, Any]:
    """
    Consolida dados judiciais a partir de `fin.processo_judicial` (DataJud) e `fin.certidao` (TSE).
    Campos ausentes são devolvidos como None, nos dois tipos de item: nenhum número de processo, data ou código é
    inventado. A flag legada `politicos.possuiProcessosDeclarados` não conta: ela foi copiada de um acervo transcrito à
    mão (D7) e, sem o processo para mostrar, o selo "Processos Vinculados" não teria o que comprovar. O selo vale para
    "há processo ou certidão positiva ligado por fonte oficial": a curadoria não guarda o papel da pessoa no processo.
    """
    # A certidão positiva entra na lista com o que ela realmente registra, junto dos processos do DataJud (os dois
    # dizem coisas diferentes: o TSE declara o registro, o DataJud traz o processo)
    processos_detalhados: List[Dict[str, Any]] = [processo_detalhado(p) for p in processos_db]
    processos_detalhados += [certidao_detalhada(c) for c in certidoes_db if certidao_positiva(c)]

    # Processo localizado ou certidão positiva/declarada registrada significa que há processos
    possui_processos = len(processos_detalhados) > 0

    certidoes_lista = []
    orgaos_declarados = []
    for c in certidoes_db:
        status_c = c.status or ""
        if certidao_positiva(c):
            orgaos_declarados.append(c.court_agency)

        certidoes_lista.append(
            {
                "id": str(c.id),
                "orgao": c.court_agency,
                "tipo_certidao": c.certificate_type,
                "tipo": c.certificate_type,
                "status_ficha": status_c,
                "status": status_c,
                "detalhes": c.details,
                "numero_processo": c.process_number,
                "data_emissao": c.issue_date,
                "link_comprovacao": c.proof_url,
                "codigo_autenticidade": c.auth_code,
            }
        )

    return {
        "possui_processos_declarados": possui_processos,
        # "Nada Consta" só é afirmado quando há certidão registrada; sem nenhum dado o status é null (desconhecido)
        "status_geral": (
            "Processos Vinculados" if possui_processos else ("Nada Consta (Ficha Limpa)" if certidoes_lista else None)
        ),
        "dados_certidoes_disponiveis": len(certidoes_lista) > 0 or len(processos_detalhados) > 0,
        "orgaos_declarados": sorted(set(orgaos_declarados)),
        # Portal público de consulta (não aponta para um candidato específico)
        "link_tse_divulgacand": "https://divulgacandcontas.tse.jus.br/divulga/#/",
        "processos_detalhados": processos_detalhados,
        "certidoes": certidoes_lista,
    }
