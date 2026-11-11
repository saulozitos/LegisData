from typing import Literal, Optional

from pydantic import BaseModel, Field

AlvoTipo = Literal["POLITICO", "VOTACAO", "PROPOSICAO", "PARTIDO", "PAINEL", "CLASSIFICACAO", "OUTRO"]


class RelatoDeErro(BaseModel):
    """O que a pessoa viu de errado e onde: sempre ligado ao parlamentar, à matéria ou ao painel consultado."""

    alvo_tipo: AlvoTipo
    alvo_id: Optional[str] = Field(default=None, max_length=100)
    alvo_rotulo: Optional[str] = Field(default=None, max_length=200)
    secao: Optional[str] = Field(default=None, max_length=100)
    descricao: str = Field(min_length=10, max_length=2000)
    contato: Optional[str] = Field(default=None, max_length=200)
    pagina: Optional[str] = Field(default=None, max_length=500)
    # campo-isca: invisível para quem usa a tela; só robôs o preenchem
    website: Optional[str] = Field(default=None, max_length=200)
