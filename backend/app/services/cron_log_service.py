"""
Mensagens de falha do cron diário.

O detalhe de uma falha (texto da exceção) pode trazer host, usuário do banco, caminho de arquivo, URL e trecho de SQL.
Ele vai para o log do servidor e para a saída de quem roda o cron, nunca para `etl.log_execucao_cron`, que a rota pública
`/parties/cron/logs` e o papel de leitura enxergam. O que se registra é só a etapa e o nome da classe da exceção, e a
rota só repete mensagens nesse formato.
"""

import re
from typing import Optional

ETAPA_VOTACOES = "votações"
ETAPA_PRESENCA = "presença"
ETAPA_ECONOMIA = "economia"
ETAPA_FINANCAS = "finanças"
# Fonte única dos rótulos: o cron os usa para registrar e a rota pública só repete mensagens que citem um deles
ETAPAS_CONHECIDAS = (ETAPA_VOTACOES, ETAPA_PRESENCA, ETAPA_ECONOMIA, ETAPA_FINANCAS)
MENSAGEM_GENERICA = "Falha registrada; o detalhe está no log do servidor."

# `fullmatch`: o `$` do Python também casa antes de uma quebra de linha final
_ITEM = re.compile(r"(?:(?:%s): )?[A-Z][A-Za-z0-9_]*" % "|".join(ETAPAS_CONHECIDAS))


def descrever_falha(etapa: Optional[str], erro: BaseException) -> str:
    """
    O que se registra de uma falha: `etapa: NomeDaClasse` (ou só a classe), sem o texto da exceção. Uma etapa fora de
    `ETAPAS_CONHECIDAS` levanta `ValueError`: a rota pública a trocaria pela mensagem genérica sem aviso.
    """
    if etapa is not None and etapa not in ETAPAS_CONHECIDAS:
        raise ValueError(f"etapa do cron desconhecida: {etapa!r}; inclua-a em ETAPAS_CONHECIDAS")
    classe = type(erro).__name__
    return f"{etapa}: {classe}" if etapa else classe


def mensagem_publica(mensagem: Optional[str]) -> Optional[str]:
    """
    A mensagem para quem consulta a rota pública: só o formato de `descrever_falha` (itens separados por `; `) passa;
    qualquer outro texto, como registros antigos com o texto cru da exceção, vira a mensagem genérica.
    """
    if not mensagem or not mensagem.strip():
        return None
    itens = mensagem.strip().split("; ")
    return mensagem.strip() if all(_ITEM.fullmatch(item) for item in itens) else MENSAGEM_GENERICA
