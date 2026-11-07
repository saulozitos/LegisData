"""
Votações de plenário: os arquivos de 2023 (`sessoes_votacao_*`, `votos_nominais_*`) e os anuais
(`votacoes/{camara,senado}_AAAA.json.gz`). A sessão se liga à proposição e o voto ao parlamentar pelos ids oficiais; o que não
se liga é rejeitado com motivo. Resultado desconhecido não vira "rejeitada": a sessão sem resultado é rejeitada.
"""

import logging
import zlib
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from etl.carga.base import Resultado, contagem_de, criar_rejeitos, executar_sql, ler_rejeitos, tabela_temporaria
from etl.carga.pessoas import Lote, _data, _texto, parlamentar_da_camara, parlamentar_do_senado
from etl.extractors.camara_extractor import interpretar_aprovacao
from etl.extractors.votacoes_extractor import ler_json_gz, listar_arquivos_processados
from etl.pipelines.loader_helpers import _to_datetime, classify_proposition_impact, inteiro
from etl.utils.datafiles import load_json

logger = logging.getLogger("CargaVotacoes")

CAMARA, SENADO = "CAMARA", "SENADO"
URL_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"
URL_SENADO = "http://legis.senado.leg.br/dadosabertos/materia/{}"
COLUNAS_SESSAO = {
    "linha": "int",
    "casa": "text",
    "id_externo": "text",
    "prop_camara_id": "int",
    "prop_senado_id": "int",
    "prop_tipo": "text",
    "prop_numero": "int",
    "prop_ano": "int",
    "prop_titulo": "text",
    "prop_ementa": "text",
    "prop_data_apresentacao": "date",
    "prop_url": "text",
    "prop_url_texto": "text",
    "prop_status": "text",
    "prop_eixo": "text",
    "prop_eixos": "text",
    "data_hora": "text",
    "titulo_pauta": "text",
    "descricao": "text",
    "aprovada": "boolean",
    "secreta": "boolean",
    "orientacao_governo": "text",
    "t_sim": "int",
    "t_nao": "int",
    "t_abs": "int",
    "t_obs": "int",
}
COLUNAS_VOTO = {
    "linha": "int",
    "casa": "text",
    "id_externo": "text",
    "parlamentar_ext_id": "int",
    "opcao": "text",
    "partido": "text",
}
COLUNAS_ORIENTACAO = {"casa": "text", "id_externo": "text", "bancada": "text", "orientacao": "text"}


def _opcao(valor: Any) -> Optional[str]:
    """A opção como a fonte a publica (maiúscula); vazio é desconhecido (nulo), não 'ausente'."""
    texto = _texto(valor)
    return texto.upper() if texto else None


def _datahora(valor: Any) -> Optional[str]:
    convertida = _to_datetime(valor)
    return convertida.replace(tzinfo=None).isoformat() if convertida else None


def _totais(totais: Any, chave: str) -> Optional[int]:
    return inteiro(totais.get(chave)) if isinstance(totais, dict) and totais.get(chave) is not None else None


def _ano_do_arquivo(caminho: Path) -> Optional[int]:
    """`camara_2023.json.gz` -> 2023."""
    resto = caminho.name.split("_", 1)[-1].split(".", 1)[0]
    return int(resto) if resto.isdigit() else None


def _arquivos_anuais(data_dir: Path, ano_inicio: Optional[int] = None) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Os arquivos anuais da Câmara e do Senado; `ano_inicio` pula os anos anteriores (a carga incremental)."""
    for casa, prefixo in ((CAMARA, "camara"), (SENADO, "senado")):
        for caminho in listar_arquivos_processados(Path(data_dir), prefixo):
            ano = _ano_do_arquivo(caminho)
            if ano_inicio is not None and ano is not None and ano < ano_inicio:
                continue
            try:
                dados = ler_json_gz(caminho)
            except (OSError, ValueError, EOFError, zlib.error) as exc:
                logger.error("Falha ao ler %s: %s", caminho.name, exc)
                continue
            if not isinstance(dados, dict) or not dados.get("fonte") or dados.get("is_synthetic"):
                logger.warning("%s sem proveniência oficial (fonte/is_synthetic): ignorado.", caminho.name)
                continue
            yield casa, dados


# ---------------------------------------------------------------------------------------------------- pessoas
def ler_parlamentares_dos_arquivos(lote: Lote, data_dir: Path, ano_inicio: Optional[int] = None) -> Set[int]:
    """Quem votou nos arquivos anuais entra como pessoa (id oficial) com os mandatos que o arquivo informa. Devolve os senadores."""
    senadores: Set[int] = set()
    for casa, dados in _arquivos_anuais(data_dir, ano_inicio):
        if casa == SENADO:
            senadores.update(n for n in (inteiro(k) for k in (dados.get("parlamentares") or {})) if n is not None)
    for casa, dados in _arquivos_anuais(data_dir, ano_inicio):
        for pid, info in (dados.get("parlamentares") or {}).items():
            if inteiro(pid) is None or not isinstance(info, dict):
                continue
            if casa == CAMARA:
                parlamentar_da_camara(lote, pid, info, info.get("legislaturas") or [], "CAMARA_API", 0)
            else:
                parlamentar_do_senado(lote, pid, info, info.get("mandatos") or [], "SENADO_API", 0, senadores)
        for sigla in dados.get("partidos") or []:
            if isinstance(sigla, str) and sigla.strip():
                lote.siglas.add(sigla.strip())
    return senadores


# ---------------------------------------------------------------------------------------------------- sessões
class Coleta:
    def __init__(self) -> None:
        self.sessoes: List[Tuple[Any, ...]] = []
        self.votos: List[Tuple[Any, ...]] = []
        self.orientacoes: List[Tuple[Any, ...]] = []
        self.votos_lidos = 0

    def sessao(self, **c: Any) -> None:
        self.sessoes.append((len(self.sessoes) + 1, *[c.get(coluna) for coluna in list(COLUNAS_SESSAO)[1:]]))

    def voto(self, casa: str, id_externo: str, parlamentar: Any, opcao: Any, partido: Any) -> None:
        self.votos_lidos += 1
        self.votos.append((self.votos_lidos, casa, id_externo, inteiro(parlamentar), _opcao(opcao), _texto(partido)))


def _eixos(
    tipo: str, numero: Optional[int], ano: Optional[int], titulo: Optional[str], ementa: Optional[str]
) -> Tuple[Any, Any]:
    if not tipo or not numero or not ano:
        return None, None
    return classify_proposition_impact(tipo, numero, ano, titulo or "", ementa or "")


def ler_plenario(coleta: Coleta, data_dir: Path) -> None:
    """Os arquivos de 2023 da Câmara e do Senado (sessões + votos nominais; o par precisa existir junto)."""
    data_dir = Path(data_dir)
    for casa, arq_sessoes, arq_votos, chave_parlamentar in (
        (CAMARA, "sessoes_votacao_2023.json", "votos_nominais_2023.json", "deputado_camara_id"),
        (SENADO, "sessoes_votacao_senado.json", "votos_nominais_senado.json", "senador_id"),
    ):
        sessoes, votos = load_json(data_dir / arq_sessoes, None), load_json(data_dir / arq_votos, None)
        if (sessoes is None) != (votos is None):
            logger.warning("%s e %s precisam existir juntos: o par foi ignorado.", arq_sessoes, arq_votos)
            continue
        for s in sessoes or []:
            if not isinstance(s, dict) or s.get("sessao_externa_id") is None:
                continue
            if casa == CAMARA:
                tipo = (_texto(s.get("proposicao_tipo")) or "").upper()
                numero, ano = inteiro(s.get("proposicao_numero")), inteiro(s.get("proposicao_ano"))
                aprovada = s.get("aprovada")
                if aprovada is None:
                    aprovada = interpretar_aprovacao({"descricao": s.get("descricao")})
                coleta.sessao(
                    casa=casa, id_externo=str(s["sessao_externa_id"]), prop_camara_id=inteiro(s.get("proposicao_camara_id")),
                    prop_tipo=tipo, prop_numero=numero, prop_ano=ano, prop_titulo=_texto(s.get("proposicao_titulo")),
                    data_hora=_datahora(s.get("data_hora")), titulo_pauta=_texto(s.get("titulo_pauta")) or "Votação em Plenário",
                    descricao=_texto(s.get("descricao")), aprovada=aprovada,
                    t_sim=_totais(s, "total_sim"), t_nao=_totais(s, "total_nao"), t_abs=_totais(s, "total_abstencao"),
                    t_obs=_totais(s, "total_obstrucao"),
                )  # fmt: skip
            else:
                tipo = (_texto(s.get("materia_sigla")) or "").upper()
                coleta.sessao(
                    casa=casa, id_externo=str(s["sessao_externa_id"]), prop_tipo=tipo,
                    prop_numero=inteiro(s.get("materia_numero")), prop_ano=inteiro(s.get("materia_ano")),
                    prop_titulo=_texto(s.get("materia_titulo")), data_hora=_datahora(s.get("data_hora")),
                    titulo_pauta=_texto(s.get("titulo_pauta")) or "Votação no Senado Federal",
                    descricao=_texto(s.get("descricao")), aprovada=s.get("aprovada"),
                    t_sim=_totais(s, "total_sim"), t_nao=_totais(s, "total_nao"), t_abs=_totais(s, "total_abstencao"),
                    t_obs=_totais(s, "total_obstrucao"),
                )  # fmt: skip
        for v in votos or []:
            if isinstance(v, dict) and v.get("sessao_externa_id") is not None:
                coleta.voto(
                    casa, str(v["sessao_externa_id"]), v.get(chave_parlamentar), v.get("voto"), v.get("partido_sigla")
                )


def ler_anuais(coleta: Coleta, data_dir: Path, ano_inicio: Optional[int] = None) -> None:
    """Os arquivos anuais: sessões com a proposição embutida, votos `[parlamentar, opção, índice do partido]` e orientações."""
    for casa, dados in _arquivos_anuais(data_dir, ano_inicio):
        lista_partidos = dados.get("partidos") or []
        for s in dados.get("sessoes") or []:
            if not isinstance(s, dict) or s.get("id") is None:
                continue
            prop = s.get("proposicao") or {}
            tipo = (_texto(prop.get("tipo")) or "").upper()
            numero, ano = inteiro(prop.get("numero")), inteiro(prop.get("ano"))
            titulo, ementa = _texto(prop.get("titulo")), _texto(prop.get("ementa"))
            camara_id = inteiro(prop.get("camara_id")) if casa == CAMARA else None
            senado_id = inteiro(prop.get("senado_id")) if casa == SENADO else None
            externo = camara_id or senado_id
            eixo, eixos = _eixos(tipo, numero, ano, titulo, ementa)
            totais = s.get("totais")
            id_externo = str(s["id"])
            coleta.sessao(
                casa=casa, id_externo=id_externo, prop_camara_id=camara_id, prop_senado_id=senado_id, prop_tipo=tipo,
                prop_numero=numero, prop_ano=ano, prop_titulo=titulo, prop_ementa=ementa,
                prop_data_apresentacao=_data(prop.get("data_apresentacao")),
                prop_url=_texto(prop.get("url_oficial")) or ((URL_CAMARA if casa == CAMARA else URL_SENADO).format(externo) if externo else None),
                prop_url_texto=_texto(prop.get("url_inteiro_teor")),
                prop_status=_texto(prop.get("status")), prop_eixo=eixo, prop_eixos=eixos,
                data_hora=_datahora(s.get("data_hora")),
                titulo_pauta=f"Votação sobre {titulo or 'matéria'}"[:255], descricao=_texto(s.get("descricao")),
                aprovada=s.get("aprovada") if s.get("aprovada") is not None else (
                    interpretar_aprovacao({"descricao": s.get("descricao")}) if casa == CAMARA else None),
                secreta=bool(s.get("secreta", False)), orientacao_governo=_texto(s.get("orientacao_governo")),
                t_sim=_totais(totais, "SIM"), t_nao=_totais(totais, "NAO"), t_abs=_totais(totais, "ABSTENCAO"),
                t_obs=_totais(totais, "OBSTRUCAO"),
            )  # fmt: skip
            for bancada, orientacao in (s.get("orientacoes") or {}).items():
                coleta.orientacoes.append((casa, id_externo, str(bancada).strip(), _opcao(orientacao)))
            for voto in s.get("votos") or []:
                try:
                    parlamentar, opcao, posicao = voto
                except (TypeError, ValueError):
                    coleta.voto(casa, id_externo, None, None, None)
                    continue
                indice = inteiro(posicao)
                sigla = lista_partidos[indice] if indice is not None and 0 <= indice < len(lista_partidos) else None
                coleta.voto(casa, id_externo, parlamentar, opcao, sigla)


def carregar_votacoes(cursor: Any, data_dir: Path, ano_inicio: Optional[int] = None) -> Resultado:
    coleta = Coleta()
    ler_plenario(coleta, data_dir)
    ler_anuais(coleta, data_dir, ano_inicio)
    criar_rejeitos(cursor)
    tabela_temporaria(cursor, "_in_sessao", COLUNAS_SESSAO, coleta.sessoes)
    tabela_temporaria(cursor, "_in_voto", COLUNAS_VOTO, coleta.votos)
    tabela_temporaria(cursor, "_in_orientacao", COLUNAS_ORIENTACAO, coleta.orientacoes)
    executar_sql(cursor, "votacoes")
    rejeitos = ler_rejeitos(cursor)
    ate = None
    if coleta.sessoes:
        cursor.execute("SELECT max((data_hora::timestamp)::date) FROM _in_sessao WHERE data_hora IS NOT NULL")
        ate = cursor.fetchone()[0]
    lidas = len(coleta.sessoes) + coleta.votos_lidos
    return Resultado(
        contagem_de(lidas, rejeitos), ate=ate, extras={"sessoes": len(coleta.sessoes), "votos": coleta.votos_lidos}
    )
