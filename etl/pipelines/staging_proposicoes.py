"""
Constantes e conversões puras das proposições da Câmara e do Senado (as tabelas planas são de
`etl.pipelines.planas_proposicoes`; a resolução de qual proposição e qual autor cada registro é está em
`etl.preparar_proposicoes`, na fusão).
"""

from typing import Optional

from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from app.models.enums import TipoProposicaoEnum  # noqa: E402

URL_CAMARA = "https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={}"
URL_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"


def tipo_proposicao(tipo_str: Optional[str]) -> str:
    """O nome do tipo no enum do banco; tipo desconhecido vira PL (como no carregador anterior)."""
    nome = (tipo_str or "PL").upper()
    return nome if nome in TipoProposicaoEnum.__members__ else "PL"
