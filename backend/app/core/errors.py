"""Erro de regra de negócio levantado pelos serviços e convertido em resposta HTTP pela API."""


class ErroDeDominio(Exception):
    """Falha esperada de uma consulta (parâmetro inválido, registro inexistente), com o código HTTP que a descreve."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
