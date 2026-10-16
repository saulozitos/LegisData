"""Pesos do IALP lidos de param.peso (metodologia IALP vigente): a única fonte de verdade da pontuação."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

METODOLOGIA = "IALP"


class PesoNaoConfigurado(LookupError):
    """Tipo, autoria ou status sem peso em param.peso: a configuração está incompleta (não existe valor padrão)."""


def _chave(valor: Any) -> str:
    return valor.value if hasattr(valor, "value") else str(valor)


@dataclass(frozen=True)
class PesosIALP:
    tipo: Dict[str, float]
    autoria: Dict[str, float]
    status: Dict[str, float]
    # exceções por combinação "TIPO:AUTORIA" (ex.: assinatura de apoio a PEC)
    autoria_por_tipo: Optional[Dict[str, float]] = None

    @staticmethod
    def _buscar(tabela: Dict[str, float], dimensao: str, valor: Any) -> float:
        chave = _chave(valor)
        if chave not in tabela:
            raise PesoNaoConfigurado(f"Peso não configurado: {METODOLOGIA}/{dimensao}/{chave}")
        return tabela[chave]

    def peso_tipo(self, valor: Any) -> float:
        return self._buscar(self.tipo, "PESO_TIPO", valor)

    def peso_autoria(self, valor: Any, tipo: Any = None) -> float:
        """Peso do papel do autor; com `tipo`, vale a exceção da combinação (PESO_AUTORIA_POR_TIPO) quando existir."""
        if tipo is not None and self.autoria_por_tipo:
            excecao = self.autoria_por_tipo.get(f"{_chave(tipo)}:{_chave(valor)}")
            if excecao is not None:
                return excecao
        return self._buscar(self.autoria, "PESO_AUTORIA", valor)

    def peso_status(self, valor: Any) -> float:
        return self._buscar(self.status, "PESO_STATUS", valor)


def carregar_pesos_ialp(db: Session) -> PesosIALP:
    """Lê os pesos da versão mais recente da metodologia IALP."""
    linhas = db.execute(
        text(
            """
            SELECT p.dimensao, p.chave, p.valor
            FROM param.peso p JOIN param.metodologia m ON m.id = p.metodologia_id
            WHERE m.codigo = :codigo AND m.versao = (SELECT max(versao) FROM param.metodologia WHERE codigo = :codigo)
            """
        ),
        {"codigo": METODOLOGIA},
    )
    tabelas: Dict[str, Dict[str, float]] = {
        "PESO_TIPO": {},
        "PESO_AUTORIA": {},
        "PESO_STATUS": {},
        "PESO_AUTORIA_POR_TIPO": {},
    }
    for dimensao, chave, valor in linhas:
        if dimensao in tabelas:
            tabelas[dimensao][chave] = float(valor)
    return PesosIALP(
        tipo=tabelas["PESO_TIPO"],
        autoria=tabelas["PESO_AUTORIA"],
        status=tabelas["PESO_STATUS"],
        autoria_por_tipo=tabelas["PESO_AUTORIA_POR_TIPO"],
    )
