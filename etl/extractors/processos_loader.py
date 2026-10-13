"""
Módulo de Persistência de Processos Judiciais (STF, TSE, TRF e STJ) na tabela `processos_judiciais`.

ATENÇÃO — os registros abaixo foram transcritos manualmente (números de processo, ementas, desfechos) e
NÃO são verificados contra os tribunais por este projeto. Afirmações sobre processos de pessoas reais
(absolvições, anulações, inelegibilidade) exigem checagem na fonte primária. Por isso a carga só acontece
quando o operador a autoriza EXPLICITAMENTE (`allow_unverified=True` / `--allow-unverified-legal`).
"""

import argparse
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datajud_client import DataJudClient, parse_cnj_parts
from etl.utils.names import normalize_name_tokens

ensure_backend_on_path()
from app.models.politician import Politician, ProcessoJudicial  # noqa: E402

logger = logging.getLogger("processos_loader")

# Acervo MANUAL de processos (transcrição não verificada contra os tribunais — ver docstring do módulo)
REGISTROS_PROCESSUAIS_NOTORIOS: Dict[str, List[Dict[str, Any]]] = {
    "jair_bolsonaro": [
        {
            "numero_processo": "AIJE 0600814-85.2022.6.00.0000",
            "tribunal": "TSE (Tribunal Superior Eleitoral)",
            "data_processo": "30/06/2023",
            "classe_assunto": "Ação de Investigação Judicial Eleitoral / Uso Indevido dos Meios de Comunicação",
            "descricao": "Declarações públicas perante o corpo diplomático no Palácio da Alvorada acerca do sistema de votação eletrônico.",
            "situacao_juridica": "Julgada Procedente por maioria (5x2) pelo Tribunal Superior Eleitoral, aplicando sanção de inelegibilidade por 8 anos a contar de 2022.",
            "link_comprovacao": "https://consultapublica.tse.jus.br/consulta/#/processo/0600814-85.2022.6.00.0000",
            "status_resumo": "Julgado Procedente (TSE)",
        },
        {
            "numero_processo": "Pet 12100 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "08/02/2024",
            "classe_assunto": "Petição Criminal / Inquéritos Constitucionais dos Atos de 8 de Janeiro",
            "descricao": "Medidas investigatórias no bojo da Operação Tempus Veritatis sobre articulações institucionais pós-pleito de 2022.",
            "situacao_juridica": "Em tramitação sob a relatoria do Min. Alexandre de Moraes. Medidas restritivas vigentes; sem denúncia penal definitiva recebida.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6851214",
            "status_resumo": "Em Tramitação (STF)",
        },
        {
            "numero_processo": "Inq 4878 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "12/08/2021",
            "classe_assunto": "Inquérito Criminal / Divulgação de Documento Sigiloso",
            "descricao": "Investigação referente à transmissão ao vivo com leitura de relatórios técnicos sobre ataques cibernéticos ao TSE.",
            "situacao_juridica": "Em andamento no STF; manifestação da Procuradoria-Geral da República pendente de deliberação.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6241315",
            "status_resumo": "Em Tramitação (STF)",
        },
    ],
    "lula": [
        {
            "numero_processo": "HC 193.726 / PR (Plenário)",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "15/04/2021",
            "classe_assunto": "Habeas Corpus Constitucional / Nulidade Processual por Incompetência do Juízo",
            "descricao": "Contestação da competência territorial da 13ª Vara Federal de Curitiba para processamento de feitos conexos da Operação Lava Jato.",
            "situacao_juridica": "Decisão do Plenário do STF declarou a incompetência do juízo de Curitiba e a anulação de todos os atos decisórios, restabelecendo a plenitude dos direitos políticos e a condição de ficha limpa.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6044738",
            "status_resumo": "Decisão Transitada / Anulado pelo STF",
        },
        {
            "numero_processo": "Rcl 43007 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "09/02/2021",
            "classe_assunto": "Reclamação Constitucional / Prova Ilícita e Quebra de Imparcialidade",
            "descricao": "Acesso a acervo probatório da Operação Spoofing contendo mensagens entre magistrado e procuradores.",
            "situacao_juridica": "Procedente perante a 2ª Turma do STF, ensejando posterior declaração de suspeição do juiz de piso (HC 164.493).",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5985120",
            "status_resumo": "Procedente (STF)",
        },
        {
            "numero_processo": "Ação Penal 1026137-89.2019.4.01.3400",
            "tribunal": "TRF-1 (12ª Vara Federal Criminal do DF)",
            "data_processo": "23/11/2019",
            "classe_assunto": "Ação Penal / Suposta Associação Ilícita",
            "descricao": 'Denúncia do MPF relativa a repasses e suposta articulação partidária ("Quadrilhão do PT").',
            "situacao_juridica": "Absolvição sumária por ausência de justa causa e atipicidade da conduta, com trânsito em julgado certificado.",
            "link_comprovacao": "https://pje1g.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam",
            "status_resumo": "Absolvição Sumária Transitada",
        },
    ],
    "eduardo_bolsonaro": [
        {
            "numero_processo": "Pet 8243 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "22/10/2019",
            "classe_assunto": "Petição Criminal / Imunidade Parlamentar Material (Art. 53 da CF)",
            "descricao": "Representações por manifestações sobre a edição de medidas excepcionais de segurança de Estado.",
            "situacao_juridica": "Arquivada pelo relator no STF acolhendo promoção formal de arquivamento da Procuradoria-Geral da República (PGR).",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5784321",
            "status_resumo": "Arquivado pela PGR / STF",
        },
        {
            "numero_processo": "Inq 4878 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "12/08/2021",
            "classe_assunto": "Inquérito Criminal / Atos e Publicações Digitais",
            "descricao": "Apuração no STF referente à divulgação de documentos e pronunciamentos em mídias sociais.",
            "situacao_juridica": "Em tramitação no STF sob relatoria do Min. Alexandre de Moraes; sem denúncia recebida ou condenação.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6241315",
            "status_resumo": "Em Tramitação",
        },
    ],
    "flavio_bolsonaro": [
        {
            "numero_processo": "HC 648.512 / RJ",
            "tribunal": "STJ (Superior Tribunal de Justiça)",
            "data_processo": "09/11/2021",
            "classe_assunto": "Habeas Corpus / Nulidade de Provas por Quebra Ilícita de Sigilo",
            "descricao": 'PIC 2018.00494541 referente a movimentações financeiras de servidores do gabinete da ALERJ ("Rachadinha").',
            "situacao_juridica": "5ª Turma do STJ anulou todas as provas e decisões decorrentes de compartilhamento de dados fiscais sem autorização judicial prévia, extinguindo a denúncia.",
            "link_comprovacao": "https://processo.stj.jus.br/processo/pesquisa/?num_registro=202100584120",
            "status_resumo": "Anulado pelo STJ",
        },
        {
            "numero_processo": "Rcl 41042 / RJ",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "25/06/2020",
            "classe_assunto": "Reclamação Constitucional / Prerrogativa de Foro",
            "descricao": "Fixação de competência jurisdicional para processar fatos do mandato na ALERJ.",
            "situacao_juridica": "STF chancelou o julgamento originário pelo Órgão Especial do TJ-RJ; autos extintos e arquivados.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5939882",
            "status_resumo": "Extinto e Arquivado",
        },
    ],
    "sergio_moro": [
        {
            "numero_processo": "RO-AIJE 0604176-51.2022.6.16.0000",
            "tribunal": "TSE (Tribunal Superior Eleitoral)",
            "data_processo": "21/05/2024",
            "classe_assunto": "Recurso Ordinário Eleitoral / Suposto Abuso de Poder Econômico em Pré-Campanha",
            "descricao": "Ação promovida pelo PL e pela Federação Brasil da Esperança impugnando despesas de pré-campanha ao Senado Federal.",
            "situacao_juridica": "O Plenário do TSE negou provimento aos recursos por unanimidade (7 votos a 0), julgando a ação totalmente improcedente e ratificando o mandato eletivo de Senador.",
            "link_comprovacao": "https://consultapublica.tse.jus.br/consulta/#/processo/0604176-51.2022.6.16.0000",
            "status_resumo": "Julgado Improcedente (Absolvição Plena TSE)",
        },
        {
            "numero_processo": "Inq 4831 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "27/04/2020",
            "classe_assunto": "Inquérito Criminal / Prerrogativa de Função",
            "descricao": "Averiguação instaurada para apurar declarações sobre interferência administrativa em órgãos federais.",
            "situacao_juridica": "Conclusão policial sem indiciamento; arquivado definitivamente pelo STF por ausência de tipicidade penal a pedido da PGR.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5898858",
            "status_resumo": "Arquivado pelo STF",
        },
    ],
    "renan_calheiros": [
        {
            "numero_processo": "Inq 3989 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "13/04/2021",
            "classe_assunto": "Inquérito Criminal / Foro por Prerrogativa de Função",
            "descricao": "Investigação originária da Operação Lava Jato referente a aportes de campanhas eleitorais e contratações estatais.",
            "situacao_juridica": "2ª Turma do STF rejeitou a denúncia ministerial e determinou o arquivamento definitivo por carência probatória.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=4735201",
            "status_resumo": "Arquivado pelo STF",
        },
        {
            "numero_processo": "AP 1025 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "08/11/2022",
            "classe_assunto": "Ação Penal Originária / Suposto Desvio de Verba Indenizatória",
            "descricao": "Acusação de desvio de verbas indenizatórias parlamentares entre 2004 e 2006.",
            "situacao_juridica": "Julgada improcedente com absolvição na 2ª Turma do STF diante da inexistência de comprovação de dolo.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5129840",
            "status_resumo": "Absolvido pelo STF",
        },
    ],
    "michel_temer": [
        {
            "numero_processo": "Ação Penal 0500582-84.2019.4.02.5101",
            "tribunal": "TRF-2 (7ª Vara Federal Criminal do RJ)",
            "data_processo": "04/05/2021",
            "classe_assunto": "Ação Penal / Operação Descontaminação (Eletronuclear / Angra 3)",
            "descricao": "Denúncia relativa a supostas vantagens indevidas em contratos da usina termonuclear de Angra 3.",
            "situacao_juridica": "Sentença federal de mérito absolveu Michel Temer por manifesta atipicidade e falta de elementos de corroboração.",
            "link_comprovacao": "https://eproc.trf2.jus.br/eproc/externo_controlador.php?acao=processo_selecionar&num_processo=05005828420194025101",
            "status_resumo": "Absolvido pela Justiça Federal",
        },
        {
            "numero_processo": "Ação Penal 1018386-30.2018.4.01.3400",
            "tribunal": "TRF-1 (12ª Vara Federal de Brasília)",
            "data_processo": "01/12/2020",
            "classe_assunto": 'Ação Penal / Suposta Associação Partidária ("Quadrilhão do MDB")',
            "descricao": "Acusação ministerial decorrente do Inq 4327 da PGR remetida à 1ª instância.",
            "situacao_juridica": "Absolvição sumária confirmada em sede recursal por ausência de justa causa e falta de lastro probatório.",
            "link_comprovacao": "https://pje1g.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam",
            "status_resumo": "Absolvido Sumariamente",
        },
    ],
    "dilma_rousseff": [
        {
            "numero_processo": "Apelação Cível 1007783-58.2018.4.01.3400",
            "tribunal": "TRF-1 (10ª Turma / Justiça Federal)",
            "data_processo": "21/08/2023",
            "classe_assunto": "Ação Popular / Lei de Improbidade Administrativa (Lei 8.429/92)",
            "descricao": 'Ação popular proposta para responsabilização pessoal por atos de remanejamento orçamentário do Plano Safra ("Pedaladas Fiscais").',
            "situacao_juridica": "10ª Turma do TRF-1 manteve por unanimidade a improcedência e arquivamento, reconhecendo que não houve ato doloso de improbidade administrativa nem dano ao erário.",
            "link_comprovacao": "https://pje2g.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam",
            "status_resumo": "Ação Julgada Improcedente",
        },
        {
            "numero_processo": "MS 34371 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "19/10/2016",
            "classe_assunto": "Mandado de Segurança Constitucional",
            "descricao": "Mandado de Segurança questionando aspectos formais do rito processual do processo de impeachment no Senado.",
            "situacao_juridica": "Denegado e arquivado no STF, mantendo o desfecho político-constitucional do Senado.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5034120",
            "status_resumo": "Arquivado no STF",
        },
    ],
}


# Nomes normalizados (igualdade exata, nunca substring) que identificam cada pessoa do acervo.
ALIASES_REGISTROS: Dict[str, set] = {
    "jair_bolsonaro": {"jair bolsonaro", "jair messias bolsonaro"},
    "lula": {"lula", "luiz inacio lula da silva"},
    "eduardo_bolsonaro": {"eduardo bolsonaro", "eduardo nantes bolsonaro"},
    "flavio_bolsonaro": {"flavio bolsonaro", "flavio nantes bolsonaro"},
    "sergio_moro": {"sergio moro", "sergio fernando moro"},
    "renan_calheiros": {"renan calheiros", "jose renan vasconcelos calheiros"},
    "michel_temer": {"michel temer", "michel miguel elias temer lulia"},
    "dilma_rousseff": {"dilma rousseff", "dilma vana rousseff"},
}


def chave_registro(electoral_name: Optional[str], civil_name: Optional[str]) -> Optional[str]:
    """Chave do acervo para o político, por igualdade exata do nome normalizado. Homônimos não casam."""
    nomes = {normalize_name_tokens(electoral_name), normalize_name_tokens(civil_name)}
    for chave, aliases in ALIASES_REGISTROS.items():
        if nomes & aliases:
            return chave
    return None


def carregar_processos_enriquecidos_datajud(
    client: Optional[DataJudClient] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Consulta a API oficial do DataJud (CNJ) com cache local para os processos
    com numeração CNJ e enriquece os registros com metadados oficiais da TPU.
    """
    client = client or DataJudClient()
    acervo_enriquecido: Dict[str, List[Dict[str, Any]]] = {}

    for pol_chave, procs in REGISTROS_PROCESSUAIS_NOTORIOS.items():
        lista_pol = []
        for reg in procs:
            item = dict(reg)
            cnj = parse_cnj_parts(item.get("numero_processo", ""))
            if cnj:
                src = client.consultar_processo(cnj["limpo"])
                if src:
                    resumo = client.consolidar_resumo_processo(src)
                    item["tribunal"] = f"{resumo.get('tribunal', item['tribunal'])} (CNJ / DataJud)"
                    item["classe_assunto"] = resumo.get("classe_assunto", item["classe_assunto"])
                    item["data_processo"] = resumo.get("data_processo", item["data_processo"])
                    item["situacao_juridica"] = (
                        f"Oficial DataJud: {resumo.get('ultimo_movimento', 'Movimentação')} ({resumo.get('data_ultimo_movimento', '')}). "
                        f"Total de {resumo.get('total_movimentacoes', 0)} movimentações registradas na base nacional."
                    )
                    item["status_resumo"] = f"{resumo.get('classe_tpu_nome', 'Processo')} (DataJud)"
                    item["is_verified_datajud"] = True
                    item["fonte"] = "CNJ / DataJud (Base Nacional de Dados do Poder Judiciário)"
            lista_pol.append(item)
        acervo_enriquecido[pol_chave] = lista_pol
    return acervo_enriquecido


def populate_processos_judiciais(
    db: Session,
    allow_unverified: bool = False,
    use_datajud: bool = False,
    client: Optional[DataJudClient] = None,
) -> int:
    """
    Sincroniza `processos_judiciais` com o acervo.
    - Se `use_datajud=True`: carrega dados oficiais validados pelo CNJ / DataJud.
    - Se `allow_unverified=True`: autoriza também a carga de processos sem validação automatizada (ex: STF).
    - Se ambos falsos: nada é gravado.
    """
    if not allow_unverified and not use_datajud:
        logger.warning(
            "Carga de processos judiciais ignorada: use --allow-unverified-legal para acervo manual "
            "ou --use-datajud para carregar dados oficiais validados pelo CNJ."
        )
        return 0

    acervo = carregar_processos_enriquecidos_datajud(client) if use_datajud else REGISTROS_PROCESSUAIS_NOTORIOS
    pols = db.query(Politician).all()
    total_inseridos = 0

    for pol in pols:
        chave = chave_registro(pol.electoral_name, pol.civil_name)
        registros = acervo.get(chave, []) if chave else []
        if not registros:
            continue

        if not allow_unverified:
            registros = [r for r in registros if r.get("is_verified_datajud")]

        if not registros:
            continue

        pol.possui_processos_declarados = True
        # Substitui apenas os processos DESTE político (idempotente).
        db.query(ProcessoJudicial).filter(ProcessoJudicial.politician_id == pol.id).delete()
        for reg in registros:
            db.add(
                ProcessoJudicial(
                    id=uuid.uuid4(),
                    politician_id=pol.id,
                    process_number=reg["numero_processo"],
                    court_agency=reg["tribunal"],
                    process_date=reg["data_processo"],
                    case_class=reg["classe_assunto"],
                    description=reg["descricao"],
                    legal_status=reg["situacao_juridica"],
                    proof_url=reg["link_comprovacao"],
                    status_summary=reg["status_resumo"],
                    is_declared_tse=True,
                )
            )
            total_inseridos += 1

    db.commit()
    logger.info(f"Sincronização de processos concluída: {total_inseridos} registros persistidos.")
    return total_inseridos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga do acervo manual de processos judiciais.")
    parser.add_argument(
        "--allow-unverified-legal",
        action="store_true",
        help="Autoriza gravar o acervo manual NÃO verificado contra os tribunais.",
    )
    parser.add_argument(
        "--use-datajud",
        action="store_true",
        help="Consulta e valida processos oficialmente através da API do DataJud / CNJ.",
    )
    cli_args = parser.parse_args()
    from app.core.database import SessionLocal

    with SessionLocal() as session:
        inseridos = populate_processos_judiciais(
            session,
            allow_unverified=cli_args.allow_unverified_legal,
            use_datajud=cli_args.use_datajud,
        )
        print(f"Total de processos judiciais persistidos no PostgreSQL: {inseridos}")
