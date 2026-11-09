"""
Identificador de pessoa pelo CPF sem guardar o CPF: HMAC-SHA256 do número (só dígitos) com a chave secreta `CPF_HMAC_KEY`.

O CPF vem das fontes oficiais (detalhe do deputado na API da Câmara e `consulta_cand` do TSE) e só existe na memória do
processo e no cache bruto (`etl/data/raw`, ignorado pelo git). Arquivos processados e banco recebem apenas o HMAC. Um hash
simples não serve: são 10^9 CPFs possíveis, qualquer um os percorre; com a chave ninguém desfaz o valor.
Sem chave configurada (ou com chave curta demais) nada é calculado: as pessoas continuam ligadas por id oficial e por
nome civil + nascimento. A chave não pode mudar sem refazer `cpf_identificadores.json` e `declaracoes_patrimonio.json`, e
um vazamento dela equivale a publicar os CPFs dos HMACs que já estão no histórico do git.
"""

import hashlib
import hmac
import logging
import re
from functools import lru_cache
from typing import Any, Optional

from etl.utils.bootstrap import ensure_backend_on_path

logger = logging.getLogger("CPF")

# `secrets.token_hex(32)` dá 64 caracteres. Os HMACs ficam em arquivo versionado: com uma chave curta, quem tem um CPF
# conhecido (o TSE publica o dos candidatos) acharia a chave por força bruta e, com ela, todos os outros CPFs.
TAMANHO_MINIMO_DA_CHAVE = 32


def so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def cpf_valido(valor: Any) -> Optional[str]:
    """Os 11 dígitos de um CPF válido (dígitos verificadores conferem); máscaras do TSE (`-4`, zeros) e lixo viram None."""
    d = so_digitos(valor)
    if len(d) != 11 or len(set(d)) == 1:
        return None
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if int(d[tamanho]) != (soma * 10 % 11) % 10:
            return None
    return d


@lru_cache(maxsize=1)
def _chave() -> bytes:
    ensure_backend_on_path()
    from app.core.config import settings

    chave = settings.CPF_HMAC_KEY.strip()
    if chave and len(chave) < TAMANHO_MINIMO_DA_CHAVE:
        logger.warning(
            "CPF_HMAC_KEY tem menos de %d caracteres: tratada como não configurada (gere com secrets.token_hex(32)).",
            TAMANHO_MINIMO_DA_CHAVE,
        )
        return b""
    return chave.encode("utf-8")


def chave_configurada() -> bool:
    return bool(_chave())


def identificador_cpf(valor: Any) -> Optional[str]:
    """HMAC-SHA256 (hex) do CPF, ou None se o CPF for inválido ou não houver chave configurada."""
    digitos, chave = cpf_valido(valor), _chave()
    if not digitos or not chave:
        return None
    return hmac.new(chave, digitos.encode("ascii"), hashlib.sha256).hexdigest()
