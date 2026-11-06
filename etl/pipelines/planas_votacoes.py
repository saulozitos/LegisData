"""
Tabelas planas das votações: plenário (`stg.camara_sessao_plenario`, `stg.camara_voto_plenario`, `stg.senado_sessao_plenario`,
`stg.senado_voto_plenario`) e histórico (`stg.historico_*`, dos arquivos anuais `votacoes/{camara,senado}_AAAA.json.gz` e
dos ex-parlamentares de `parlamentares_legislaturas_anteriores.json`).

Uma linha por registro dos arquivos, com os valores que dependem só da própria linha (datas, texto da pauta, classificação
da proposição, a opção do voto e o partido já lido da lista do arquivo). Que político, proposição e mandato cada registro
significa é decisão das funções SQL `etl.preparar_*`, na fusão. Arquivo ilegível, sem proveniência (`fonte`, `is_synthetic`)
ou só com um dos lados (sessões sem votos, ou o contrário) é pulado inteiro e contado em `arquivos_ignorados`: a execução
sai `COM_ALERTA`, porque os votos dele não dá para contar.
"""

import logging
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from etl.extractors.camara_extractor import classificar_setor_por_texto, interpretar_aprovacao
from etl.extractors.senado_extractor import MATERIAS_BUSCA
from etl.extractors.votacoes_extractor import ler_json_gz, listar_arquivos_processados
from etl.pipelines.loader_helpers import _to_datetime, classify_proposition_impact, inteiro
from etl.pipelines.planas_cadastro import _data, _gravar, _texto
from etl.pipelines.staging_proposicoes import URL_CAMARA, URL_SENADO
from etl.pipelines.staging_votos import ContagemDeVotos
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from app.models.enums import StatusTramitacaoEnum, TipoProposicaoEnum, VotoOpcaoEnum  # noqa: E402

logger = logging.getLogger("PlanasVotacoes")

ARQUIVO_HISTORICOS = "parlamentares_legislaturas_anteriores.json"
CAMARA, SENADO = "CAMARA", "SENADO"
# Arquivos legados de votação do Senado não traziam o ano da matéria; as duas matérias coletadas são conhecidas.
MATERIA_ANO_CONHECIDA = {(m["sigla"], m["numero"]): m["ano"] for m in MATERIAS_BUSCA}
TIPOS_SUPORTADOS = {"PL", "PEC", "PLP", "MPV", "PDL", "DECRETO_PRES", "LEI_DELEGADA"}

COLUNAS_SESSAO_CAMARA = [
    "sessao_externa_id",
    "proposicao_camara_id",
    "data_hora",
    "titulo_pauta",
    "descricao",
    "aprovada",
    "total_sim",
    "total_nao",
    "total_abstencao",
    "total_obstrucao",
]
COLUNAS_VOTO_CAMARA = ["sessao_externa_id", "deputado_camara_id", "partido_sigla", "voto"]
COLUNAS_SESSAO_SENADO = [
    "sessao_externa_id",
    "materia_sigla",
    "materia_numero",
    "materia_ano",
    "data_hora",
    "titulo_pauta",
    "descricao",
    "aprovada",
    "total_sim",
    "total_nao",
    "total_abstencao",
    "total_obstrucao",
]
COLUNAS_VOTO_SENADO = ["sessao_externa_id", "senador_id", "partido_sigla", "voto"]
COLUNAS_PARLAMENTAR = [
    "origem",
    "casa",
    "ext_id",
    "nome",
    "nome_civil",
    "partido",
    "uf",
    "foto_url",
    "biografia",
    "legislaturas",
    "mandatos",
]
COLUNAS_SESSAO_HISTORICO = [
    "casa",
    "ext_id",
    "data_hora",
    "titulo_pauta",
    "descricao",
    "aprovada",
    "secreta",
    "orientacao_governo",
    "total_sim",
    "total_nao",
    "total_abstencao",
    "total_obstrucao",
    "prop_valida",
    "prop_camara_id",
    "prop_senado_id",
    "prop_tipo",
    "prop_numero",
    "prop_ano",
    "prop_titulo",
    "prop_ementa",
    "prop_data",
    "prop_url_inteiro_teor",
    "prop_status",
    "prop_autor_nome",
    "prop_autor_camara_id",
    "prop_eixo",
    "prop_eixos",
    "prop_area",
    "prop_url_oficial",
]
COLUNAS_VOTO_HISTORICO = ["casa", "sessao_ext_id", "parlamentar_ext_id", "opcao", "partido"]


def _datahora(valor: Any) -> Optional[str]:
    convertida = _to_datetime(valor)
    return convertida.isoformat() if convertida else None


def _bool(valor: Any) -> str:
    return "true" if bool(valor) else "false"


def _inteiro_ou_zero(valor: Any) -> int:
    return inteiro(valor) or 0


def _opcao(valor: Any) -> Optional[str]:
    """O nome da opção de voto no enum do banco, ou None quando desconhecida."""
    nome = str(valor or "AUSENTE").strip().upper()
    return nome if nome in VotoOpcaoEnum.__members__ else None


def _arquivo_confiavel(dados: Any, caminho: Path) -> bool:
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s sem proveniência oficial (fonte/is_synthetic) — ignorado.", caminho.name)
        return False
    return True


def acumular_votos(cursor: Any, execucao_id: Any, linhas: Iterable[List[Any]]) -> None:
    """
    Acrescenta votos a `stg.historico_voto` (casa, sessão, parlamentar, opção, sigla), sem tocar nos que já estão: o par
    (casa, sessão, parlamentar) é único e vale o primeiro, como o staging relacional fazia. A tabela é CUMULATIVA de propósito:
    `leg.voto` é refeito inteiro a cada fusão, então um arquivo que sumiu (ou uma carga que não trouxe votos) não pode apagar
    os votos que já entraram.
    """
    from etl.utils.copia import copiar_linhas

    cursor.execute(
        "CREATE TEMP TABLE IF NOT EXISTS _voto_novo (linha int, casa text, sessao_ext_id text, parlamentar_ext_id int, "
        "opcao text, partido text) ON COMMIT DROP"
    )
    cursor.execute("TRUNCATE _voto_novo")
    copiar_linhas(
        cursor,
        "_voto_novo",
        ["linha", *COLUNAS_VOTO_HISTORICO],
        ([n, *linha] for n, linha in enumerate(linhas, start=1)),
    )
    cursor.execute(
        "INSERT INTO stg.historico_voto (execucao_id, linha, casa, sessao_ext_id, parlamentar_ext_id, opcao, partido) "
        "SELECT DISTINCT ON (casa, sessao_ext_id, parlamentar_ext_id) %s, linha, casa, sessao_ext_id, parlamentar_ext_id, "
        "opcao, partido FROM _voto_novo ORDER BY casa, sessao_ext_id, parlamentar_ext_id, linha "
        "ON CONFLICT (casa, sessao_ext_id, parlamentar_ext_id) DO NOTHING",
        (execucao_id,),
    )


# ---------------------------------------------------------------------------------------------- plenário
def gravar_planas_plenario(cursor: Any, data_dir: Path, execucao_id: Any) -> ContagemDeVotos:
    """
    Sessões e votos nominais do plenário. Um arquivo de sessões sem o de votos (ou o contrário) não entra. As sessões vão para
    as planas do plenário (a fusão recalcula os totais com os votos do arquivo); os votos válidos também vão, cumulativos, para
    `stg.historico_voto`. Voto sem parlamentar ou com opção desconhecida fica de fora e conta como rejeitado.
    """
    votos_contados = ContagemDeVotos()
    tabelas: Dict[str, Tuple[List[str], List[List[Any]]]] = {}
    acumulados: List[List[Any]] = []
    for casa, sessoes_arq, votos_arq in (
        (CAMARA, "sessoes_votacao_2023.json", "votos_nominais_2023.json"),
        (SENADO, "sessoes_votacao_senado.json", "votos_nominais_senado.json"),
    ):
        sessoes, votos = load_json(data_dir / sessoes_arq, None), load_json(data_dir / votos_arq, None)
        if (sessoes is None) != (votos is None):
            logger.warning("%s e %s precisam existir juntos: o par foi ignorado.", sessoes_arq, votos_arq)
            votos_contados += ContagemDeVotos(arquivos_ignorados=1)
        if sessoes is None or votos is None:
            sessoes, votos = [], []
        # linha sem `sessao_externa_id` não tem a que sessão pertencer (`str(None)` viraria a sessão "None")
        sessoes = [s for s in sessoes if isinstance(s, dict) and s.get("sessao_externa_id") is not None]
        votos_lidos = len(votos)
        votos = [v for v in votos if isinstance(v, dict) and v.get("sessao_externa_id") is not None]
        chave_parlamentar = "deputado_camara_id" if casa == CAMARA else "senador_id"
        validos = [
            [
                casa,
                str(v["sessao_externa_id"]),
                inteiro(v.get(chave_parlamentar)),
                _opcao(v.get("voto")),
                _texto(v.get("partido_sigla")),
            ]
            for v in votos
        ]
        validos = [v for v in validos if v[2] is not None and v[3] is not None]
        acumulados += validos
        votos_contados += ContagemDeVotos(
            lidas=votos_lidos, gravadas=len(validos), rejeitadas=votos_lidos - len(validos)
        )
        if casa == CAMARA:
            tabelas["camara_sessao_plenario"] = (
                COLUNAS_SESSAO_CAMARA,
                [
                    [
                        str(s["sessao_externa_id"]),
                        inteiro(s.get("proposicao_camara_id")),
                        _datahora(s.get("data_hora")),
                        s.get("titulo_pauta") or "Votação em Plenário",
                        _texto(s.get("descricao")),
                        _bool(s.get("aprovada")),
                        _inteiro_ou_zero(s.get("total_sim")),
                        _inteiro_ou_zero(s.get("total_nao")),
                        _inteiro_ou_zero(s.get("total_abstencao")),
                        _inteiro_ou_zero(s.get("total_obstrucao")),
                    ]
                    for s in sessoes
                ],
            )
            tabelas["camara_voto_plenario"] = (
                COLUNAS_VOTO_CAMARA,
                [
                    [
                        str(v["sessao_externa_id"]),
                        inteiro(v.get("deputado_camara_id")),
                        _texto(v.get("partido_sigla")),
                        _texto(v.get("voto")),
                    ]
                    for v in votos
                ],
            )
        else:
            tabelas["senado_sessao_plenario"] = (
                COLUNAS_SESSAO_SENADO,
                [
                    [
                        str(s["sessao_externa_id"]),
                        _texto(s.get("materia_sigla")),
                        inteiro(s.get("materia_numero")),
                        inteiro(s.get("materia_ano"))
                        or inteiro(MATERIA_ANO_CONHECIDA.get((s.get("materia_sigla"), s.get("materia_numero")))),
                        _datahora(s.get("data_hora")),
                        s.get("titulo_pauta") or "Votação no Senado Federal",
                        _texto(s.get("descricao")),
                        _bool(s.get("aprovada")),
                        _inteiro_ou_zero(s.get("total_sim")),
                        _inteiro_ou_zero(s.get("total_nao")),
                        _inteiro_ou_zero(s.get("total_abstencao")),
                        _inteiro_ou_zero(s.get("total_obstrucao")),
                    ]
                    for s in sessoes
                ],
            )
            tabelas["senado_voto_plenario"] = (
                COLUNAS_VOTO_SENADO,
                [
                    [
                        str(v["sessao_externa_id"]),
                        inteiro(v.get("senador_id")),
                        _texto(v.get("partido_sigla")),
                        _texto(v.get("voto")),
                    ]
                    for v in votos
                ],
            )
    for nome, (colunas, linhas) in tabelas.items():
        _gravar(cursor, f"stg.{nome}", colunas, linhas, execucao_id)
    acumular_votos(cursor, execucao_id, acumulados)
    return votos_contados


# ---------------------------------------------------------------------------------------------- ex-parlamentares
def _senadores_votantes(data_dir: Path) -> set:
    votantes: set = set()
    for caminho in listar_arquivos_processados(Path(data_dir), "senado"):
        try:
            dados = ler_json_gz(caminho)
        except (OSError, ValueError, EOFError, zlib.error):
            continue
        if not isinstance(dados, dict):
            continue
        votantes.update(n for n in (inteiro(k) for k in (dados.get("parlamentares") or {})) if n is not None)
    return votantes


def _ufs(uf: Any) -> str:
    return str(uf or "não informada")


def _biografia(casa: str, uf: Any, partido: Any) -> str:
    cargo = "Deputado Federal" if casa == CAMARA else "Senador Federal"
    return f"{cargo} pela UF {_ufs(uf)} ({partido or 'sem partido'})."


def linhas_parlamentares_anteriores(data_dir: Path, contagem: Any) -> Optional[List[List[Any]]]:
    """
    Deputados da 56ª legislatura e senadores (titulares) de legislaturas anteriores. `None` quando o arquivo falta ou não tem
    proveniência. Suplente de senador que nunca votou é rejeitado (`SUPLENTE_SEM_VOTO`); sem id, `SEM_ID`.
    """
    import json

    dados = load_json(Path(data_dir) / ARQUIVO_HISTORICOS, None)
    if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
        logger.warning("%s ausente ou sem proveniência — ex-parlamentares não carregados.", ARQUIVO_HISTORICOS)
        return None
    linhas: List[List[Any]] = []
    for d in dados.get("deputados") or []:
        contagem.ler()
        if not d.get("camara_id"):
            contagem.rejeitar("SEM_ID")
            continue
        contagem.gravar()
        nome = (d.get("nome") or d.get("nome_eleitoral") or "").strip()
        partido = d.get("partido") or d.get("partido_sigla")
        linhas.append(
            [
                "LEGISLATURAS_ANTERIORES",
                CAMARA,
                int(d["camara_id"]),
                nome,
                _texto(d.get("nome_civil")),
                partido,
                _texto(d.get("uf")),
                _texto(d.get("foto_url")),
                _biografia(CAMARA, d.get("uf"), partido),
                json.dumps(d.get("legislaturas") or []),
                None,
            ]
        )
    votantes = _senadores_votantes(data_dir)
    for s in dados.get("senadores") or []:
        contagem.ler()
        sid = s.get("senado_id")
        if not sid:
            contagem.rejeitar("SEM_ID")
            continue
        titular = any("suplente" not in str(m.get("participacao") or "").lower() for m in s.get("mandatos") or [])
        if not titular and sid not in votantes:
            contagem.rejeitar("SUPLENTE_SEM_VOTO")
            continue
        contagem.gravar()
        mandatos = [
            m
            for m in s.get("mandatos") or []
            if "suplente" not in str(m.get("participacao") or "").lower() or sid in votantes
        ]
        nome = (s.get("nome") or s.get("nome_eleitoral") or "").strip()
        partido = s.get("partido_sigla") or s.get("partido")
        linhas.append(
            [
                "LEGISLATURAS_ANTERIORES",
                SENADO,
                int(sid),
                nome,
                _texto(s.get("nome_civil")),
                partido,
                _texto(s.get("uf")),
                _texto(s.get("foto_url")),
                _biografia(SENADO, s.get("uf"), s.get("partido") or s.get("partido_sigla")),
                None,
                json.dumps(mandatos),
            ]
        )
    return linhas


def gravar_planas_parlamentares_anteriores(cursor: Any, data_dir: Path, execucao_id: Any, contagem: Any) -> int:
    """Substitui as linhas de origem `LEGISLATURAS_ANTERIORES` de `stg.historico_parlamentar`."""
    linhas = linhas_parlamentares_anteriores(data_dir, contagem)
    cursor.execute("DELETE FROM stg.historico_parlamentar WHERE origem = 'LEGISLATURAS_ANTERIORES'")
    if linhas is None:
        return 0
    _inserir(cursor, "stg.historico_parlamentar", COLUNAS_PARLAMENTAR, linhas, execucao_id, "LEGISLATURAS_ANTERIORES")
    return len(linhas)


def _inserir(
    cursor: Any, tabela: str, colunas: List[str], linhas: Iterable[List[Any]], execucao_id: Any, origem: str
) -> None:
    """Acrescenta linhas (sem esvaziar a tabela) numerando-as depois das que já existem da mesma origem."""
    from etl.utils.copia import copiar_linhas

    cursor.execute("SELECT coalesce(max(linha), 0) FROM " + tabela)  # nosec B608 - nome constante deste módulo
    inicio = int(cursor.fetchone()[0])
    copiar_linhas(
        cursor,
        tabela,
        ["execucao_id", "linha", *colunas],
        ([execucao_id, inicio + n, *linha] for n, linha in enumerate(linhas, start=1)),
    )


# ---------------------------------------------------------------------------------------------- histórico anual
def _tipo(sigla: str) -> Optional[str]:
    nome = (sigla or "").upper()
    return nome if nome in TIPOS_SUPORTADOS and nome in TipoProposicaoEnum.__members__ else None


def _linha_de_sessao(s: Dict[str, Any], casa: str) -> List[Any]:
    """A linha plana de uma sessão: a proposição já classificada, o resultado e os totais lidos do arquivo."""
    prop = s.get("proposicao") or {}
    tipo = _tipo(str(prop.get("tipo") or ""))
    numero, ano = int(prop.get("numero") or 0), int(prop.get("ano") or 0)
    valida = tipo is not None and bool(numero) and bool(ano)
    chave_ext = prop.get("camara_id") if casa == CAMARA else prop.get("senado_id")
    titulo = ementa = eixo = eixos = area = url = None
    apresentacao = None
    status = "EM_TRAMITACAO"
    if valida:
        titulo = prop.get("titulo") or f"{TipoProposicaoEnum[tipo].value} {numero}/{ano}"
        ementa = (prop.get("ementa") or "").strip()
        apresentacao = _data(prop.get("data_apresentacao"))
        eixo, eixos = classify_proposition_impact(TipoProposicaoEnum[tipo].value, numero, ano, titulo, ementa)
        area = classificar_setor_por_texto(titulo, ementa)
        if prop.get("status") in StatusTramitacaoEnum.__members__:
            status = prop["status"]
        if chave_ext:
            url = (URL_CAMARA if casa == CAMARA else URL_SENADO).format(chave_ext)
        titulo = titulo[:255]
    aprovada = s.get("aprovada")
    if aprovada is None and casa == CAMARA:
        aprovada = interpretar_aprovacao({"descricao": s.get("descricao")})
    totais = s.get("totais") or {}
    titulo_materia = prop.get("titulo") or "matéria"
    return [
        casa,
        str(s["id"]),
        _datahora(s.get("data_hora")),
        f"Votação sobre {titulo_materia}"[:255],
        _texto(s.get("descricao")),
        _bool(aprovada),
        _bool(s.get("secreta")),
        _texto(s.get("orientacao_governo")),
        _inteiro_ou_zero(totais.get("SIM")),
        _inteiro_ou_zero(totais.get("NAO")),
        _inteiro_ou_zero(totais.get("ABSTENCAO")),
        _inteiro_ou_zero(totais.get("OBSTRUCAO")),
        _bool(valida),
        inteiro(prop.get("camara_id")) if casa == CAMARA else None,
        inteiro(prop.get("senado_id")) if casa != CAMARA else None,
        tipo,
        numero or None,
        ano or None,
        titulo,
        (ementa or titulo) if valida else None,
        apresentacao,
        _texto(prop.get("url_inteiro_teor")),
        status,
        _texto(prop.get("autor_nome")),
        inteiro(prop.get("autor_camara_id")),
        eixo,
        eixos,
        area,
        url,
    ]


def gravar_planas_historico(cursor: Any, data_dir: Path, execucao_id: Any) -> ContagemDeVotos:
    """Os arquivos anuais de votações nominais. Devolve a contagem de votos lidos e de arquivos pulados."""
    import json

    cursor.execute("DELETE FROM stg.historico_parlamentar WHERE origem = 'VOTACOES'")
    parlamentares: List[List[Any]] = []
    partidos: List[List[Any]] = []
    sessoes: List[List[Any]] = []
    votos: List[List[Any]] = []
    contagem = ContagemDeVotos()
    vistos_partidos: set = set()
    for casa, prefixo in ((CAMARA, "camara"), (SENADO, "senado")):
        for caminho in listar_arquivos_processados(Path(data_dir), prefixo):
            try:
                dados = ler_json_gz(caminho)
            except (OSError, ValueError, EOFError, zlib.error) as exc:
                logger.error("Falha ao ler %s: %s", caminho.name, exc)
                contagem += ContagemDeVotos(arquivos_ignorados=1)
                continue
            if not _arquivo_confiavel(dados, caminho):
                contagem += ContagemDeVotos(arquivos_ignorados=1)
                continue
            for pid_bruto, info in (dados.get("parlamentares") or {}).items():
                pid = inteiro(pid_bruto)
                if pid is None or not isinstance(info, dict):
                    continue
                nome = (info.get("nome") or info.get("nome_eleitoral") or "").strip()
                partido = (
                    (info.get("partido") or info.get("partido_sigla"))
                    if casa == CAMARA
                    else (info.get("partido_sigla") or info.get("partido"))
                )
                parlamentares.append(
                    [
                        "VOTACOES",
                        casa,
                        pid,
                        nome,
                        _texto(info.get("nome_civil")),
                        partido,
                        _texto(info.get("uf")),
                        _texto(info.get("foto_url")),
                        _biografia(casa, info.get("uf"), info.get("partido") or info.get("partido_sigla")),
                        json.dumps(info.get("legislaturas") or []) if casa == CAMARA else None,
                        json.dumps(info.get("mandatos") or []) if casa != CAMARA else None,
                    ]
                )
            lista_partidos = dados.get("partidos") or []
            for sigla in lista_partidos:
                chave = (sigla or "").strip()
                if chave and chave not in vistos_partidos:
                    vistos_partidos.add(chave)
                    partidos.append([chave])
            for s in dados.get("sessoes") or []:
                if not isinstance(s, dict) or s.get("id") is None:
                    continue  # sem id não há a que sessão ligar os votos (`str(None)` viraria a sessão "None")
                sessoes.append(_linha_de_sessao(s, casa))
                lidos = validos = 0
                for pol_ext, opcao, idx_partido in s.get("votos") or []:
                    lidos += 1
                    parlamentar = inteiro(pol_ext)
                    if _opcao(opcao) is None or parlamentar is None:
                        continue  # opção desconhecida ou parlamentar sem id: fica de fora e conta como rejeitada
                    validos += 1
                    posicao = inteiro(idx_partido)
                    sigla = (
                        lista_partidos[posicao] if posicao is not None and 0 <= posicao < len(lista_partidos) else None
                    )
                    votos.append([casa, str(s["id"]), parlamentar, _opcao(opcao), (sigla or "").strip() or None])
                contagem += ContagemDeVotos(lidas=lidos, gravadas=validos, rejeitadas=lidos - validos)
    _inserir(cursor, "stg.historico_parlamentar", COLUNAS_PARLAMENTAR, parlamentares, execucao_id, "VOTACOES")
    _gravar(cursor, "stg.historico_partido", ["sigla"], partidos, execucao_id)
    _gravar(cursor, "stg.historico_sessao", COLUNAS_SESSAO_HISTORICO, sessoes, execucao_id)
    acumular_votos(cursor, execucao_id, votos)
    return contagem


__all__ = ["gravar_planas_plenario", "gravar_planas_parlamentares_anteriores", "gravar_planas_historico"]
