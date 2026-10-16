"""Links oficiais das proposições, numa única definição para todas as telas."""

from typing import Any, Optional


def url_oficial_proposicao(prop: Any) -> Optional[str]:
    """Link da fonte: o registrado na proposição ou, na falta, a ficha de tramitação da Câmara ou do Senado."""
    if prop.url_oficial:
        return str(prop.url_oficial)
    if prop.id_camara:
        return f"https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao={prop.id_camara}"
    if prop.id_senado:
        return f"https://www25.senado.leg.br/web/atividade/materias/-/materia/{prop.id_senado}"
    return None
