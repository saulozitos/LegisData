"""
Registro de cada carga em `etl.execucao` e dos arquivos de origem em `etl.arquivo_bruto`.

A linha de execução é aberta e fechada em transações PRÓPRIAS, fora da transação da carga: se a carga desfaz tudo, a
execução fica registrada como `ERRO`. Só o nome da classe da exceção vai para a coluna `erro` (o texto pode trazer host,
usuário do banco e trecho de SQL e fica no log do servidor).

Os parâmetros de uma execução não podem usar as chaves `carga` nem `fonte`: `semeadura_das_financas` e o `deploy.sh` leem
`etl.execucao` (estágio CARREGAR, status OK) por elas para saber quem é dono dos dados de finanças. Toda carga nova registra
a execução por aqui; quem grava em `etl.execucao` por fora (como `financas_loader`) responde por essa regra sozinho.

Status: `OK` só quando as contagens foram preenchidas, fecham (`lidas == gravadas + rejeitadas`), nada foi rejeitado, o
carregador não marcou `com_alerta` e todas as verificações passaram; fora disso `COM_ALERTA` (contagem ausente não é
zero). As verificações medidas (`Execucao.verificar`) e a de contagens vão para `etl.verificacao` ao fechar a linha. Uma
execução que o processo deixou `EXECUTANDO` (morto sem chance de fechar) é fechada como `ERRO` com `INTERROMPIDA` na próxima
abertura da mesma fonte e estágio, depois de `ORFA_APOS`.

Invariantes para quem expurgar histórico: `etl.arquivo_bruto`, `etl.verificacao` e `etl.rejeito` referenciam `etl.execucao`
(sem `ON DELETE`), então apague ou anule essas linhas antes da execução; e as linhas `CARREGAR`/`OK` de finanças não podem ser expurgadas (ver
`semeadura_das_financas`). Este módulo não depende de `app.*`, só de SQLAlchemy.
"""

import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from etl.utils.verificacoes import Verificacao, contagem_fecha

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
class Contagem:
    """
    Linhas de uma etapa: `lidas` = o que a fonte trouxe, `gravadas` = o que entrou (inclusive o que já estava, quando a
    carga é idempotente), `rejeitadas` = o que ficou de fora, com o motivo em `motivos` (`{motivo: quantas}`). Cada
    rejeitada deve ter motivo; `lidas == gravadas + rejeitadas` é a conferência.
    """

    lidas: int = 0
    gravadas: int = 0
    rejeitadas: int = 0
    motivos: Dict[str, int] = field(default_factory=dict)

    def ler(self, quantas: int = 1) -> None:
        self.lidas += quantas

    def gravar(self, quantas: int = 1) -> None:
        self.gravadas += quantas

    def rejeitar(self, motivo: str, quantas: int = 1) -> None:
        self.rejeitadas += quantas
        self.motivos[motivo] = self.motivos.get(motivo, 0) + quantas

    def __add__(self, outra: "Contagem") -> "Contagem":
        motivos = dict(self.motivos)
        for motivo, quantas in outra.motivos.items():
            motivos[motivo] = motivos.get(motivo, 0) + quantas
        return Contagem(
            self.lidas + outra.lidas, self.gravadas + outra.gravadas, self.rejeitadas + outra.rejeitadas, motivos
        )


@dataclass
class Execucao:
    """A execução em andamento: o carregador preenche as contagens e o contexto fecha a linha com elas."""

    id: int
    fonte: str
    estagio: str
    lidas: Optional[int] = None
    gravadas: Optional[int] = None
    rejeitadas: Optional[int] = None
    recurso: Optional[str] = None  # o recurso da fonte que a execução carrega (`parametros['recurso']`), se houver
    motivos: Dict[str, int] = field(default_factory=dict)  # rejeitadas por motivo; vão agregadas para `etl.rejeito`
    # O carregador sabe de um problema que as contagens não mostram (ex.: arquivo pulado inteiro)
    com_alerta: bool = False
    # Verificações medidas pelo carregador (catálogo de `etl.utils.verificacoes`); gravadas em `etl.verificacao` ao fechar.
    # Uma que não passou deixa a execução em `COM_ALERTA`.
    verificacoes: List[Verificacao] = field(default_factory=list)

    def aplicar(self, contagem: Contagem) -> None:
        """Copia a contagem da etapa para a execução (lidas, gravadas, rejeitadas e os motivos)."""
        self.lidas, self.gravadas, self.rejeitadas = contagem.lidas, contagem.gravadas, contagem.rejeitadas
        self.motivos = dict(contagem.motivos)

    def verificar(self, verificacao: Verificacao) -> Verificacao:
        """Registra o resultado de uma verificação; devolve-o para o carregador poder agir sobre ele."""
        self.verificacoes.append(verificacao)
        return verificacao


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
    return Execucao(id=int(identificador), fonte=fonte, estagio=estagio, recurso=(parametros or {}).get("recurso"))


def fechar_execucao(engine: Engine, execucao: Execucao, status: str, erro: Optional[str] = None) -> None:
    """
    Fecha a linha com o status, as contagens da execução e o horário de término, e grava as verificações medidas (transação
    própria). A verificação `contagens` (as contagens fecham?) entra sempre, medida aqui: é ela que explica um `COM_ALERTA`.
    """
    verificacoes = list(execucao.verificacoes)
    verificacoes.append(contagem_fecha("contagens", execucao.lidas, execucao.gravadas, execucao.rejeitadas))
    with engine.begin() as conexao:
        for verificacao in verificacoes:
            conexao.execute(
                text(
                    "INSERT INTO etl.verificacao (execucao_id, nome, passou, detalhe) "
                    "VALUES (:id, :nome, :passou, CAST(:detalhe AS jsonb))"
                ),
                {
                    "id": execucao.id,
                    "nome": verificacao.nome,
                    "passou": verificacao.passou,
                    "detalhe": json.dumps(verificacao.detalhe, default=str),
                },
            )
        for motivo, quantas in sorted(execucao.motivos.items()):
            # Um registro por motivo, com o total (a carga não guarda cada linha rejeitada: seriam milhares iguais)
            conexao.execute(
                text(
                    "INSERT INTO etl.rejeito (execucao_id, recurso, motivo, payload) "
                    "VALUES (:id, :recurso, :motivo, CAST(:payload AS jsonb))"
                ),
                {
                    "id": execucao.id,
                    "recurso": execucao.recurso or execucao.estagio.lower(),
                    "motivo": motivo,
                    "payload": json.dumps({"total": quantas}),
                },
            )
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
    reprovadas = [v.nome for v in execucao.verificacoes if not v.passou]
    status = (
        STATUS_OK
        if fecham and not execucao.rejeitadas and not execucao.com_alerta and not reprovadas
        else STATUS_COM_ALERTA
    )
    if reprovadas:
        logger.warning("Execução %s: verificações que não passaram: %s", execucao.id, ", ".join(reprovadas))
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
