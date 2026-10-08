"""
Extrator de microdados da PNAD Contínua anual (IBGE) → distribuição por faixas de salário mínimo.

Fonte oficial (visita 5: traz o rendimento de TODAS as fontes e o rendimento domiciliar):
    https://ftp.ibge.gov.br/Trabalho_e_Rendimento/Pesquisa_Nacional_por_Amostra_de_Domicilios_continua/
    Anual/Microdados/Visita/Visita_5/

O que o módulo faz, em streaming (o arquivo descompactado tem ~2 GB; nada é carregado inteiro em memória):
  1. descobre os anos publicados e baixa o `.zip` de microdados e o dicionário de variáveis (`input_*.txt`);
  2. lê as posições das colunas do dicionário oficial (formato SAS `@posição NOME [$]largura.`);
  3. soma, ponderando pelo peso calibrado `V1032`, quatro distribuições por faixa de salário mínimo:
       - domicilios_renda_total      : domicílios por rendimento habitual domiciliar total (VD5007)
       - pessoas_renda_domiciliar    : pessoas por rendimento habitual domiciliar total do seu domicílio (VD5007)
       - pessoas_renda_per_capita    : pessoas por rendimento habitual domiciliar per capita (VD5008)
       - ocupados_renda_trabalho     : pessoas ocupadas por rendimento habitual de todos os trabalhos (VD4019)
  4. grava `pnad_faixas_salario_minimo.json` (atômico, com proveniência) somente se a validação passar.

Convenções (documentadas também no JSON gerado, em `metodologia`):
  - Faixas em múltiplos do salário mínimo, intervalo fechado à esquerda: [min, max). "Sem rendimento" (<= 0) é
    uma faixa própria e entra no total.
  - Salário mínimo de cada ano: coluna `salario_minimo` de `resumo_macroeconomico_anual.csv`
    (valor nominal vigente ao final do ano, mesma série usada em todo o ETL).
  - O número de domicílios usa o peso do responsável (V2005 == "01"): a PNAD Contínua não publica peso
    domiciliar, e esta é a aproximação usual.
  - Pessoas sem rendimento domiciliar definido (pensionistas, empregados domésticos e parentes deles — VD5007/
    VD5008 vazios) ficam fora das bases domiciliares, como na metodologia do IBGE.
  - Valores monetários são NOMINAIS (preços do ano da pesquisa): a comparação é feita em salários mínimos do
    mesmo ano, nunca em reais entre anos.
"""

import logging
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

import numpy as np
import pandas as pd

from etl.config import DEFAULT_USER_AGENT, PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.io_utils import atomic_write_json
from etl.utils.provenance import mark_official

logger = logging.getLogger("PNADExtractor")

BASE_URL = (
    "https://ftp.ibge.gov.br/Trabalho_e_Rendimento/Pesquisa_Nacional_por_Amostra_de_Domicilios_continua/"
    "Anual/Microdados/Visita/Visita_{visita}"
)
VISITA_PADRAO = 5
ANO_INICIAL_PADRAO = 2016  # primeiro ano com microdados de visita 5 publicados pelo IBGE

PNAD_RAW_DIR = RAW_DATA_DIR / "pnad"
OUTPUT_FILE = PROCESSED_DATA_DIR / "pnad_faixas_salario_minimo.json"
OUTPUT_FILENAME = OUTPUT_FILE.name

# Faixas em salários mínimos: [min, max). A faixa 0 é "sem rendimento" (valor <= 0).
BORDAS_SM: Tuple[float, ...] = (0.5, 1.0, 2.0, 4.0, 10.0, 20.0)
FAIXAS: List[Dict[str, Any]] = [
    {"id": "sem_rendimento", "rotulo": "Sem rendimento", "min_sm": None, "max_sm": None},
    {"id": "ate_0_5", "rotulo": "Até 1/2 SM", "min_sm": 0.0, "max_sm": 0.5},
    {"id": "0_5_a_1", "rotulo": "Mais de 1/2 a 1 SM", "min_sm": 0.5, "max_sm": 1.0},
    {"id": "1_a_2", "rotulo": "Mais de 1 a 2 SM", "min_sm": 1.0, "max_sm": 2.0},
    {"id": "2_a_4", "rotulo": "Mais de 2 a 4 SM", "min_sm": 2.0, "max_sm": 4.0},
    {"id": "4_a_10", "rotulo": "Mais de 4 a 10 SM", "min_sm": 4.0, "max_sm": 10.0},
    {"id": "10_a_20", "rotulo": "Mais de 10 a 20 SM", "min_sm": 10.0, "max_sm": 20.0},
    {"id": "mais_de_20", "rotulo": "Mais de 20 SM", "min_sm": 20.0, "max_sm": None},
]
N_FAIXAS = len(FAIXAS)

# Colunas lidas do microdado (nome oficial → papel)
COLUNAS_NECESSARIAS = ("Ano", "UF", "V1032", "V2005", "VD4002", "VD4019", "VD5007", "VD5008")

# Códigos IBGE das UFs
UF_POR_CODIGO = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}

# A soma dos pesos de todas as pessoas deve ser da ordem da população brasileira (~210 milhões).
POPULACAO_MIN = 150_000_000
POPULACAO_MAX = 260_000_000
DOMICILIOS_MIN = 40_000_000
DOMICILIOS_MAX = 120_000_000

INDICADORES = (
    "domicilios_renda_total",
    "pessoas_renda_domiciliar",
    "pessoas_renda_per_capita",
    "ocupados_renda_trabalho",
)

METODOLOGIA = {
    "ponderacao": "Peso calibrado V1032 (PNAD Contínua anual, visita 5).",
    "faixas": "Múltiplos do salário mínimo do ano de referência, intervalo [min, max); 'Sem rendimento' é <= 0.",
    "salario_minimo": "Série `salario_minimo` do ETL (valor nominal vigente ao final do ano de referência).",
    "domicilios": "Peso do responsável pelo domicílio (V2005 == '01'); a PNAD Contínua não publica peso domiciliar.",
    "renda_domiciliar_total": "VD5007: rendimento habitual domiciliar (todas as fontes).",
    "renda_per_capita": "VD5008: rendimento habitual domiciliar per capita (todas as fontes).",
    "renda_do_trabalho": "VD4019: rendimento habitual de todos os trabalhos (pessoas ocupadas, VD4002 == '1').",
    "valores_monetarios": "Nominais (preços do ano da pesquisa); compare apenas em salários mínimos do mesmo ano.",
}


class PNADError(RuntimeError):
    """Falha definitiva do extrator (download, layout, validação)."""


# ----------------------------------------------------------------------------------------------------------
# Download
# ----------------------------------------------------------------------------------------------------------
Opener = Callable[..., Any]


def _abrir(url: str, metodo: str, timeout: float, opener: Opener, user_agent: str):
    req = urllib.request.Request(url, method=metodo, headers={"User-Agent": user_agent})
    return opener(req, timeout=timeout)


def _tamanho_remoto(url: str, timeout: float, opener: Opener, user_agent: str) -> Optional[int]:
    try:
        with _abrir(url, "HEAD", timeout, opener, user_agent) as resp:
            valor = resp.headers.get("Content-Length")
            return int(valor) if valor else None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        logger.warning("HEAD falhou em %s: %s", url, exc)
        return None


def baixar_arquivo(
    url: str,
    destino: Path,
    *,
    forcar: bool = False,
    tentativas: int = 4,
    timeout: float = 120.0,
    opener: Opener = urllib.request.urlopen,
    user_agent: str = DEFAULT_USER_AGENT,
    espera: Callable[[float], None] = time.sleep,
) -> Path:
    """Baixa `url` em streaming para `destino` (escrita atômica). Reaproveita o cache se o tamanho confere."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    esperado = _tamanho_remoto(url, timeout, opener, user_agent)

    if destino.exists() and not forcar:
        if esperado is None or destino.stat().st_size == esperado:
            logger.info("Cache válido: %s", destino.name)
            return destino
        logger.warning("Cache de %s com tamanho divergente; baixando de novo.", destino.name)

    ultimo_erro: Optional[BaseException] = None
    for tentativa in range(1, max(1, tentativas) + 1):
        fd, tmp_name = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".part", dir=str(destino.parent))
        os.close(fd)
        try:
            gravados = 0
            with _abrir(url, "GET", timeout, opener, user_agent) as resp, open(tmp_name, "wb") as out:
                if esperado is None:
                    valor = resp.headers.get("Content-Length")
                    esperado = int(valor) if valor else None
                while True:
                    bloco = resp.read(1024 * 1024)
                    if not bloco:
                        break
                    out.write(bloco)
                    gravados += len(bloco)
                out.flush()
                os.fsync(out.fileno())
            if esperado is not None and gravados != esperado:
                raise PNADError(f"Download truncado ({gravados} de {esperado} bytes)")
            os.replace(tmp_name, destino)
            logger.info("Baixado %s (%.1f MB)", destino.name, gravados / 1e6)
            return destino
        except (urllib.error.URLError, TimeoutError, OSError, PNADError) as exc:
            ultimo_erro = exc
            logger.warning("Falha ao baixar %s (tentativa %d/%d): %s", url, tentativa, tentativas, exc)
            if tentativa < tentativas:
                espera(2.0**tentativa)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
    raise PNADError(f"Não foi possível baixar {url}: {ultimo_erro}")


def _listar(url: str, timeout: float, opener: Opener, user_agent: str) -> str:
    with _abrir(url.rstrip("/") + "/", "GET", timeout, opener, user_agent) as resp:
        return resp.read().decode("utf-8", errors="replace")


def descobrir_arquivos(
    visita: int = VISITA_PADRAO,
    *,
    timeout: float = 60.0,
    opener: Opener = urllib.request.urlopen,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Dict[int, Dict[str, str]]:
    """Mapeia ano → {zip, input} (URLs) a partir das listagens de diretório do FTP do IBGE."""
    base = BASE_URL.format(visita=visita)
    try:
        dados = _listar(f"{base}/Dados", timeout, opener, user_agent)
        docs = _listar(f"{base}/Documentacao", timeout, opener, user_agent)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PNADError(f"Listagem do FTP do IBGE indisponível: {exc}") from exc

    zips: Dict[int, str] = {}
    for nome in re.findall(rf'href="(PNADC_(\d{{4}})_visita{visita}[^"]*\.zip)"', dados):
        zips[int(nome[1])] = nome[0]
    inputs: Dict[int, str] = {}
    for nome in re.findall(rf'href="(input_PNADC_(\d{{4}})_visita{visita}[^"]*\.txt)"', docs):
        inputs[int(nome[1])] = nome[0]

    achados: Dict[int, Dict[str, str]] = {}
    for ano, nome_zip in sorted(zips.items()):
        if ano in inputs:
            achados[ano] = {"zip": f"{base}/Dados/{nome_zip}", "input": f"{base}/Documentacao/{inputs[ano]}"}
    return achados


# ----------------------------------------------------------------------------------------------------------
# Layout e leitura
# ----------------------------------------------------------------------------------------------------------
_LINHA_LAYOUT = re.compile(r"^@(\d+)\s+(\w+)\s+(\$?)(\d+)\.", re.MULTILINE)


def parse_layout(texto: str) -> Dict[str, Tuple[int, int]]:
    """Dicionário SAS → {nome: (início 0-based, largura)}. Ex.: '@0058 V1032 15.' → ('V1032': (57, 15))."""
    layout: Dict[str, Tuple[int, int]] = {}
    for pos, nome, _char, largura in _LINHA_LAYOUT.findall(texto):
        layout[nome] = (int(pos) - 1, int(largura))
    return layout


def colunas_do_layout(layout: Dict[str, Tuple[int, int]]) -> Dict[str, Tuple[int, int]]:
    faltando = [c for c in COLUNAS_NECESSARIAS if c not in layout]
    if faltando:
        raise PNADError(f"Dicionário de variáveis sem as colunas {faltando}")
    return {c: layout[c] for c in COLUNAS_NECESSARIAS}


def _ler_blocos(
    fileobj: Iterable[bytes], colunas: Dict[str, Tuple[int, int]], tamanho_bloco: int = 100_000
) -> Iterator[pd.DataFrame]:
    """Lê o arquivo posicional em blocos de linhas; devolve DataFrames só com as colunas necessárias."""
    nomes = list(colunas)
    fatias = [colunas[n] for n in nomes]
    buffers: List[List[bytes]] = [[] for _ in nomes]
    n = 0
    for linha in fileobj:
        linha = linha.rstrip(b"\r\n")
        if not linha.strip():
            continue
        for i, (ini, larg) in enumerate(fatias):
            buffers[i].append(linha[ini : ini + larg].strip())
        n += 1
        if n >= tamanho_bloco:
            yield _montar(nomes, buffers)
            buffers = [[] for _ in nomes]
            n = 0
    if n:
        yield _montar(nomes, buffers)


def _montar(nomes: List[str], buffers: List[List[bytes]]) -> pd.DataFrame:
    dados: Dict[str, Any] = {}
    for nome, col in zip(nomes, buffers):
        serie = pd.Series([c.decode("latin-1") for c in col], dtype=object)
        if nome in ("Ano", "UF", "V2005", "VD4002"):
            dados[nome] = serie
        else:
            dados[nome] = pd.to_numeric(serie.replace("", np.nan), errors="coerce")
    return pd.DataFrame(dados)


# ----------------------------------------------------------------------------------------------------------
# Agregação ponderada
# ----------------------------------------------------------------------------------------------------------
def indice_faixa(valor_sm: np.ndarray) -> np.ndarray:
    """Índice da faixa [min, max) para valores em salários mínimos; <= 0 → 0 ('sem rendimento')."""
    idx = 1 + np.searchsorted(np.asarray(BORDAS_SM), valor_sm, side="right")
    return np.where(valor_sm <= 0, 0, idx)


class Acumulador:
    """Soma ponderada por faixa (e totais para a média), por indicador e por UF."""

    def __init__(self) -> None:
        self.faixas: Dict[Tuple[str, str], np.ndarray] = {}
        self.soma_valor: Dict[Tuple[str, str], float] = {}
        self.peso_valor: Dict[Tuple[str, str], float] = {}
        self.peso_total_pessoas = 0.0
        self.linhas = 0

    def _add(self, indicador: str, uf: pd.Series, idx: np.ndarray, peso: np.ndarray, valor: np.ndarray) -> None:
        ufs = uf.to_numpy()
        for chave_uf in ("BR", *sorted(set(ufs))):
            mascara = np.ones(len(ufs), dtype=bool) if chave_uf == "BR" else ufs == chave_uf
            if not mascara.any():
                continue
            chave = (indicador, chave_uf)
            if chave not in self.faixas:
                self.faixas[chave] = np.zeros(N_FAIXAS)
                self.soma_valor[chave] = 0.0
                self.peso_valor[chave] = 0.0
            self.faixas[chave] += np.bincount(idx[mascara], weights=peso[mascara], minlength=N_FAIXAS)
            self.soma_valor[chave] += float(np.sum(peso[mascara] * valor[mascara]))
            self.peso_valor[chave] += float(np.sum(peso[mascara]))

    def adicionar(self, bloco: pd.DataFrame, salario_minimo: float) -> None:
        peso = bloco["V1032"].to_numpy(dtype=float)
        valido = ~np.isnan(peso) & (peso > 0)
        bloco = bloco[valido]
        peso = peso[valido]
        self.linhas += len(bloco)
        self.peso_total_pessoas += float(peso.sum())
        uf = bloco["UF"].str[:2].map(UF_POR_CODIGO).fillna("ND")

        # Pessoas por renda domiciliar total e per capita (apenas quem tem renda domiciliar definida)
        total = bloco["VD5007"].to_numpy(dtype=float)
        per_capita = bloco["VD5008"].to_numpy(dtype=float)

        m = ~np.isnan(total)
        if m.any():
            self._add(
                "pessoas_renda_domiciliar",
                uf[m],
                indice_faixa(total[m] / salario_minimo),
                peso[m],
                total[m],
            )
        m = ~np.isnan(per_capita)
        if m.any():
            self._add(
                "pessoas_renda_per_capita",
                uf[m],
                indice_faixa(per_capita[m] / salario_minimo),
                peso[m],
                per_capita[m],
            )

        # Domicílios: uma linha por domicílio, o responsável
        resp = (bloco["V2005"].to_numpy() == "01") & ~np.isnan(total)
        if resp.any():
            self._add(
                "domicilios_renda_total",
                uf[resp],
                indice_faixa(total[resp] / salario_minimo),
                peso[resp],
                total[resp],
            )

        # Ocupados por rendimento do trabalho
        trabalho = bloco["VD4019"].to_numpy(dtype=float)
        ocup = (bloco["VD4002"].to_numpy() == "1") & ~np.isnan(trabalho)
        if ocup.any():
            self._add(
                "ocupados_renda_trabalho",
                uf[ocup],
                indice_faixa(trabalho[ocup] / salario_minimo),
                peso[ocup],
                trabalho[ocup],
            )

    def resultado(self) -> Dict[str, Any]:
        def bloco(indicador: str, uf: str) -> Optional[Dict[str, Any]]:
            chave = (indicador, uf)
            if chave not in self.faixas:
                return None
            soma = self.faixas[chave]
            total = float(soma.sum())
            if total <= 0:
                return None
            media = self.soma_valor[chave] / self.peso_valor[chave] if self.peso_valor[chave] else None
            return {
                "total_estimado": int(round(total)),
                "percentual": [round(float(v) / total * 100.0, 2) for v in soma],
                "media_nominal_brl": round(media, 2) if media is not None else None,
            }

        nacional = {i: bloco(i, "BR") for i in INDICADORES}
        ufs = sorted({uf for (_, uf) in self.faixas if uf not in ("BR", "ND")})
        por_uf = {uf: {i: bloco(i, uf) for i in INDICADORES} for uf in ufs}
        return {"nacional": nacional, "uf": por_uf}


def validar_ano(acc: Acumulador, ano: int) -> None:
    if not (POPULACAO_MIN <= acc.peso_total_pessoas <= POPULACAO_MAX):
        raise PNADError(
            f"{ano}: soma dos pesos ({acc.peso_total_pessoas:,.0f}) fora do intervalo plausível "
            f"[{POPULACAO_MIN:,}, {POPULACAO_MAX:,}] — layout ou arquivo inconsistente"
        )
    nac = acc.resultado()["nacional"]
    for indicador in INDICADORES:
        info = nac[indicador]
        if not info:
            raise PNADError(f"{ano}: indicador '{indicador}' sem dados")
        if abs(sum(info["percentual"]) - 100.0) > 0.2:
            raise PNADError(f"{ano}: percentuais de '{indicador}' não somam 100%")
    dom = nac["domicilios_renda_total"]["total_estimado"]
    if not (DOMICILIOS_MIN <= dom <= DOMICILIOS_MAX):
        raise PNADError(f"{ano}: número de domicílios implausível ({dom:,})")


def processar_zip(zip_path: Path, layout_texto: str, salario_minimo: float, ano: int) -> Dict[str, Any]:
    """Lê o `.zip` de microdados em streaming e devolve a distribuição do ano (validada)."""
    colunas = colunas_do_layout(parse_layout(layout_texto))
    acc = Acumulador()
    with zipfile.ZipFile(zip_path) as zf:
        membros = [i for i in zf.infolist() if i.filename.lower().endswith(".txt")]
        if not membros:
            raise PNADError(f"{zip_path.name}: nenhum .txt dentro do zip")
        with zf.open(membros[0]) as bruto:
            for bloco in _ler_blocos(bruto, colunas):
                anos = bloco["Ano"].dropna().unique()
                if len(anos) and any(a != str(ano) for a in anos):
                    raise PNADError(f"{zip_path.name}: contém ano(s) {sorted(anos)} diferente(s) de {ano}")
                acc.adicionar(bloco, salario_minimo)
    validar_ano(acc, ano)
    res = acc.resultado()
    res["linhas_lidas"] = acc.linhas
    res["populacao_total_estimada"] = int(round(acc.peso_total_pessoas))
    return res


# ----------------------------------------------------------------------------------------------------------
# Orquestração
# ----------------------------------------------------------------------------------------------------------
def carregar_salarios_minimos(csv_path: Optional[Path] = None) -> Dict[int, float]:
    caminho = csv_path or (PROCESSED_DATA_DIR / "resumo_macroeconomico_anual.csv")
    if not Path(caminho).exists():
        raise PNADError(f"Série de salário mínimo ausente: {caminho} (rode --economic antes)")
    df = pd.read_csv(caminho, usecols=["ano", "salario_minimo"]).dropna()
    return {int(r.ano): float(r.salario_minimo) for r in df.itertuples()}


class PNADExtractor:
    def __init__(
        self,
        visita: int = VISITA_PADRAO,
        raw_dir: Path = PNAD_RAW_DIR,
        output_file: Path = OUTPUT_FILE,
        opener: Opener = urllib.request.urlopen,
        salarios_minimos: Optional[Dict[int, float]] = None,
    ):
        self.visita = visita
        self.raw_dir = Path(raw_dir)
        self.output_file = Path(output_file)
        self.opener = opener
        self._salarios = salarios_minimos

    def _carregar_existente(self) -> Dict[str, Any]:
        if self.output_file.exists():
            try:
                import json

                with open(self.output_file, "r", encoding="utf-8") as fh:
                    dados = json.load(fh)
                if isinstance(dados, dict) and isinstance(dados.get("anos"), dict):
                    return dados
            except (ValueError, OSError) as exc:
                logger.warning("Saída anterior ilegível (%s); será refeita.", exc)
        return {}

    def run(self, anos: Optional[Iterable[int]] = None, force: bool = False) -> Dict[str, Any]:
        salarios = self._salarios if self._salarios is not None else carregar_salarios_minimos()
        disponiveis = descobrir_arquivos(self.visita, opener=self.opener)
        if not disponiveis:
            raise PNADError("Nenhum microdado PNAD encontrado no FTP do IBGE")

        alvo = sorted(set(anos)) if anos else [a for a in sorted(disponiveis) if a >= ANO_INICIAL_PADRAO]
        sem_arquivo = [a for a in alvo if a not in disponiveis]
        if sem_arquivo:
            raise PNADError(f"Anos sem microdado publicado (visita {self.visita}): {sem_arquivo}")

        anterior = {} if force else self._carregar_existente()
        resultado_anos: Dict[str, Any] = dict(anterior.get("anos", {}))

        for ano in alvo:
            urls = disponiveis[ano]
            if str(ano) in resultado_anos and resultado_anos[str(ano)].get("arquivo_microdados") == urls["zip"]:
                logger.info("PNAD %d já extraída de %s; mantendo.", ano, urls["zip"].rsplit("/", 1)[-1])
                continue
            sm = salarios.get(ano)
            if sm is None or sm <= 0:
                logger.warning("PNAD %d: sem salário mínimo na série do ETL — ano ignorado.", ano)
                continue
            logger.info("PNAD %d: baixando e processando…", ano)
            zip_path = baixar_arquivo(
                urls["zip"], self.raw_dir / urls["zip"].rsplit("/", 1)[-1], forcar=force, opener=self.opener
            )
            layout_path = baixar_arquivo(
                urls["input"], self.raw_dir / urls["input"].rsplit("/", 1)[-1], forcar=force, opener=self.opener
            )
            layout_texto = layout_path.read_text(encoding="latin-1")
            dados = processar_zip(zip_path, layout_texto, sm, ano)
            resultado_anos[str(ano)] = {
                "ano": ano,
                "visita": self.visita,
                "salario_minimo_brl": sm,
                "arquivo_microdados": urls["zip"],
                "dicionario": urls["input"],
                "data_extracao": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                **dados,
            }

        if not resultado_anos:
            raise PNADError("Nenhum ano processado; arquivo de saída preservado.")

        ordenados = {k: resultado_anos[k] for k in sorted(resultado_anos)}
        saida: Dict[str, Any] = {
            "descricao": "Distribuição por faixas de salário mínimo calculada dos microdados da PNAD Contínua anual",
            "faixas": FAIXAS,
            "metodologia": METODOLOGIA,
            "ano_mais_recente": max(int(a) for a in ordenados),
            "anos": ordenados,
        }
        mark_official(
            saida,
            "IBGE — PNAD Contínua anual, microdados (visita %d): %s"
            % (self.visita, BASE_URL.format(visita=self.visita)),
        )
        atomic_write_json(self.output_file, saida)
        logger.info("Gravado %s (%d anos)", self.output_file, len(ordenados))
        return saida
