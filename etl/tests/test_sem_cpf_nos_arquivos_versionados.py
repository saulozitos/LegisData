"""D3: nenhum arquivo versionado pode carregar CPF (nem em texto, nem como chave, nem como número solto de campo de documento)."""

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from etl.pipelines.loader_helpers import cpfs_validos_em
from etl.tests.sinteticos import CPF_A, formatado

RAIZ = Path(__file__).resolve().parents[2]
EXTENSOES = {
    ".json",
    ".csv",
    ".md",
    ".py",
    ".sh",
    ".sql",
    ".yml",
    ".yaml",
    ".txt",
    ".toml",
    ".ini",
    ".service",
    ".timer",
}
# Sequências de versão e hashes de lockfiles somam dígitos que passam no verificador por acaso: o frontend fica de fora.
FORA = ("frontend/", "output/")
CHAVES_DE_DOCUMENTO = ("cpf", "documento", "cpf_cnpj", "cpf_cnpj_doador", "cnpj_cpf")


def _versionados():
    if shutil.which("git") is None:
        return []
    saida = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=True).stdout.decode("utf-8")
    return sorted(
        RAIZ / nome
        for nome in saida.split("\0")
        if nome and not nome.startswith(FORA) and (Path(nome).suffix in EXTENSOES or nome.endswith(".json.gz"))
    )


ARQUIVOS = _versionados()


def _textos(no):
    """Textos de um JSON: valores string e chaves; e inteiros de 10 ou 11 dígitos em campo cujo nome sugere documento."""
    if isinstance(no, dict):
        for chave, valor in no.items():
            yield str(chave)
            if isinstance(valor, int) and not isinstance(valor, bool) and str(chave).lower() in CHAVES_DE_DOCUMENTO:
                yield str(valor).zfill(11)
            yield from _textos(valor)
    elif isinstance(no, list):
        for item in no:
            yield from _textos(item)
    elif isinstance(no, str):
        yield no


def _achados(arquivo: Path) -> int:
    if arquivo.name.endswith(".json.gz"):
        conteudo = gzip.open(arquivo, "rt", encoding="utf-8").read()
    else:
        conteudo = arquivo.read_text(encoding="utf-8", errors="replace")
    if arquivo.suffix == ".json" or arquivo.name.endswith(".json.gz"):
        return sum(cpfs_validos_em(texto) for texto in _textos(json.loads(conteudo)))
    return sum(cpfs_validos_em(linha) for linha in conteudo.splitlines())


@pytest.mark.skipif(not ARQUIVOS, reason="git indisponível")
@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda p: p.relative_to(RAIZ).as_posix())
def test_arquivo_versionado_nao_tem_cpf_valido(arquivo):
    assert _achados(arquivo) == 0, f"{arquivo.relative_to(RAIZ)}: sequência com dígitos verificadores de CPF"


@pytest.mark.skipif(not ARQUIVOS, reason="git indisponível")
def test_a_varredura_cobre_os_arquivos_processados_e_os_testes():
    nomes = {p.relative_to(RAIZ).as_posix() for p in ARQUIVOS}
    assert "etl/data/processed/despesas_ceap_2019_2026.json" in nomes
    assert "etl/data/processed/tse_doacoes_campanha.json" in nomes
    assert any(n.endswith(".json.gz") for n in nomes) and "docs/DEPLOY_AUTOMATICO.md" in nomes
    assert "etl/tests/test_sem_cpf_nos_arquivos_versionados.py" in nomes


# ── Controle positivo: a guarda enxerga o que deve enxergar (senão passaria sempre) ───────────────────────────────────
@pytest.mark.parametrize(
    "texto",
    [
        f"FULANO {CPF_A}",
        f"FULANO {formatado(CPF_A)}",
        f"FULANO 000{CPF_A}",
        f"FULANO {CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]}",
        " ".join(CPF_A),  # um dígito por espaço
        f"FULANO {CPF_A[:3]}      {CPF_A[3:]}",  # separador longo
        f"FULANO 0000000{CPF_A}",  # zeros de enchimento em qualquer quantidade
    ],
)
def test_a_varredura_acha_cpf_sintetico_em_todas_as_formas(texto):
    assert cpfs_validos_em(texto) == 1


def test_a_varredura_acha_cpf_em_chave_em_valor_e_em_inteiro_de_campo_de_documento(tmp_path):
    arquivo = tmp_path / "x.json"
    for conteudo in ({CPF_A: 1}, {"nome": f"F {CPF_A}"}, {"cpf": int(CPF_A)}, [{"documento": int(CPF_A)}]):
        arquivo.write_text(json.dumps(conteudo), encoding="utf-8")
        assert _achados(arquivo) == 1, conteudo
    arquivo.write_text(json.dumps({"valor_pago_brl": int(CPF_A)}), encoding="utf-8")
    assert _achados(arquivo) == 0  # um valor em reais que coincide com os dígitos não é CPF


def test_a_varredura_le_json_gz_e_texto_comum(tmp_path):
    gz = tmp_path / "x.json.gz"
    gz.write_bytes(gzip.compress(json.dumps({"a": f"F {CPF_A}"}).encode()))
    texto = tmp_path / "x.md"
    texto.write_text(f"linha sem nada\nCPF {CPF_A}\n", encoding="utf-8")
    assert _achados(gz) == 1 and _achados(texto) == 1


@pytest.mark.parametrize("texto", ["LOJA 2020 2021 2022", "TEL 61 3215 1234", "11.222.333/0001-81", "VALOR 1.234,56"])
def test_a_varredura_nao_acusa_o_que_nao_e_cpf(texto):
    assert cpfs_validos_em(texto) == 0
