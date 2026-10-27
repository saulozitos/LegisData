"""
Carga das séries econômicas e sociais em `eco.observacao` a partir dos arquivos processados pelos extratores.

Regras:
- Só entram valores de fonte oficial: linhas marcadas `is_synthetic` são descartadas e célula vazia vira ausência de
  observação (nunca zero).
- A janela começa em 1995-01-01 (decisão D8); anos anteriores são ignorados.
- Cada série é apagada e regravada por inteiro, mas só se o arquivo trouxe ao menos uma linha dela: arquivo vazio ou
  sem a coluna não apaga a base.
- O catálogo (`eco.serie`) vem da migração; série desconhecida no mapa é erro, não é criada às escondidas.

Idempotente: duas execuções seguidas deixam a tabela igual.
"""

import csv
import logging
import math
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.utils.bootstrap import ensure_backend_on_path

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("EconomiaLoader")

INICIO_JANELA = date(1995, 1, 1)

# arquivo -> (coluna do arquivo -> código da série). Uma linha por ano, abrangência nacional.
SERIES_ANUAIS_BR: Dict[str, Dict[str, str]] = {
    "resumo_macroeconomico_anual.csv": {
        "ipca_acumulado_ano_pct": "IPCA_ACUM_ANO",
        "pib_crescimento_real_pct": "PIB_CRESC_REAL",
        "taxa_desemprego_anual": "DESEMPREGO_ANUAL",
        "taxa_desmatamento_amazonia": "DESMATAMENTO_AMAZONIA",
        "cambio_dolar_medio": "CAMBIO_MEDIO_ANO",
        "cotacao_dolar_fechamento": "CAMBIO_FECHAMENTO_ANO",
        "salario_minimo_nominal_brl": "SALARIO_MINIMO",
        "divida_liquida_pct_pib": "DIVIDA_LIQUIDA_PIB",
    },
    "indicadores_sociais_anuais.csv": {
        "gini": "GINI",
        "analfabetismo": "ANALFABETISMO",
        "extrema_pobreza_pct": "EXTREMA_POBREZA_PCT",
        "extrema_pobreza_milhoes": "EXTREMA_POBREZA_MILHOES",
        "pobreza_pct": "POBREZA_PCT",
        "inseguranca_alimentar_pct": "INSEGURANCA_ALIMENTAR_PCT",
        "inseguranca_alimentar_milhoes": "INSEGURANCA_ALIMENTAR_MILHOES",
        "inseguranca_alimentar_total_pct": "INSEGURANCA_ALIMENTAR_TOTAL_PCT",
    },
    "seguranca_publica_historico.csv": {
        "taxa_homicidios": "HOMICIDIOS_TAXA",
        "homicidios_total": "HOMICIDIOS_TOTAL",
    },
}

# série -> coluna do mesmo arquivo que vai para a `nota` da observação (a pesquisa de onde o número saiu: o Gini tem
# quebra metodológica em 2012 e a tela precisa dizer qual pesquisa é cada ponto)
NOTAS_DAS_SERIES: Dict[str, str] = {"GINI": "serie_gini"}

SERIES_ANUAIS_UF: Dict[str, Dict[str, str]] = {
    "indicadores_sociais_uf.csv": {
        "indice_gini": "GINI_UF",
        "taxa_analfabetismo_pct": "ANALFABETISMO_UF",
        "extrema_pobreza_pct": "EXTREMA_POBREZA_UF",
        "pobreza_pct": "POBREZA_UF",
        "inseguranca_alimentar_pct": "INSEGURANCA_ALIMENTAR_UF",
    }
}


class Observacao(NamedTuple):
    serie: str
    referencia: date
    uf: Optional[str]
    valor: float
    parcial: bool
    nota: Optional[str] = None


def numero(valor: Any) -> Optional[float]:
    """Número finito ou None; texto vazio, 'nan' e infinito são ausência."""
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = valor.strip().replace(",", ".") if valor.strip() else None
        if valor is None:
            return None
    try:
        resultado = float(valor)
    except (TypeError, ValueError):
        return None
    return resultado if math.isfinite(resultado) else None


def sintetico(linha: Dict[str, str]) -> bool:
    return str(linha.get("is_synthetic", "")).strip().lower() in ("true", "1", "sim")


def parcial(linha: Dict[str, str]) -> bool:
    return str(linha.get("parcial", "")).strip().lower() in ("true", "1", "sim")


def ler_csv(caminho: Path) -> List[Dict[str, str]]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de séries ausente: {caminho}")
    with open(caminho, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def observacoes_anuais(linhas: Iterable[Dict[str, str]], colunas: Dict[str, str], com_uf: bool) -> List[Observacao]:
    resultado: List[Observacao] = []
    for linha in linhas:
        if sintetico(linha):
            continue
        ano = numero(linha.get("ano"))
        if ano is None or date(int(ano), 1, 1) < INICIO_JANELA:
            continue
        uf = (linha.get("uf") or "").strip().upper() if com_uf else None
        if com_uf and not uf:
            continue
        for coluna, codigo in colunas.items():
            valor = numero(linha.get(coluna))
            if valor is not None:
                nota = (linha.get(NOTAS_DAS_SERIES.get(codigo, "")) or "").strip() or None
                resultado.append(Observacao(codigo, date(int(ano), 1, 1), uf, valor, parcial(linha), nota))
    return resultado


def observacoes_ipca_mensal(linhas: Iterable[Dict[str, str]]) -> List[Observacao]:
    resultado: List[Observacao] = []
    for linha in linhas:
        try:
            referencia = date.fromisoformat((linha.get("data") or "").strip())
        except ValueError:
            continue
        valor = numero(linha.get("valor"))
        if valor is not None and referencia >= INICIO_JANELA:
            resultado.append(Observacao("IPCA_MENSAL", referencia.replace(day=1), None, valor, False))
    return resultado


def observacoes_mensais(linhas: Iterable[Dict[str, str]]) -> List[Observacao]:
    """Arquivo longo `serie,data,valor`: o código da série vem na própria linha."""
    resultado: List[Observacao] = []
    for linha in linhas:
        try:
            referencia = date.fromisoformat((linha.get("data") or "").strip())
        except ValueError:
            continue
        codigo = (linha.get("serie") or "").strip()
        valor = numero(linha.get("valor"))
        if codigo and valor is not None and referencia >= INICIO_JANELA:
            resultado.append(Observacao(codigo, referencia.replace(day=1), None, valor, False))
    return resultado


def observacoes_subsidio(linhas: Iterable[Dict[str, str]]) -> List[Observacao]:
    """Subsídio parlamentar: só entra valor com a norma citada (decreto legislativo), que vai para a `nota`."""
    observacoes: List[Observacao] = []
    for linha in linhas:
        ano, valor, norma = numero(linha.get("ano")), numero(linha.get("valor")), (linha.get("norma") or "").strip()
        if ano is None or valor is None or valor <= 0 or not norma or date(int(ano), 1, 1) < INICIO_JANELA:
            continue
        observacoes.append(Observacao("SUBSIDIO_PARLAMENTAR", date(int(ano), 1, 1), None, valor, False, norma))
    return observacoes


def reunir(processed_dir: Path) -> List[Observacao]:
    """Lê todos os arquivos; falha se algum estiver ausente, antes de qualquer alteração no banco."""
    todas: List[Observacao] = []
    for arquivo, colunas in SERIES_ANUAIS_BR.items():
        todas += observacoes_anuais(ler_csv(processed_dir / arquivo), colunas, com_uf=False)
    for arquivo, colunas in SERIES_ANUAIS_UF.items():
        todas += observacoes_anuais(ler_csv(processed_dir / arquivo), colunas, com_uf=True)
    todas += observacoes_ipca_mensal(ler_csv(processed_dir / "ipca_mensal_historico.csv"))
    todas += observacoes_mensais(ler_csv(processed_dir / "bcb_series_mensais.csv"))
    todas += observacoes_subsidio(ler_csv(processed_dir / "subsidio_parlamentar.csv"))
    return todas


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, int]:
    """Grava as observações e devolve a contagem por série."""
    pasta = Path(processed_dir or PROCESSED_DATA_DIR)
    observacoes = reunir(pasta)
    por_serie: Dict[str, List[Observacao]] = {}
    for obs in observacoes:
        por_serie.setdefault(obs.serie, []).append(obs)
    if not por_serie:
        logger.warning("Nenhuma observação nos arquivos; a base não foi alterada.")
        return {}

    with engine.begin() as conn:
        ids = {codigo: id_ for id_, codigo in conn.execute(text("SELECT id, codigo FROM eco.serie"))}
        desconhecidas = sorted(set(por_serie) - set(ids))
        if desconhecidas:
            raise ValueError(f"Séries fora do catálogo eco.serie: {', '.join(desconhecidas)}")
        for codigo, linhas in por_serie.items():
            conn.execute(text("DELETE FROM eco.observacao WHERE serie_id = :s"), {"s": ids[codigo]})
            conn.execute(
                text(
                    "INSERT INTO eco.observacao (serie_id, referencia, uf, valor, parcial, nota) "
                    "VALUES (:s, :r, :uf, :v, :p, :n) "
                    "ON CONFLICT (serie_id, referencia, uf_chave) DO UPDATE SET valor = EXCLUDED.valor, "
                    "parcial = EXCLUDED.parcial, nota = EXCLUDED.nota"
                ),
                [
                    {"s": ids[codigo], "r": o.referencia, "uf": o.uf, "v": o.valor, "p": o.parcial, "n": o.nota}
                    for o in linhas
                ],
            )
    contagem = {codigo: len(linhas) for codigo, linhas in por_serie.items()}
    logger.info("Séries carregadas em eco.observacao: %s", contagem)
    return contagem
