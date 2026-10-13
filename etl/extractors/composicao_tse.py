"""
Bancadas ELEITAS por partido (Câmara e Senado) a partir do `consulta_cand` do TSE.

Para cada eleição conta-se, por `SG_PARTIDO`, os candidatos a Deputado Federal / Senador com situação final
("DS_SIT_TOT_TURNO") "ELEITO", "ELEITO POR QP" ou "ELEITO POR MÉDIA". É a composição NA ELEIÇÃO (partido do dia
do pleito): trocas de partido posteriores e suplentes que assumem não entram. O Senado renova 1/3 e 2/3 a cada
4 anos, com mandatos de 8: a bancada de uma legislatura que começa no ano Y soma os eleitos em Y-1 e em Y-5.
"""

import logging
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from etl.extractors.tse_core import CSV_ENCODING, TSE_RAW_DIR, baixar, escolher_membros, fonte

logger = logging.getLogger("ComposicaoTSE")

COLUNAS = ["SG_UF", "NR_CANDIDATO", "NM_CANDIDATO", "DS_CARGO", "SG_PARTIDO", "DS_SIT_TOT_TURNO"]
# `SQ_CANDIDATO` não é único nos arquivos antigos (2002-2006): a identidade é UF + número + nome.
CHAVE_CANDIDATO = ["SG_UF", "NR_CANDIDATO", "NM_CANDIDATO"]
CARGO_CAMARA = "DEPUTADO FEDERAL"
CARGO_SENADO = "SENADOR"
# Os rótulos variam por ano: "ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA" e, nos arquivos antigos, só "MÉDIA".
ELEITOS = ("ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA", "ELEITO POR MEDIA", "MÉDIA", "MEDIA", "QP")
ANOS_DISPONIVEIS = (1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022)


def contar_eleitos(df: pd.DataFrame, cargo: str) -> Dict[str, int]:
    """{partido: eleitos} de um DataFrame de consulta_cand (um registro por candidato)."""
    eleitos = df[(df["DS_CARGO"].str.upper() == cargo) & (df["DS_SIT_TOT_TURNO"].str.upper().isin(ELEITOS))]
    eleitos = eleitos.drop_duplicates(CHAVE_CANDIDATO)
    return dict(Counter(eleitos["SG_PARTIDO"].str.strip()))


def eleitos_por_partido(
    ano: int, cargo: str, raw_dir: Path = TSE_RAW_DIR, force: bool = False
) -> Optional[Dict[str, int]]:
    """Eleitos do `cargo` na eleição de `ano`, ou None se o arquivo do TSE não está disponível."""
    if ano not in ANOS_DISPONIVEIS:
        return None
    zip_path = baixar("consulta_cand", f"consulta_cand_{ano}.zip", raw_dir, force)
    if zip_path is None:
        return None
    partes = []
    with zipfile.ZipFile(zip_path) as zf:
        membros = escolher_membros([i.filename for i in zf.infolist()])
        for nome in membros:
            with zf.open(nome) as fh:
                partes.append(
                    pd.read_csv(fh, sep=";", encoding=CSV_ENCODING, dtype=str, usecols=COLUNAS, keep_default_na=False)
                )
    if not partes:
        return None
    return contar_eleitos(pd.concat(partes, ignore_index=True), cargo)


def bancada_camara(ano_legislatura: int, **kw: Any) -> Optional[Dict[str, int]]:
    """Deputados federais eleitos na eleição que antecede a legislatura que começa em `ano_legislatura`."""
    return eleitos_por_partido(ano_legislatura - 1, CARGO_CAMARA, **kw)


def bancada_senado(ano_legislatura: int, **kw: Any) -> Optional[Dict[str, int]]:
    """Senadores em exercício no início da legislatura: eleitos em Y-1 (mandato novo) e em Y-5 (ainda vigentes)."""
    recente = eleitos_por_partido(ano_legislatura - 1, CARGO_SENADO, **kw)
    anterior = eleitos_por_partido(ano_legislatura - 5, CARGO_SENADO, **kw)
    if recente is None or anterior is None:
        return None  # sem uma das duas eleições o total não fecha: não se publica bancada parcial
    soma: Counter = Counter(recente)
    soma.update(anterior)
    return dict(soma)


def fonte_consulta(ano: int) -> str:
    return fonte("consulta_cand", f"consulta_cand_{ano}.zip")
