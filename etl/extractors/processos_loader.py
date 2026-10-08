"""
Módulo de Extração e Persistência de Processos Judiciais (STF, TSE, TRF e STJ).
Insere e atualiza os registros oficiais diretamente na tabela `processos_judiciais` do PostgreSQL.
"""

import uuid
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

try:
    from backend.app.models.politician import Politician, ProcessoJudicial
except ModuleNotFoundError:
    from app.models.politician import Politician, ProcessoJudicial

logger = logging.getLogger("processos_loader")

# Lista CURADA MANUALMENTE de processos públicos. Pendente de conferência
# registro a registro contra as páginas oficiais dos tribunais.
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
            "status_resumo": "Julgado Procedente (TSE)"
        },
        {
            "numero_processo": "Pet 12100 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "08/02/2024",
            "classe_assunto": "Petição Criminal / Inquéritos Constitucionais dos Atos de 8 de Janeiro",
            "descricao": "Medidas investigatórias no bojo da Operação Tempus Veritatis sobre articulações institucionais pós-pleito de 2022.",
            "situacao_juridica": "Em tramitação sob a relatoria do Min. Alexandre de Moraes. Medidas restritivas vigentes; sem denúncia penal definitiva recebida.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6851214",
            "status_resumo": "Em Tramitação (STF)"
        },
        {
            "numero_processo": "Inq 4878 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "12/08/2021",
            "classe_assunto": "Inquérito Criminal / Divulgação de Documento Sigiloso",
            "descricao": "Investigação referente à transmissão ao vivo com leitura de relatórios técnicos sobre ataques cibernéticos ao TSE.",
            "situacao_juridica": "Em andamento no STF; manifestação da Procuradoria-Geral da República pendente de deliberação.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6241315",
            "status_resumo": "Em Tramitação (STF)"
        }
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
            "status_resumo": "Decisão Transitada / Anulado pelo STF"
        },
        {
            "numero_processo": "Rcl 43007 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "09/02/2021",
            "classe_assunto": "Reclamação Constitucional / Prova Ilícita e Quebra de Imparcialidade",
            "descricao": "Acesso a acervo probatório da Operação Spoofing contendo mensagens entre magistrado e procuradores.",
            "situacao_juridica": "Procedente perante a 2ª Turma do STF, ensejando posterior declaração de suspeição do juiz de piso (HC 164.493).",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5985120",
            "status_resumo": "Procedente (STF)"
        },
        {
            "numero_processo": "Ação Penal 1026137-89.2019.4.01.3400",
            "tribunal": "TRF-1 (12ª Vara Federal Criminal do DF)",
            "data_processo": "23/11/2019",
            "classe_assunto": "Ação Penal / Suposta Associação Ilícita",
            "descricao": "Denúncia do MPF relativa a repasses e suposta articulação partidária (\"Quadrilhão do PT\").",
            "situacao_juridica": "Absolvição sumária por ausência de justa causa e atipicidade da conduta, com trânsito em julgado certificado.",
            "link_comprovacao": "https://pje1g.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam",
            "status_resumo": "Absolvição Sumária Transitada"
        }
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
            "status_resumo": "Arquivado pela PGR / STF"
        },
        {
            "numero_processo": "Inq 4878 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "12/08/2021",
            "classe_assunto": "Inquérito Criminal / Atos e Publicações Digitais",
            "descricao": "Apuração no STF referente à divulgação de documentos e pronunciamentos em mídias sociais.",
            "situacao_juridica": "Em tramitação no STF sob relatoria do Min. Alexandre de Moraes; sem denúncia recebida ou condenação.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=6241315",
            "status_resumo": "Em Tramitação"
        }
    ],
    "flavio_bolsonaro": [
        {
            "numero_processo": "HC 648.512 / RJ",
            "tribunal": "STJ (Superior Tribunal de Justiça)",
            "data_processo": "09/11/2021",
            "classe_assunto": "Habeas Corpus / Nulidade de Provas por Quebra Ilícita de Sigilo",
            "descricao": "PIC 2018.00494541 referente a movimentações financeiras de servidores do gabinete da ALERJ (\"Rachadinha\").",
            "situacao_juridica": "5ª Turma do STJ anulou todas as provas e decisões decorrentes de compartilhamento de dados fiscais sem autorização judicial prévia, extinguindo a denúncia.",
            "link_comprovacao": "https://processo.stj.jus.br/processo/pesquisa/?num_registro=202100584120",
            "status_resumo": "Anulado pelo STJ"
        },
        {
            "numero_processo": "Rcl 41042 / RJ",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "25/06/2020",
            "classe_assunto": "Reclamação Constitucional / Prerrogativa de Foro",
            "descricao": "Fixação de competência jurisdicional para processar fatos do mandato na ALERJ.",
            "situacao_juridica": "STF chancelou o julgamento originário pelo Órgão Especial do TJ-RJ; autos extintos e arquivados.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5939882",
            "status_resumo": "Extinto e Arquivado"
        }
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
            "status_resumo": "Julgado Improcedente (Absolvição Plena TSE)"
        },
        {
            "numero_processo": "Inq 4831 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "27/04/2020",
            "classe_assunto": "Inquérito Criminal / Prerrogativa de Função",
            "descricao": "Averiguação instaurada para apurar declarações sobre interferência administrativa em órgãos federais.",
            "situacao_juridica": "Conclusão policial sem indiciamento; arquivado definitivamente pelo STF por ausência de tipicidade penal a pedido da PGR.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5898858",
            "status_resumo": "Arquivado pelo STF"
        }
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
            "status_resumo": "Arquivado pelo STF"
        },
        {
            "numero_processo": "AP 1025 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "08/11/2022",
            "classe_assunto": "Ação Penal Originária / Suposto Desvio de Verba Indenizatória",
            "descricao": "Acusação de desvio de verbas indenizatórias parlamentares entre 2004 e 2006.",
            "situacao_juridica": "Julgada improcedente com absolvição na 2ª Turma do STF diante da inexistência de comprovação de dolo.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5129840",
            "status_resumo": "Absolvido pelo STF"
        }
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
            "status_resumo": "Absolvido pela Justiça Federal"
        },
        {
            "numero_processo": "Ação Penal 1018386-30.2018.4.01.3400",
            "tribunal": "TRF-1 (12ª Vara Federal de Brasília)",
            "data_processo": "01/12/2020",
            "classe_assunto": "Ação Penal / Suposta Associação Partidária (\"Quadrilhão do MDB\")",
            "descricao": "Acusação ministerial decorrente do Inq 4327 da PGR remetida à 1ª instância.",
            "situacao_juridica": "Absolvição sumária confirmada em sede recursal por ausência de justa causa e falta de lastro probatório.",
            "link_comprovacao": "https://pje1g.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam",
            "status_resumo": "Absolvido Sumariamente"
        }
    ],
    "dilma_rousseff": [
        {
            "numero_processo": "Apelação Cível 1007783-58.2018.4.01.3400",
            "tribunal": "TRF-1 (10ª Turma / Justiça Federal)",
            "data_processo": "21/08/2023",
            "classe_assunto": "Ação Popular / Lei de Improbidade Administrativa (Lei 8.429/92)",
            "descricao": "Ação popular proposta para responsabilização pessoal por atos de remanejamento orçamentário do Plano Safra (\"Pedaladas Fiscais\").",
            "situacao_juridica": "10ª Turma do TRF-1 manteve por unanimidade a improcedência e arquivamento, reconhecendo que não houve ato doloso de improbidade administrativa nem dano ao erário.",
            "link_comprovacao": "https://pje2g.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam",
            "status_resumo": "Ação Julgada Improcedente"
        },
        {
            "numero_processo": "MS 34371 / DF",
            "tribunal": "STF (Supremo Tribunal Federal)",
            "data_processo": "19/10/2016",
            "classe_assunto": "Mandado de Segurança Constitucional",
            "descricao": "Mandado de Segurança questionando aspectos formais do rito processual do processo de impeachment no Senado.",
            "situacao_juridica": "Denegado e arquivado no STF, mantendo o desfecho político-constitucional do Senado.",
            "link_comprovacao": "https://portal.stf.jus.br/processos/detalhe.asp?incidente=5034120",
            "status_resumo": "Arquivado no STF"
        }
    ]
}


# Vínculo EXPLÍCITO entre o político e o conjunto de registros, pelo nome civil
# completo normalizado (sem acentos, minúsculo). Correspondência por substring
# ("calheiros", "moro", "lula"...) atribuía processos a homônimos, por exemplo:
# Renildo Calheiros, Renan Filho, Rosângela Moro, Lula da Fonte.
NOME_CIVIL_PARA_CHAVE: Dict[str, str] = {
    "jair messias bolsonaro": "jair_bolsonaro",
    "luiz inacio lula da silva": "lula",
    "eduardo nantes bolsonaro": "eduardo_bolsonaro",
    "flavio nantes bolsonaro": "flavio_bolsonaro",
    "sergio fernando moro": "sergio_moro",
    "jose renan vasconcelos calheiros": "renan_calheiros",
    "michel miguel elias temer lulia": "michel_temer",
    "dilma vana rousseff": "dilma_rousseff",
}


def _normalizar(nome: Optional[str]) -> str:
    import unicodedata
    if not nome:
        return ""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", nome) if unicodedata.category(c) != "Mn"
    )
    return " ".join(sem_acento.lower().split())


def populate_processos_judiciais(db: Session) -> int:
    """
    Popula a tabela `processos_judiciais` com a lista curada acima.

    ATENÇÃO: os registros de REGISTROS_PROCESSUAIS_NOTORIOS foram digitados à mão e
    precisam de conferência humana (número, tribunal, situação e link) antes de
    serem publicados. O vínculo é feito apenas por nome civil completo exato.
    """
    pols = db.query(Politician).all()
    total_inseridos = 0

    for pol in pols:
        chave = NOME_CIVIL_PARA_CHAVE.get(_normalizar(pol.civil_name))
        registros = REGISTROS_PROCESSUAIS_NOTORIOS.get(chave, []) if chave else []

        if registros:
            # Remove processos anteriores para evitar duplicação idempotente
            db.query(ProcessoJudicial).filter(ProcessoJudicial.politician_id == pol.id).delete()

            for reg in registros:
                p_item = ProcessoJudicial(
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
                    is_declared_tse=False
                )
                db.add(p_item)
                total_inseridos += 1

    db.commit()
    logger.info(f"Sincronização de processos concluída: {total_inseridos} registros persistidos.")
    return total_inseridos


if __name__ == "__main__":
    try:
        from backend.app.core.database import SessionLocal
    except ModuleNotFoundError:
        from app.core.database import SessionLocal
    with SessionLocal() as session:
        inseridos = populate_processos_judiciais(session)
        print(f"Total de processos judiciais persistidos no PostgreSQL: {inseridos}")
