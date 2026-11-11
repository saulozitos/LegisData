"""
Relatos de informação incorreta.

O relato vai para `etl.relato_erro` com o alvo (parlamentar, votação, proposição, painel) para a correção chegar com contexto.
Nenhum CPF é gravado (decisão D3): texto com CPF válido, formatado ou não, é recusado e a pessoa é orientada a tirá-lo.
"""

import re
from typing import Any, Dict

from app.core.errors import ErroDeDominio
from app.schemas.feedback import RelatoDeErro
from sqlalchemy import text
from sqlalchemy.orm import Session

_SEQUENCIA_DE_11 = re.compile(r"(?<!\d)(?:\d[\s.\-]?){10}\d(?!\d)")


def _cpf_valido(digitos: str) -> bool:
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * p for d, p in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        if int(digitos[tamanho]) != (soma * 10 % 11) % 10:
            return False
    return True


def contem_cpf(texto: str) -> bool:
    """True se o texto traz uma sequência de 11 dígitos (com ou sem pontuação) que fecha o dígito verificador de CPF."""
    return any(_cpf_valido(re.sub(r"\D", "", m.group(0))) for m in _SEQUENCIA_DE_11.finditer(texto))


def registrar(db: Session, relato: RelatoDeErro) -> Dict[str, Any]:
    if relato.website:  # robô: responde como se tivesse aceitado, sem gravar
        return {"id": None, "mensagem": "Recebemos o seu relato. Obrigado por ajudar a corrigir a base."}
    campos = [relato.descricao, relato.contato, relato.alvo_rotulo, relato.alvo_id, relato.secao]
    if any(contem_cpf(c) for c in campos if c):
        raise ErroDeDominio(
            422, "O texto parece conter um CPF. Remova o número e descreva o problema sem dados pessoais de terceiros."
        )
    novo_id = db.execute(
        text(
            """
            INSERT INTO etl.relato_erro (alvo_tipo, alvo_id, alvo_rotulo, secao, descricao, contato, pagina)
            VALUES (:alvo_tipo, :alvo_id, :alvo_rotulo, :secao, :descricao, :contato, :pagina)
            RETURNING id
            """
        ),
        {
            "alvo_tipo": relato.alvo_tipo,
            "alvo_id": relato.alvo_id,
            "alvo_rotulo": relato.alvo_rotulo,
            "secao": relato.secao,
            "descricao": relato.descricao.strip(),
            "contato": (relato.contato or "").strip() or None,
            "pagina": relato.pagina,
        },
    ).scalar_one()
    db.commit()
    return {"id": novo_id, "mensagem": "Recebemos o seu relato. Obrigado por ajudar a corrigir a base."}
