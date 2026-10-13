"""
Resultados das eleições presidenciais por UF a partir dos dados abertos do TSE.

Fonte: `votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip` (votos por candidato, município e zona).
Somam-se os votos nominais válidos de cada candidato por UF e turno; o vencedor e o segundo colocado de cada UF
saem do turno DECISIVO (2º turno quando houve, senão o 1º) e os percentuais são sobre os votos válidos do turno
naquela UF. Os resultados de 1994 em diante estão disponíveis; 1989 não existe nos dados abertos do TSE e não é
preenchido (lacuna documentada, nunca estimada). Votos do exterior (UF "ZZ") entram apenas no total nacional.
"""

import csv
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.social_indicators_extractor import ESTADOS_BRASIL
from etl.extractors.tse_core import CSV_ENCODING, TSE_RAW_DIR, baixar, fonte
from etl.utils.datafiles import load_json
from etl.utils.io_utils import atomic_write_text
from etl.utils.provenance import mark_official

logger = logging.getLogger("TSEEleicoesExtractor")

ANOS_PADRAO = (1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022)
COLUNAS = {
    "SG_UF",
    "NR_TURNO",
    "DS_CARGO",
    "NM_CANDIDATO",
    "SG_PARTIDO",
    "QT_VOTOS_NOMINAIS",
    "QT_VOTOS_NOMINAIS_VALIDOS",
}
SAIDA = "eleicoes_presidenciais_uf_tse.csv"
CAMPOS = [
    "ano_eleicao",
    "mandato_id_ref",
    "uf",
    "estado_nome",
    "regiao",
    "candidato_vencedor_nome",
    "partido_vencedor_sigla",
    "votos_vencedor_pct",
    "candidato_segundo_nome",
    "partido_segundo_sigla",
    "votos_segundo_pct",
    "total_votos_validos",
    "turno",
    "verificado",
    "is_synthetic",
    "fonte",
]
PARTICULAS = {"de", "da", "do", "das", "dos", "e"}


def nome_proprio(nome: str) -> str:
    """'LUIZ INÁCIO LULA DA SILVA' -> 'Luiz Inácio Lula da Silva'."""
    palavras = str(nome or "").strip().lower().split()
    return " ".join(p if (i and p in PARTICULAS) else p.capitalize() for i, p in enumerate(palavras))


def mandato_por_ano(presidentes: List[Dict[str, Any]]) -> Dict[int, str]:
    """Ano de eleição -> `id_referencia` do primeiro mandato dela decorrente (ex.: 2014 -> dilma-2015)."""
    escolhido: Dict[int, Tuple[str, str]] = {}
    for p in presidentes:
        ano, ref, inicio = p.get("ano_eleicao"), p.get("id_referencia"), str(p.get("data_inicio") or "9999")
        if not ano or not ref:
            continue
        if int(ano) not in escolhido or inicio < escolhido[int(ano)][0]:
            escolhido[int(ano)] = (inicio, ref)
    return {ano: ref for ano, (_, ref) in escolhido.items()}


def _numero(serie: pd.Series) -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").fillna(0)


def somar_votos(zip_path: Path, chunksize: int = 500_000) -> pd.DataFrame:
    """Votos por (UF, turno, candidato, partido) para presidente. Prefere o `_BR.csv` (só cargos nacionais)."""
    with zipfile.ZipFile(zip_path) as zf:
        nomes = [i.filename for i in zf.infolist()]
        membro = next((n for n in nomes if re.search(r"_BR\.csv$", n)), None) or next(
            (n for n in nomes if re.search(r"_BRASIL\.csv$", n)), None
        )
        if membro is None:
            raise ValueError(f"{zip_path.name}: sem arquivo consolidado de votação")
        parciais: List[pd.DataFrame] = []
        with zf.open(membro) as fh:
            for bloco in pd.read_csv(
                fh,
                sep=";",
                encoding=CSV_ENCODING,
                dtype=str,
                keep_default_na=False,
                usecols=lambda c: c in COLUNAS,
                chunksize=chunksize,
                on_bad_lines="skip",
            ):
                bloco = bloco[bloco["DS_CARGO"].str.upper() == "PRESIDENTE"]
                if bloco.empty:
                    continue
                validos = _numero(bloco.get("QT_VOTOS_NOMINAIS_VALIDOS", pd.Series(0, index=bloco.index)))
                if validos.sum() == 0:  # anos antigos podem trazer só a coluna não filtrada
                    validos = _numero(bloco.get("QT_VOTOS_NOMINAIS", pd.Series(0, index=bloco.index)))
                parciais.append(
                    bloco.assign(votos=validos)
                    .groupby(["SG_UF", "NR_TURNO", "NM_CANDIDATO", "SG_PARTIDO"], as_index=False)["votos"]
                    .sum()
                )
    if not parciais:
        return pd.DataFrame(columns=["SG_UF", "NR_TURNO", "NM_CANDIDATO", "SG_PARTIDO", "votos"])
    total = pd.concat(parciais, ignore_index=True)
    return total.groupby(["SG_UF", "NR_TURNO", "NM_CANDIDATO", "SG_PARTIDO"], as_index=False)["votos"].sum()


def resultados_por_uf(votos: pd.DataFrame, ano: int, mandato_ref: str, origem: str) -> List[Dict[str, Any]]:
    """Vencedor e segundo colocado de cada UF no turno decisivo, com percentuais sobre os votos válidos."""
    if votos.empty:
        return []
    turno = str(votos["NR_TURNO"].astype(int).max()) if votos["NR_TURNO"].str.isdigit().all() else "1"
    decisivo = votos[votos["NR_TURNO"] == turno]
    linhas: List[Dict[str, Any]] = []
    for estado in ESTADOS_BRASIL:
        do_estado = decisivo[decisivo["SG_UF"] == estado["uf"]].sort_values("votos", ascending=False)
        total = float(do_estado["votos"].sum())
        if len(do_estado) < 2 or total <= 0:
            continue
        primeiro, segundo = do_estado.iloc[0], do_estado.iloc[1]
        linhas.append(
            mark_official(
                {
                    "ano_eleicao": ano,
                    "mandato_id_ref": mandato_ref,
                    "uf": estado["uf"],
                    "estado_nome": estado["nome"],
                    "regiao": estado["regiao"],
                    "candidato_vencedor_nome": nome_proprio(primeiro["NM_CANDIDATO"]),
                    "partido_vencedor_sigla": primeiro["SG_PARTIDO"],
                    "votos_vencedor_pct": round(float(primeiro["votos"]) / total * 100, 2),
                    "candidato_segundo_nome": nome_proprio(segundo["NM_CANDIDATO"]),
                    "partido_segundo_sigla": segundo["SG_PARTIDO"],
                    "votos_segundo_pct": round(float(segundo["votos"]) / total * 100, 2),
                    "total_votos_validos": int(total),
                    "turno": int(turno),
                    "verificado": True,
                },
                origem,
            )
        )
    return linhas


class TSEEleicoesExtractor:
    def __init__(self, processed_dir: Path = PROCESSED_DATA_DIR, raw_dir: Path = TSE_RAW_DIR):
        self.processed_dir = Path(processed_dir)
        self.raw_dir = Path(raw_dir)

    def run(self, anos: Optional[Iterable[int]] = None, force: bool = False, **_ignorado: Any) -> List[Dict[str, Any]]:
        presidentes = load_json(self.processed_dir / "presidentes_historico.json", []) or []
        refs = mandato_por_ano(presidentes)
        todas: List[Dict[str, Any]] = []
        for ano in anos or ANOS_PADRAO:
            ano = int(ano)
            ref = refs.get(ano)
            if not ref:
                logger.warning("Eleição %s sem mandato correspondente em presidentes_historico.json: ignorada.", ano)
                continue
            arquivo = f"votacao_candidato_munzona_{ano}.zip"
            caminho = baixar("votacao_candidato_munzona", arquivo, self.raw_dir, force)
            if not caminho:
                continue
            linhas = resultados_por_uf(somar_votos(caminho), ano, ref, fonte("votacao_candidato_munzona", arquivo))
            logger.info("[%s] %d UFs apuradas (turno decisivo).", ano, len(linhas))
            todas.extend(linhas)

        if not todas:
            logger.warning("Nenhum resultado obtido: %s preservado.", SAIDA)
            return []
        destino = self.processed_dir / SAIDA
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CAMPOS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(todas)
        atomic_write_text(destino, buffer.getvalue())
        logger.info("%d resultados por UF salvos em %s.", len(todas), destino)
        return todas


if __name__ == "__main__":
    TSEEleicoesExtractor().run()
