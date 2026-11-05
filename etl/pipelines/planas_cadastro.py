"""
Tabelas planas do cadastro (`stg.curadoria_*`, `stg.camara_deputado`, `stg.senado_senador`, `stg.tse_filiacao`).

Uma tabela por arquivo de entrada, sem chave estrangeira e sem consulta ao banco: cada linha é o registro do arquivo, com os
valores convertidos linha a linha (datas, biografia, `is_atual`) e a execução que a carregou. Quem decide a que pessoa,
partido ou mandato o registro se refere é a função SQL `etl.preparar_cadastro`, na fusão. Cada carga substitui o conteúdo da
tabela pelo do arquivo atual (o histórico dos arquivos fica em `etl.arquivo_bruto`).

Nenhum CPF é lido nem gravado (decisão D3): o arquivo de presidentes traz o campo, e ele não passa daqui.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from etl.pipelines.dados_partidos import PARTY_FULL_NAMES, PARTY_SPECTRUM_MAP
from etl.pipelines.loader_helpers import LEGISLATURA_ATUAL_INICIO, _to_date, inteiro, legislatura_datas
from etl.pipelines.staging_partidos import montar_partidos
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.copia import copiar_linhas, esvaziar
from etl.utils.datafiles import load_deputados, load_json, load_senadores
from etl.utils.provenance import is_synthetic

ensure_backend_on_path()

from app.models.enums import MotivoDesfiliacaoEnum  # noqa: E402

logger = logging.getLogger("PlanasCadastro")

COLUNAS_PARTIDO = ["sigla", "nome", "espectro", "ideologia", "lema", "numero", "logo_url"]
COLUNAS_PRESIDENTE = [
    "id_referencia",
    "nome_civil",
    "nome_eleitoral",
    "data_nascimento",
    "data_falecimento",
    "genero",
    "naturalidade_municipio",
    "naturalidade_uf",
    "foto_url",
    "partido_sigla",
    "mandato_numero",
    "ano_eleicao",
    "data_inicio",
    "data_fim",
    "status_mandato",
    "biografia",
]
COLUNAS_MINISTRO = ["id_referencia", "nome", "inicio", "fim"]
COLUNAS_DEPUTADO = [
    "camara_id",
    "nome_eleitoral",
    "nome_civil",
    "partido_sigla",
    "uf",
    "foto_url",
    "id_legislatura",
    "sexo",
    "data_nascimento",
    "uf_nascimento",
    "municipio_nascimento",
    "email",
    "gabinete_sala",
    "gabinete_telefone",
    "biografia",
]
COLUNAS_SENADOR = [
    "senado_id",
    "nome_civil",
    "nome_eleitoral",
    "partido_sigla",
    "uf",
    "foto_url",
    "email",
    "gabinete_sala",
    "gabinete_telefone",
    "mandato_inicio",
    "mandato_fim",
    "ano_eleicao",
    "datas_informadas",
    "biografia",
]
COLUNAS_FILIACAO = [
    "politico_nome",
    "camara_id",
    "senado_id",
    "uf",
    "partido_sigla",
    "data_filiacao",
    "data_desfiliacao",
    "motivo_desfiliacao",
    "is_atual",
    "fonte",
    "sintetico",
]

TABELAS = (
    "stg.curadoria_partido",
    "stg.curadoria_presidente",
    "stg.curadoria_ministro_fazenda",
    "stg.camara_deputado",
    "stg.senado_senador",
    "stg.tse_filiacao",
)


def _data(valor: Any) -> Optional[str]:
    convertida = _to_date(valor)
    return convertida.isoformat() if convertida else None


def _texto(valor: Any) -> Optional[str]:
    """Texto como veio; vazio vira nulo (desconhecido é nulo, nunca texto vazio)."""
    if valor is None:
        return None
    texto = str(valor)
    return texto if texto.strip() else None


def _motivo(bruto: Any) -> Optional[str]:
    """O nome do motivo de desfiliação no enum do banco; texto fora do enum cai em MUDANCA_VOLUNTARIA."""
    if bruto is None or isinstance(bruto, float) and bruto != bruto:
        return None
    texto = str(bruto)
    if not texto or texto.lower() == "none":
        return None
    return texto if texto in MotivoDesfiliacaoEnum.__members__ else MotivoDesfiliacaoEnum.MUDANCA_VOLUNTARIA.name


def linhas_partidos(data_dir: Path) -> List[List[Any]]:
    return [[p[c] for c in COLUNAS_PARTIDO] for p in montar_partidos(data_dir)]


def linhas_partidos_conhecidos() -> List[List[Any]]:
    """Nome e espectro curados de toda sigla conhecida: a fusão cria com eles o partido que aparece só numa fonte."""
    return [
        [sigla, PARTY_FULL_NAMES.get(sigla), PARTY_SPECTRUM_MAP.get(sigla)]
        for sigla in sorted(set(PARTY_FULL_NAMES) | set(PARTY_SPECTRUM_MAP))
    ]


def linhas_presidentes(data_dir: Path) -> Tuple[List[List[Any]], List[List[Any]]]:
    """Presidentes e os ministros da Fazenda de cada mandato (dois arquivos planos)."""
    presidentes: List[List[Any]] = []
    ministros: List[List[Any]] = []
    for p in load_json(data_dir / "presidentes_historico.json", []) or []:
        biografia = f"Presidente da República. Eleição: {p.get('ano_eleicao')}. Status: {p.get('status_mandato')}."
        presidentes.append(
            [
                p["id_referencia"],
                p["nome_civil"],
                p["nome_eleitoral"],
                _data(p.get("data_nascimento")),
                _data(p.get("data_falecimento")),
                _texto(p.get("genero")),
                _texto(p.get("naturalidade_municipio")),
                _texto(p.get("naturalidade_uf")),
                _texto(p.get("foto_url")),
                _texto(p.get("partido_sigla")),
                p["mandato_numero"],
                p["ano_eleicao"],
                _data(p["data_inicio"]),
                _data(p.get("data_fim")),
                p.get("status_mandato", "CONCLUIDO"),
                biografia,
            ]
        )
        for m in p.get("ministros_fazenda_chave", []):
            ministros.append([p["id_referencia"], m["nome"], _data(m["inicio"]), _data(m.get("fim"))])
    return presidentes, ministros


def linhas_deputados(data_dir: Path) -> List[List[Any]]:
    linhas: List[List[Any]] = []
    for d in load_deputados(data_dir):  # deduplicado por camara_id
        legislatura = d.get("id_legislatura")
        biografia = f"Deputado Federal pela UF {d.get('uf')} ({d.get('partido_sigla')})."
        if legislatura:
            biografia = f"{biografia[:-1]}. Legislatura {legislatura}."
        linhas.append(
            [
                d["camara_id"],
                _texto(d.get("nome_eleitoral")),
                _texto(d.get("nome_civil")),
                _texto(d.get("partido_sigla")),
                _texto(d.get("uf")),
                _texto(d.get("foto_url")),
                legislatura or None,
                _texto(d.get("sexo")),
                _data(d.get("data_nascimento")),
                _texto(d.get("uf_nascimento")),
                _texto(d.get("municipio_nascimento")),
                _texto(d.get("email")),
                _texto(d.get("gabinete_sala")),
                _texto(d.get("gabinete_telefone")),
                biografia,
            ]
        )
    return linhas


def datas_do_mandato_de_senador(s: Dict[str, Any]) -> Tuple[Any, Any, int, bool]:
    """
    Início, fim, ano da eleição e se as datas vieram da fonte. Fonte sem datas: início da legislatura atual, sem fim, e
    sem afirmar a eleição de 2022 (metade do Senado foi eleita em 2018) — `datas_informadas` fica falso.
    """
    inicio, fim = _to_date(s.get("mandato_inicio")), _to_date(s.get("mandato_fim"))
    if inicio is None and s.get("legislatura_inicio"):
        inicio, _ = legislatura_datas(int(s["legislatura_inicio"]))
    if fim is None and s.get("legislatura_fim"):
        _, fim = legislatura_datas(int(s["legislatura_fim"]))
    if inicio is None:
        return LEGISLATURA_ATUAL_INICIO, None, LEGISLATURA_ATUAL_INICIO.year - 1, False
    return inicio, fim, inicio.year - 1, bool(s.get("mandato_inicio") or s.get("legislatura_inicio"))


def linhas_senadores(data_dir: Path) -> List[List[Any]]:
    linhas: List[List[Any]] = []
    for s in load_senadores(data_dir):  # deduplicado por senado_id
        inicio, fim, ano, informadas = datas_do_mandato_de_senador(s)
        linhas.append(
            [
                s["senado_id"],
                _texto(s.get("nome_civil")),
                _texto(s.get("nome_eleitoral")),
                _texto(s.get("partido_sigla")),
                _texto(s.get("uf")),
                _texto(s.get("foto_url")),
                _texto(s.get("email")),
                _texto(s.get("gabinete_sala")),
                _texto(s.get("gabinete_telefone")),
                inicio.isoformat(),
                fim.isoformat() if fim else None,
                ano,
                "true" if informadas else "false",
                f"Senador Federal pela UF {s.get('uf')} ({s.get('partido_sigla')}).",
            ]
        )
    return linhas


def linhas_filiacoes(data_dir: Path) -> Optional[List[List[Any]]]:
    """As filiações do arquivo, ou `None` quando ele não existe (a carga é pulada, como antes)."""
    itens = load_json(data_dir / "filiacoes_partidarias.json", None)
    if itens is None:
        return None
    linhas: List[List[Any]] = []
    for item in itens:
        desfiliacao = _data(item.get("data_desfiliacao"))
        atual = item.get("is_atual", desfiliacao is None)
        linhas.append(
            [
                _texto(item.get("politico_nome")),
                inteiro(item.get("camara_id")) or None,
                inteiro(item.get("senado_id")) or None,
                _texto(item.get("uf")),
                _texto(item.get("partido_sigla")),
                _data(item.get("data_filiacao")),
                desfiliacao,
                _motivo(item.get("motivo_desfiliacao")),
                "true" if bool(atual) else "false",
                _texto(item.get("fonte")),
                "true" if is_synthetic(item) else "false",
            ]
        )
    return linhas


def _gravar(cursor: Any, tabela: str, colunas: Sequence[str], linhas: Iterable[Sequence[Any]], execucao_id: Any) -> int:
    """Substitui o conteúdo da tabela: `execucao_id` e o número da linha acompanham cada registro."""
    cursor.execute(f"TRUNCATE {tabela}")  # nosec B608 - nome constante deste módulo
    com_controle = (
        [execucao_id, numero, *linha] for numero, linha in enumerate((list(linha) for linha in linhas), start=1)
    )
    return copiar_linhas(cursor, tabela, ["execucao_id", "linha", *colunas], com_controle)


def gravar_planas(cursor: Any, data_dir: Path, execucao_id: Any, recurso: str) -> Dict[str, int]:
    """
    Grava as tabelas planas de um recurso do cadastro: `partidos`, `politicos` (presidentes, deputados, senadores) ou
    `filiacoes`. Devolve `{tabela: linhas}`.
    """
    if recurso == "partidos":
        return {
            "stg.curadoria_partido": _gravar(
                cursor, "stg.curadoria_partido", COLUNAS_PARTIDO, linhas_partidos(data_dir), execucao_id
            ),
            "stg.curadoria_partido_conhecido": _gravar(
                cursor,
                "stg.curadoria_partido_conhecido",
                ["sigla_maiuscula", "nome", "espectro"],
                linhas_partidos_conhecidos(),
                execucao_id,
            ),
        }
    if recurso == "politicos":
        presidentes, ministros = linhas_presidentes(data_dir)
        return {
            "stg.curadoria_presidente": _gravar(
                cursor, "stg.curadoria_presidente", COLUNAS_PRESIDENTE, presidentes, execucao_id
            ),
            "stg.curadoria_ministro_fazenda": _gravar(
                cursor, "stg.curadoria_ministro_fazenda", COLUNAS_MINISTRO, ministros, execucao_id
            ),
            "stg.camara_deputado": _gravar(
                cursor, "stg.camara_deputado", COLUNAS_DEPUTADO, linhas_deputados(data_dir), execucao_id
            ),
            "stg.senado_senador": _gravar(
                cursor, "stg.senado_senador", COLUNAS_SENADOR, linhas_senadores(data_dir), execucao_id
            ),
        }
    if recurso == "filiacoes":
        linhas = linhas_filiacoes(data_dir)
        if linhas is None:
            logger.warning("Arquivo filiacoes_partidarias.json não encontrado. Pulando carga.")
            return {}
        return {"stg.tse_filiacao": _gravar(cursor, "stg.tse_filiacao", COLUNAS_FILIACAO, linhas, execucao_id)}
    raise ValueError(f"recurso sem tabela plana: {recurso}")


__all__ = ["gravar_planas", "esvaziar", "TABELAS"]
