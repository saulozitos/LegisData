"""
Mensagens de falha do cron diário.

O detalhe de uma falha (texto da exceção) pode trazer host, usuário do banco, caminho de arquivo, URL e trecho de SQL.
Ele vai para o log do servidor e para a saída de quem roda o cron, nunca para `etl.log_execucao_cron`, que a rota pública
`/parties/cron/logs` e o papel de leitura enxergam. O que se registra é só a etapa e o nome da classe da exceção, e a
rota só repete mensagens nesse formato.
"""

import re
from typing import Optional

ETAPAS_CONHECIDAS = ("votações", "presença", "economia", "finanças")
MENSAGEM_GENERICA = "Falha registrada; o detalhe está no log do servidor."

_ITEM = re.compile(r"^(?:(?:%s): )?[A-Z][A-Za-z0-9_]*$" % "|".join(ETAPAS_CONHECIDAS))


def descrever_falha(etapa: Optional[str], erro: BaseException) -> str:
    """O que se registra de uma falha: `etapa: NomeDaClasse` (ou só a classe), sem o texto da exceção."""
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
    return mensagem.strip() if all(_ITEM.match(item) for item in itens) else MENSAGEM_GENERICA
