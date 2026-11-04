"""
Registro de cada carga em `etl.execucao` e dos arquivos de origem em `etl.arquivo_bruto`.

A linha de execução é aberta e fechada em transações PRÓPRIAS, fora da transação da carga: se a carga desfaz tudo, a
execução fica registrada como `ERRO`. Só o nome da classe da exceção vai para a coluna `erro` (o texto pode trazer host,
usuário do banco e trecho de SQL e fica no log do servidor).

Os parâmetros de uma execução não podem usar as chaves `carga` nem `fonte`: `semeadura_das_financas` e o `deploy.sh` leem
`etl.execucao` (estágio CARREGAR, status OK) por elas para saber quem é dono dos dados de finanças. Toda carga nova registra
a execução por aqui; quem grava em `etl.execucao` por fora (como `financas_loader`) responde por essa regra sozinho.

Status: `OK` só quando as contagens foram preenchidas, fecham (`lidas == gravadas + rejeitadas`) e nada foi rejeitado; fora
disso `COM_ALERTA` (contagem ausente não é zero). Uma execução que o processo deixou `EXECUTANDO` (morto sem chance de
fechar) é fechada como `ERRO` com `INTERROMPIDA` na próxima abertura da mesma fonte e estágio, depois de `ORFA_APOS`.

Invariantes para quem expurgar histórico: `etl.arquivo_bruto.execucao_id` referencia `etl.execucao` (sem `ON DELETE`), então
apague ou anule o arquivo antes da execução; e as linhas `CARREGAR`/`OK` de finanças não podem ser expurgadas (ver
`semeadura_das_financas`). Este módulo não depende de `app.*`, só de SQLAlchemy.
"""

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.utils.verificacoes import contagem_fecha

logger = logging.getLogger("Execucao")

ESTAGIOS = ("EXTRAIR", "CARREGAR", "MERGE", "DERIVAR", "VALIDAR", "TUDO", "LEGADO")
STATUS_EXECUTANDO = "EXECUTANDO"
STATUS_OK = "OK"
STATUS_COM_ALERTA = "COM_ALERTA"
STATUS_ERRO = "ERRO"
CHAVES_RESERVADAS = ("carga", "fonte")  # lidas por `semeadura_das_financas` e pelo deploy.sh
ORFA_APOS = "6 hours"  # uma carga `EXECUTANDO` há mais que isto, sem processo vivo, é tratada como interrompida
ERRO_INTERROMPIDA = "INTERROMPIDA"


@dataclass
class Execucao:
    """A execução em andamento: o carregador preenche as contagens e o contexto fecha a linha com elas."""

    id: int
    fonte: str
    estagio: str
    lidas: Optional[int] = None
    gravadas: Optional[int] = None
    rejeitadas: Optional[int] = None


def _validar(estagio: str, parametros: Optional[Dict[str, Any]]) -> None:
    if estagio not in ESTAGIOS:
        raise ValueError(f"estágio desconhecido: {estagio!r}; use um de {ESTAGIOS}")
    reservadas = [chave for chave in CHAVES_RESERVADAS if parametros and chave in parametros]
    if reservadas:
        raise ValueError(f"parâmetros de execução não podem usar as chaves {reservadas}: o deploy as lê")


def abrir_execucao(
    engine: Engine,
    fonte: str,
    estagio: str,
    parametros: Optional[Dict[str, Any]] = None,
    orfa_apos: str = ORFA_APOS,
) -> Execucao:
    """
    Grava a linha `EXECUTANDO` (transação própria, já confirmada). `fonte` é o `etl.fonte.codigo`. Antes, fecha como
    interrompida a execução da mesma fonte e estágio que ficou `EXECUTANDO` há mais que `orfa_apos` (um intervalo do
    Postgres): uma carga que dure mais que o padrão deve passar um prazo maior.
    """
    _validar(estagio, parametros)
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "UPDATE etl.execucao SET finalizado_em = now(), status = :erro, erro = :motivo "
                "WHERE status = :executando AND estagio = :estagio AND iniciado_em < now() - CAST(:orfa AS interval) "
                "AND fonte_id = (SELECT id FROM etl.fonte WHERE codigo = :fonte)"
            ),
            {
                "erro": STATUS_ERRO,
                "motivo": ERRO_INTERROMPIDA,
                "executando": STATUS_EXECUTANDO,
                "estagio": estagio,
                "orfa": orfa_apos,
                "fonte": fonte,
            },
        )
        identificador = conexao.execute(
            text(
                "INSERT INTO etl.execucao (fonte_id, estagio, parametros) "
                "SELECT id, :estagio, CAST(:parametros AS jsonb) FROM etl.fonte WHERE codigo = :fonte RETURNING id"
            ),
            {"fonte": fonte, "estagio": estagio, "parametros": json.dumps(parametros) if parametros else None},
        ).scalar()
    if identificador is None:
        raise ValueError(f"fonte desconhecida em etl.fonte: {fonte!r}")
    return Execucao(id=int(identificador), fonte=fonte, estagio=estagio)


def fechar_execucao(engine: Engine, execucao: Execucao, status: str, erro: Optional[str] = None) -> None:
    """Fecha a linha com o status, as contagens da execução e o horário de término (transação própria)."""
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "UPDATE etl.execucao SET finalizado_em = now(), status = :status, linhas_lidas = :lidas, "
                "linhas_gravadas = :gravadas, linhas_rejeitadas = :rejeitadas, erro = :erro WHERE id = :id"
            ),
            {
                "id": execucao.id,
                "status": status,
                "lidas": execucao.lidas,
                "gravadas": execucao.gravadas,
                "rejeitadas": execucao.rejeitadas,
                "erro": erro,
            },
        )


@contextmanager
def registrar_execucao(
    engine: Engine,
    fonte: str,
    estagio: str,
    parametros: Optional[Dict[str, Any]] = None,
    orfa_apos: str = ORFA_APOS,
) -> Iterator[Execucao]:
    """
    Abre a execução, entrega-a ao carregador e a fecha: `OK` ao terminar com as contagens preenchidas e fechando, `COM_ALERTA`
    se houve rejeitadas ou as contagens faltam ou não fecham, `ERRO` com o nome da classe da exceção se ela escapar (a
    exceção continua subindo). Falhar ao fechar nunca derruba a carga: a carga já terminou (ou já falhou) e a falha de
    registro vira aviso; a linha fica `EXECUTANDO` até a próxima abertura da fonte a fechar como interrompida.
    """
    execucao = abrir_execucao(engine, fonte, estagio, parametros, orfa_apos)
    try:
        yield execucao
    except BaseException as exc:
        try:
            fechar_execucao(engine, execucao, STATUS_ERRO, erro=type(exc).__name__)
        except Exception as falha:  # noqa: BLE001 - a exceção da carga é a que importa; esta só vira aviso
            logger.warning("Execução %s não pôde ser fechada como ERRO: %s", execucao.id, falha)
        raise
    fecham = contagem_fecha("contagens", execucao.lidas, execucao.gravadas, execucao.rejeitadas).passou
    status = STATUS_OK if fecham and not execucao.rejeitadas else STATUS_COM_ALERTA
    if not fecham:
        logger.warning(
            "Execução %s: contagens ausentes ou que não fecham (lidas=%s, gravadas=%s, rejeitadas=%s)",
            execucao.id,
            execucao.lidas,
            execucao.gravadas,
            execucao.rejeitadas,
        )
    try:
        fechar_execucao(engine, execucao, status)
    except Exception as falha:  # noqa: BLE001 - a carga já foi confirmada; a próxima abertura da fonte fecha a linha
        logger.warning("Execução %s não pôde ser fechada como %s: %s", execucao.id, status, falha)


def registrar_arquivo_bruto(
    cursor: Any,
    fonte: str,
    url: str,
    sha256: str,
    tamanho: int,
    caminho: str,
    execucao_id: Optional[int] = None,
    http_status: int = 200,
) -> None:
    """
    Registra o arquivo de origem na transação do cursor (DB-API, estilo `%s`) da carga. O mesmo conteúdo (fonte e SHA-256)
    não é registrado duas vezes: a primeira linha, com a execução que o trouxe, permanece.
    """
    cursor.execute(
        "INSERT INTO etl.arquivo_bruto (fonte_id, execucao_id, url, sha256, bytes, http_status, caminho) "
        "SELECT id, %s, %s, %s, %s, %s, %s FROM etl.fonte WHERE codigo = %s "
        "ON CONFLICT (fonte_id, sha256) DO NOTHING",
        (execucao_id, url, sha256, tamanho, http_status, caminho, fonte),
    )
