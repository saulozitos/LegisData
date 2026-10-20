"""CPFs sintéticos dos testes: calculados na hora, nunca escritos por extenso (D3: sem CPF no repositório, nem em teste)."""


def cpf_com_digitos(base: str) -> str:
    """Os 11 dígitos de um CPF a partir dos 9 primeiros (calcula os dois verificadores)."""
    digitos = [int(c) for c in base]
    for tamanho in (9, 10):
        soma = sum(d * peso for d, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        digitos.append((soma * 10 % 11) % 10)
    return "".join(map(str, digitos))


CPF_A = cpf_com_digitos("100000001")
CPF_B = cpf_com_digitos("123456789")
CPF_A_INVALIDO = CPF_A[:-1] + str((int(CPF_A[-1]) + 1) % 10)


def formatado(cpf: str) -> str:
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


# CNPJ real de raiz zerada que passa nos dígitos verificadores de CPF por acaso (deve ser tratado como CNPJ)
CNPJ_DE_RAIZ_ZERADA = "00000000000191"
