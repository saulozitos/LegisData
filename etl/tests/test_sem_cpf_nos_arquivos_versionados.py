"""D3: nenhum arquivo versionado pode carregar CPF (nem em texto, nem como chave, nem como número solto de campo de documento)."""

import csv
import gzip
import io
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from etl.pipelines.loader_helpers import cpfs_suspeitos_em
from etl.tests.sinteticos import CNPJ_DE_RAIZ_ZERADA, CPF_A, DOZE_DIGITOS_SEM_CPF, formatado

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
    *(".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".cfg", ".mjs", ".example", ".env", ".ipynb"),
}
NOMES_SEM_EXTENSAO = {"Makefile", "Dockerfile"}
# Sequências de versão e hashes de lockfiles somam dígitos que passam no verificador por acaso: só eles ficam de fora.
FORA = ("output/",)
LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock")
CHAVES_DE_DOCUMENTO = ("cpf", "documento", "doc", "cnpj", "cnpj_cpf", "cpf_cnpj")


def _versionados():
    if shutil.which("git") is None:
        return []
    resultado = subprocess.run(["git", "ls-files", "-z"], cwd=RAIZ, capture_output=True, check=False)
    if resultado.returncode != 0:  # fora de um checkout git (tarball): os testes pulam em vez de falhar na coleta
        return []
    saida = resultado.stdout.decode("utf-8")
    return sorted(
        RAIZ / nome
        for nome in saida.split("\0")
        if nome
        and not nome.startswith(FORA)
        and Path(nome).name not in LOCKFILES
        and (Path(nome).suffix in EXTENSOES or Path(nome).name in NOMES_SEM_EXTENSAO or nome.endswith(".json.gz"))
    )


ARQUIVOS = _versionados()


def _chave_de_documento(chave: str) -> bool:
    chave = chave.lower()
    return "cpf" in chave or "cnpj" in chave or chave in CHAVES_DE_DOCUMENTO


def _textos(no):
    """Textos de um JSON: valores string e chaves; e inteiros de 10 ou 11 dígitos em campo cujo nome sugere documento."""
    if isinstance(no, dict):
        for chave, valor in no.items():
            yield str(chave)
            if isinstance(valor, int) and not isinstance(valor, bool) and _chave_de_documento(str(chave)):
                yield str(valor).zfill(14 if "cnpj" in str(chave).lower() else 11)
            yield from _textos(valor)
    elif isinstance(no, list):
        for item in no:
            yield from _textos(item)
    elif isinstance(no, str):
        yield no


def _janelas(arquivo: Path) -> bool:
    """As janelas de 11 dígitos em números corridos só valem em código; em dados, códigos de emenda dariam falso positivo."""
    return arquivo.suffix in (".py", ".sh")


def _achados(arquivo: Path) -> int:
    janelas = _janelas(arquivo)
    if arquivo.name.endswith(".json.gz"):
        with gzip.open(arquivo, "rt", encoding="utf-8") as aberto:
            conteudo = aberto.read()
    else:
        conteudo = arquivo.read_text(encoding="utf-8", errors="replace")
    if arquivo.suffix == ".json" or arquivo.name.endswith(".json.gz"):
        return sum(cpfs_suspeitos_em(texto, janelas) for texto in _textos(json.loads(conteudo)))
    if arquivo.suffix == ".csv":
        return _achados_no_csv(conteudo)
    return sum(cpfs_suspeitos_em(linha, janelas) for linha in conteudo.splitlines())


NUMERO = re.compile(r"^-?[0-9]+(?:[.,][0-9]+)?$")


def _achados_no_csv(conteudo: str) -> int:
    """Célula puramente numérica é valor (reais, contagem): só vale como documento se a coluna tem nome de documento."""
    linhas = list(csv.reader(io.StringIO(conteudo)))
    cabecalho = [c.lower() for c in linhas[0]] if linhas else []
    achados = 0
    for linha in linhas[1:]:
        for i, celula in enumerate(linha):
            coluna_de_documento = i < len(cabecalho) and any(h in cabecalho[i] for h in CHAVES_DE_DOCUMENTO)
            if NUMERO.match(celula.strip()) and not coluna_de_documento:
                continue
            achados += cpfs_suspeitos_em(celula, False)
    return achados


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
    assert any(n.startswith("frontend/") for n in nomes) and not any(Path(n).name in LOCKFILES for n in nomes)
    assert "etl/tests/test_sem_cpf_nos_arquivos_versionados.py" in nomes


# ── Controle positivo: a guarda enxerga o que deve enxergar (senão passaria sempre) ───────────────────────────────────
@pytest.mark.parametrize(
    "texto",
    [
        f"FULANO {CPF_A}, 2",  # um CPF solto antes de uma vírgula não se esconde atrás dela
        f'"JOAO {CPF_A}", "12345678000195"',
        f"FULANO {CPF_A[:4]} {CPF_A[4:8]} {CPF_A[8:]} / 2024",
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
    assert cpfs_suspeitos_em(texto) >= 1


def test_a_varredura_acha_cpf_em_chave_em_valor_e_em_inteiro_de_campo_de_documento(tmp_path):
    arquivo = tmp_path / "x.json"
    for conteudo in (
        {CPF_A: 1},
        {"nome": f"F {CPF_A}"},
        {"cpf": int(CPF_A)},
        [{"documento": int(CPF_A)}],
        {"nr_cpf_candidato": int(CPF_A)},
        {"cpf_doador": int(CPF_A)},
    ):
        arquivo.write_text(json.dumps(conteudo), encoding="utf-8")
        assert _achados(arquivo) == 1, conteudo
    arquivo.write_text(json.dumps({"valor_pago_brl": int(CPF_A)}), encoding="utf-8")
    assert _achados(arquivo) == 0  # um valor em reais que coincide com os dígitos não é CPF


def test_a_varredura_de_csv_ignora_valor_numerico_mas_acha_documento_em_coluna_de_documento_e_texto(tmp_path):
    csv_ = tmp_path / "x.csv"
    csv_.write_text(f"valor,nome\n{CPF_A},ok\n", encoding="utf-8")
    assert _achados(csv_) == 0  # célula só de dígitos numa coluna de valor
    csv_.write_text(f"cpf_doador,nome\n{CPF_A},ok\n", encoding="utf-8")
    assert _achados(csv_) == 1
    csv_.write_text(f"valor,nome\n10,FULANO {CPF_A}\n", encoding="utf-8")
    assert _achados(csv_) == 1


def test_a_varredura_le_json_gz_e_texto_comum(tmp_path):
    gz = tmp_path / "x.json.gz"
    gz.write_bytes(gzip.compress(json.dumps({"a": f"F {CPF_A}"}).encode()))
    texto = tmp_path / "x.md"
    texto.write_text(f"linha sem nada\nCPF {CPF_A}\n", encoding="utf-8")
    assert _achados(gz) == 1 and _achados(texto) == 1


@pytest.mark.parametrize("texto", ["LOJA 2020 2021 2022", "TEL 61 3215 1234", "11.222.333/0001-81", "VALOR 1.234,56"])
def test_a_varredura_nao_acusa_o_que_nao_e_cpf(texto):
    assert cpfs_suspeitos_em(texto) == 0


def test_a_varredura_acha_cpf_colado_a_outros_digitos_em_codigo_mas_nao_em_dados(tmp_path):
    codigo, dados = tmp_path / "x.py", tmp_path / "x.json"
    colado = f'x = "7{CPF_A}"'  # um dígito antes do CPF: a janela de 11 dígitos é um CPF válido
    codigo.write_text(colado, encoding="utf-8")
    dados.write_text(json.dumps({"codigo_da_emenda": f"7{CPF_A}"}), encoding="utf-8")
    assert _achados(codigo) == 1  # em código escrito à mão, qualquer janela conta
    assert _achados(dados) == 0  # em dados, número corrido de 12 a 14 dígitos é código de emenda ou de processo


def test_a_varredura_acha_cpf_dentro_da_mascara_de_cnpj_e_em_campo_de_cnpj(tmp_path):
    d = "000" + CPF_A
    mascara = f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    arquivo = tmp_path / "x.json"
    for conteudo in ({"nome": f"MEI {mascara}"}, {"cnpj": int(d)}, [{"cnpj_fornecedor": int(d)}]):
        arquivo.write_text(json.dumps(conteudo), encoding="utf-8")
        assert _achados(arquivo) >= 1, conteudo
    csv_ = tmp_path / "x.csv"
    csv_.write_text(f"nome,cnpj_fornecedor\nMEI,{d}\n", encoding="utf-8")
    assert _achados(csv_) >= 1


def test_a_varredura_nao_acusa_cnpj_conhecido_url_nem_numero_sem_cpf(tmp_path):
    codigo = tmp_path / "x.py"
    codigo.write_text(
        f'a = "{CNPJ_DE_RAIZ_ZERADA}"\nb = "https://site/pesquisa/?num_registro={CPF_A[:1]}{CPF_A}"\nc = "{DOZE_DIGITOS_SEM_CPF}"\n',
        encoding="utf-8",
    )
    assert _achados(codigo) == 0
