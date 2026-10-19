"""D3: nenhum arquivo processado e versionado pode carregar CPF (nem em texto, nem como chave)."""

import json
import re

import pytest

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import _ascii, cpf_valido

ARQUIVOS = sorted(PROCESSED_DATA_DIR.glob("*.json"))
ONZE_DIGITOS = re.compile(r"(?<![0-9])[0-9]{11}(?![0-9])")
CPF_FORMATADO = re.compile(r"(?<![0-9])[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}(?![0-9])")


def _textos(no):
    """Os textos do JSON: valores string e chaves. Número solto não conta (um valor em reais pode passar nos dígitos)."""
    if isinstance(no, dict):
        for chave, valor in no.items():
            yield str(chave)
            yield from _textos(valor)
    elif isinstance(no, list):
        for item in no:
            yield from _textos(item)
    elif isinstance(no, str):
        yield no


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda p: p.name)
def test_arquivo_processado_nao_tem_cpf_valido(arquivo):
    achados = 0
    for texto in _textos(json.loads(arquivo.read_text(encoding="utf-8"))):
        normal = _ascii(texto)
        achados += sum(cpf_valido(m.group(0)) for m in ONZE_DIGITOS.finditer(normal))
        achados += sum(cpf_valido(re.sub(r"\D", "", m.group(0))) for m in CPF_FORMATADO.finditer(normal))
    assert achados == 0, f"{arquivo.name}: {achados} sequência(s) com dígitos verificadores de CPF"


def test_ha_arquivos_para_varrer():
    assert len(ARQUIVOS) >= 20
