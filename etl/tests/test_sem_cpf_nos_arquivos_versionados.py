"""D3: nenhum arquivo versionado pode carregar CPF (nem em texto, nem como chave, nem como número solto de campo de documento)."""

import csv
import gzip
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from etl.pipelines.loader_helpers import cpfs_suspeitos_em
from etl.tests.sinteticos import CNPJ_DE_RAIZ_ZERADA, CPF_A, DOZE_DIGITOS_SEM_CPF, formatado

RAIZ = Path(__file__).resolve().parents[2]
# Lista de EXCLUSÕES (não de inclusões): todo arquivo versionado que decodifica como texto é varrido, qualquer que seja a
# extensão (.prisma, .mts, .mako, .svg, dotfiles, .csv.gz...). Binários (imagens, fontes, dumps) não decodificam e saem.
BINARIOS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".dump",
    ".zip",
}
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
        and Path(nome).suffix.lower() not in BINARIOS
        and (RAIZ / nome).is_file()
    )


ARQUIVOS = _versionados()


def _chave_de_documento(chave: str) -> bool:
    chave = chave.lower()
    return any(trecho in chave for trecho in CHAVES_DE_DOCUMENTO)  # o mesmo critério (substring) do CSV


def _textos(no):
    """Textos de um JSON: valores string e chaves; e números inteiros (int, ou float sem casas, como o pandas grava) em campo cujo nome sugere documento."""
    if isinstance(no, dict):
        for chave, valor in no.items():
            yield str(chave)
            numero_inteiro = isinstance(valor, int) or (isinstance(valor, float) and valor.is_integer())
            if numero_inteiro and not isinstance(valor, bool) and _chave_de_documento(str(chave)):
                yield str(int(valor)).zfill(14 if "cnpj" in str(chave).lower() else 11)
            yield from _textos(valor)
    elif isinstance(no, list):
        for item in no:
            yield from _textos(item)
    elif isinstance(no, str):
        yield no


def _e_dado(arquivo: Path) -> bool:
    """Dados (JSON, CSV, e os compactados deles) somam códigos de emenda e de processo de 12 a 14 dígitos e valores em reais."""
    nome = arquivo.name.lower()
    return nome.endswith((".json", ".csv", ".json.gz", ".csv.gz")) or arquivo.parent.name == "processed"


def _janelas(arquivo: Path) -> bool:
    """As janelas (CPF colado a outros dígitos, ou em grupos com qualquer pontuação) valem em tudo que não é dado."""
    if arquivo.suffix.lower() == ".svg":  # coordenadas de desenho: só as formas formatadas de CPF valem
        return False
    return not _e_dado(arquivo) and not (arquivo.suffix == ".md" and "docs" in arquivo.parts)


def _ler(arquivo: Path) -> str:
    """
    Texto do arquivo (descompactando .gz). Fora de UTF-8 (os CSVs da Câmara e do TSE vêm em latin-1) lê como latin-1, que
    sempre decodifica: nenhum arquivo versionado escapa da varredura por causa da codificação. Binário de verdade fica em
    `BINARIOS`; um `.gz` corrompido levanta (o teste falha em vez de contar zero achados).
    """
    if arquivo.name.lower().endswith(".gz"):
        bruto = gzip.decompress(arquivo.read_bytes())
    else:
        bruto = arquivo.read_bytes()
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def _achados(arquivo: Path) -> int:
    janelas = _janelas(arquivo)
    conteudo = _ler(arquivo)
    nome = arquivo.name.lower()
    if nome.endswith(".svg"):  # os números dos atributos de desenho (caminho, pontos, matriz) não são texto
        conteudo = re.sub(r'\b(?:d|points|viewBox|transform|style)="[^"]*"', " ", conteudo)
    if nome.endswith((".json", ".json.gz")):
        # (texto sem nenhum dígito, inclusive Unicode, não tem CPF: o filtro só poupa tempo nas listas grandes)
        return sum(
            cpfs_suspeitos_em(texto, janelas)
            for texto in _textos(json.loads(conteudo))
            if any(c.isdigit() for c in texto)
        )
    if nome.endswith((".csv", ".csv.gz")):
        return _achados_no_csv(conteudo)
    return sum(cpfs_suspeitos_em(linha, janelas) for linha in conteudo.splitlines())


NUMERO = re.compile(r"^-?[0-9]+(?:[.,][0-9]+)?$")


def _achados_no_csv(conteudo: str) -> int:
    """Célula puramente numérica é valor (reais, contagem): só vale como documento se a coluna tem nome de documento."""
    linhas = list(csv.reader(io.StringIO(conteudo)))
    cabecalho = [c.lower() for c in linhas[0]] if linhas else []
    achados = sum(cpfs_suspeitos_em(celula, False) for celula in (linhas[0] if linhas else []))  # o cabeçalho também
    for linha in linhas[1:]:
        for i, celula in enumerate(linha):
            coluna_de_documento = i < len(cabecalho) and any(h in cabecalho[i] for h in CHAVES_DE_DOCUMENTO)
            if NUMERO.match(celula.strip()) and not coluna_de_documento:
                continue
            achados += cpfs_suspeitos_em(celula, False)
    return achados


def test_no_ci_a_varredura_nunca_pula_por_falta_de_git():
    """Sem `git ls-files` a guarda de D3 inteira viraria skip silencioso: no CI isso é falha."""
    if os.environ.get("CI"):
        assert ARQUIVOS, "git indisponível ou checkout sem .git: a guarda de CPF não varreu nada"


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
        # grupos ligados por qualquer pontuação constante (a guarda é mais desconfiada que o saneamento, não menos)
        f'("{CPF_A[:3]}", "{CPF_A[3:6]}", "{CPF_A[6:9]}", "{CPF_A[9:]}")',
        f"{CPF_A[:3]}/{CPF_A[3:6]}/{CPF_A[6:9]}/{CPF_A[9:]}",
        f"{CPF_A[:4]},{CPF_A[4:8]},{CPF_A[8:]}",
        f"{CPF_A[:2]};{CPF_A[2:5]};{CPF_A[5:8]};{CPF_A[8:]}",
        ",".join(CPF_A),  # um dígito por vez
        f"[{CPF_A[:3]}|{CPF_A[3:6]}|{CPF_A[6:9]}|{CPF_A[9:]}]",
        f"FULANO {CPF_A[:3]}.{CPF_A[3:6]}.{CPF_A[6:9]}/{CPF_A[9:]}",  # separadores mistos, barra no fim
        f"FULANO 123{CPF_A}",  # CPF colado a 3 dígitos (14 corridos que não fecham como CNPJ)
        f"FULANO 99{CPF_A}",  # e a 2 dígitos (13)
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
        assert _achados(arquivo) >= 1, conteudo
    arquivo.write_text(json.dumps({"valor_pago_brl": int(CPF_A)}), encoding="utf-8")
    assert _achados(arquivo) == 0  # um valor em reais que coincide com os dígitos não é CPF


def test_a_varredura_de_csv_ignora_valor_numerico_mas_acha_documento_em_coluna_de_documento_e_texto(tmp_path):
    csv_ = tmp_path / "x.csv"
    csv_.write_text(f"valor,nome\n{CPF_A},ok\n", encoding="utf-8")
    assert _achados(csv_) == 0  # célula só de dígitos numa coluna de valor
    csv_.write_text(f"cpf_doador,nome\n{CPF_A},ok\n", encoding="utf-8")
    assert _achados(csv_) >= 1
    csv_.write_text(f"valor,nome\n10,FULANO {CPF_A}\n", encoding="utf-8")
    assert _achados(csv_) >= 1


def test_a_varredura_le_json_gz_e_texto_comum(tmp_path):
    gz = tmp_path / "x.json.gz"
    gz.write_bytes(gzip.compress(json.dumps({"a": f"F {CPF_A}"}).encode()))
    texto = tmp_path / "x.md"
    texto.write_text(f"linha sem nada\nCPF {CPF_A}\n", encoding="utf-8")
    assert _achados(gz) >= 1 and _achados(texto) >= 1


@pytest.mark.parametrize(
    "texto",
    [
        "LOJA 2020 2021 2022",
        "TEL 61 3215 1234",
        "11.222.333/0001-81",
        "VALOR 1.234,56",
        "(2023, 400.5, 2022.1, 33.5)",  # tupla de números com separadores diversos
        "M12 3C4.567 8 9.101 2.345",  # coordenadas de desenho
    ],
)
def test_a_varredura_nao_acusa_o_que_nao_e_cpf(texto):
    assert cpfs_suspeitos_em(texto) == 0


def test_a_varredura_acha_cpf_colado_a_outros_digitos_em_codigo_mas_nao_em_dados(tmp_path):
    codigo, dados = tmp_path / "x.py", tmp_path / "x.json"
    colado = f'x = "7{CPF_A}"'  # um dígito antes do CPF: a janela de 11 dígitos é um CPF válido
    codigo.write_text(colado, encoding="utf-8")
    dados.write_text(json.dumps({"codigo_da_emenda": f"7{CPF_A}"}), encoding="utf-8")
    assert _achados(codigo) >= 1  # em código escrito à mão, qualquer janela conta
    assert _achados(dados) == 0  # em dados, número corrido de 12 a 14 dígitos é código de emenda ou de processo


@pytest.mark.parametrize(
    "nome",
    [
        "x.ts",
        "x.tsx",
        "x.prisma",
        "x.mts",
        "x.mako",
        "x.sql",
        "x.yml",
        "x.md",
        ".dockerignore",
        ".flake8",
        "LICENSE",
        "x.csv.gz",
    ],
)
def test_a_varredura_cobre_qualquer_extensao_de_texto_e_o_colado_so_nao_vale_em_dados(tmp_path, nome):
    arquivo = tmp_path / nome
    linha = f"x = 7{CPF_A}\n"  # CPF colado a um dígito
    if nome.endswith(".gz"):
        arquivo.write_bytes(gzip.compress(f"valor,nome\n10,F {CPF_A}\n".encode()))
    else:
        arquivo.write_text(linha, encoding="utf-8")
    assert _achados(arquivo) >= 1, nome


def test_a_varredura_le_latin1_e_falha_em_gz_corrompido_em_vez_de_contar_zero(tmp_path):
    latin1 = tmp_path / "x.csv"
    latin1.write_bytes(f"nome,obs\nJOS\xc9,F {CPF_A}\n".encode("latin-1"))  # 0xC9 não é UTF-8 válido
    assert _achados(latin1) >= 1
    quebrado = tmp_path / "x.csv.gz"
    quebrado.write_bytes(b"isto nao e gzip")
    with pytest.raises(OSError):
        _achados(quebrado)


def test_a_varredura_so_vigia_as_formas_de_texto_do_svg(tmp_path):
    svg = tmp_path / "x.svg"
    svg.write_text('<path d="M12 3C4.567 8 9.101 2.345 7 1 2 3 5 6"/>', encoding="utf-8")
    assert _achados(svg) == 0
    svg.write_text(f"<text>{CPF_A[:3]}.{CPF_A[3:6]}.{CPF_A[6:9]}-{CPF_A[9:]}</text>", encoding="utf-8")
    assert _achados(svg) >= 1


def test_a_varredura_acha_cpf_como_float_em_campo_de_documento_e_o_colado_nao_vale_na_pasta_processed(tmp_path):
    dados = tmp_path / "x.json"
    dados.write_text(json.dumps({"cpf": float(CPF_A)}), encoding="utf-8")
    assert _achados(dados) >= 1
    dados.write_text(json.dumps({"cpf": True, "valor": float(CPF_A)}), encoding="utf-8")
    assert _achados(dados) == 0  # bool não é documento, e valor em reais com os mesmos dígitos também não
    pasta = tmp_path / "processed"
    pasta.mkdir()
    texto = pasta / "x.txt"
    texto.write_text(f"codigo 7{CPF_A}\n", encoding="utf-8")
    assert _achados(texto) == 0  # a pasta de dados processados se comporta como dado: sem janelas
    fora = tmp_path / "y.txt"
    fora.write_text(f"codigo 7{CPF_A}\n", encoding="utf-8")
    assert _achados(fora) >= 1


@pytest.mark.skipif(not ARQUIVOS, reason="git indisponível")
def test_o_conjunto_varrido_inclui_extensoes_que_a_lista_antiga_deixava_de_fora():
    nomes = {p.name for p in ARQUIVOS} | {p.suffix for p in ARQUIVOS}
    assert {".prisma", ".mts", ".mako", ".svg", ".gitignore", ".dockerignore", ".flake8", "LICENSE"} <= nomes
    assert not any(p.suffix.lower() in BINARIOS for p in ARQUIVOS)


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
