"""
Núcleo compartilhado dos extratores do TSE (dados abertos em cdn.tse.jus.br).

- download em streaming (zips grandes ficam em `etl/data/raw/tse/`, ignorado pelo git);
- leitura em blocos dos CSV dentro do zip (latin-1, separador `;`);
- universo de parlamentares/presidentes e CASAMENTO SEGURO candidato -> político:
  CPF (quando os dois lados têm) > nome exato + data de nascimento > nome exato + UF.
  Nunca por substring; homônimos ambíguos são descartados e contados.
"""

import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Set, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.datafiles import load_deputados, load_json, load_senadores
from etl.utils.download import DownloadError, NotFoundError, download_file
from etl.utils.identidades import IdentidadesParlamentares, parse_date, valid_cpf
from etl.utils.names import normalize_plain

logger = logging.getLogger("TSECore")

TSE_CDN = "https://cdn.tse.jus.br/estatistica/sead/odsele"
TSE_RAW_DIR = RAW_DATA_DIR / "tse"
FONTE_TSE = "TSE — Dados Abertos (cdn.tse.jus.br/estatistica/sead/odsele)"
CSV_ENCODING = "latin-1"
CARGOS_NACIONAIS = frozenset({"PRESIDENTE", "VICE-PRESIDENTE"})


def fonte(dataset: str, arquivo: str) -> str:
    """Texto de proveniência com a URL exata do arquivo usado."""
    return f"{FONTE_TSE}: {dataset}/{arquivo}"


def baixar(dataset: str, arquivo: str, raw_dir: Path = TSE_RAW_DIR, force: bool = False) -> Optional[Path]:
    """Baixa `dataset/arquivo` do CDN do TSE. Devolve None se o arquivo não existe (404) ou o download falha."""
    url = f"{TSE_CDN}/{dataset}/{arquivo}"
    try:
        return download_file(url, Path(raw_dir) / arquivo, force=force, timeout=180.0)
    except NotFoundError:
        logger.warning("Arquivo inexistente no TSE: %s", url)
    except DownloadError as exc:
        logger.error("Falha ao baixar %s: %s", url, exc)
    return None


# ----------------------------------------------------------------------------------------------------------
# Leitura dos CSV dentro dos zips
# ----------------------------------------------------------------------------------------------------------
def escolher_membros(nomes: Sequence[str], padrao: str = r"\.csv$") -> List[str]:
    """
    Membros CSV a ler. Prefere o consolidado `*_BRASIL.csv`; sem ele, junta os arquivos por UF
    (nunca `*_BR.csv` junto do consolidado, que duplicaria os registros nacionais).
    """
    csvs = [n for n in nomes if re.search(padrao, n, re.I) and not n.endswith("/")]
    brasil = [n for n in csvs if re.search(r"_BRASIL\.csv$", n, re.I)]
    return brasil or csvs


def ler_csv_zip(
    zip_path: Path,
    *,
    padrao: str = r"\.csv$",
    usecols: Optional[Callable[[str], bool]] = None,
    chunksize: int = 200_000,
    membros: Optional[str] = None,
) -> Iterator[pd.DataFrame]:
    """
    Itera os blocos (strings) dos CSV do zip. Por padrão usa o consolidado `*_BRASIL.csv`; com `membros`
    (regex) lê exatamente os arquivos cujo nome casa (ex.: um arquivo por UF).
    """
    with zipfile.ZipFile(zip_path) as zf:
        nomes = [i.filename for i in zf.infolist()]
        selecionados = (
            [n for n in nomes if re.search(membros, n) and not n.endswith("/")]
            if membros
            else escolher_membros(nomes, padrao)
        )
        for membro in selecionados:
            with zf.open(membro) as fh:
                reader = pd.read_csv(
                    fh,
                    sep=";",
                    encoding=CSV_ENCODING,
                    dtype=str,
                    keep_default_na=False,
                    usecols=usecols,
                    chunksize=chunksize,
                    on_bad_lines="skip",
                )
                for bloco in reader:
                    yield bloco


def parse_brl(value: Any) -> Optional[float]:
    """'15000,00' -> 15000.0. Marcadores do TSE (#NE, #NULO, -1, vazio) -> None."""
    text = str(value if value is not None else "").strip().strip('"')
    if not text or text.startswith("#"):
        return None
    text = text.replace(".", "").replace(",", ".") if "," in text else text
    try:
        return float(text)
    except ValueError:
        return None


# ----------------------------------------------------------------------------------------------------------
# Universo de políticos e casamento
# ----------------------------------------------------------------------------------------------------------
@dataclass
class Politico:
    chave: str
    nome_civil: str
    nome_eleitoral: str
    uf: Optional[str]
    cargo: str
    camara_id: Optional[int] = None
    senado_id: Optional[int] = None
    cpf: Optional[str] = field(default=None, repr=False)
    nascimento: Optional[date] = None

    def identificadores(self) -> Dict[str, Any]:
        """Campos de identificação gravados nos arquivos processados (sem CPF)."""
        return {
            "nome_civil": self.nome_civil,
            "nome_eleitoral": self.nome_eleitoral,
            "camara_id": self.camara_id,
            "senado_id": self.senado_id,
        }


def carregar_universo(
    processed_dir: Path = PROCESSED_DATA_DIR,
    identidades: Optional[IdentidadesParlamentares] = None,
    *,
    consultar_apis: bool = True,
) -> List[Politico]:
    """Deputados, senadores e presidentes conhecidos, enriquecidos com CPF/nascimento das APIs oficiais."""
    deputados = load_deputados(processed_dir)
    senadores = load_senadores(processed_dir)
    presidentes = load_json(Path(processed_dir) / "presidentes_historico.json", []) or []

    if identidades is None:
        identidades = IdentidadesParlamentares(offline=not consultar_apis)
    if consultar_apis:
        identidades.enrich([d.get("camara_id") for d in deputados], [s.get("senado_id") for s in senadores])

    universo: List[Politico] = []
    for d in deputados:
        ident = identidades.get(f"camara:{d.get('camara_id')}") or {}
        universo.append(
            Politico(
                chave=f"camara:{d.get('camara_id')}",
                camara_id=d.get("camara_id"),
                nome_civil=ident.get("nome_civil") or d.get("nome_civil") or d.get("nome_eleitoral") or "",
                nome_eleitoral=d.get("nome_eleitoral") or "",
                uf=(d.get("uf") or "").upper() or None,
                cargo="DEPUTADO_FEDERAL",
                cpf=valid_cpf(ident.get("cpf")),
                nascimento=parse_date(ident.get("data_nascimento")),
            )
        )
    for s in senadores:
        ident = identidades.get(f"senado:{s.get('senado_id')}") or {}
        universo.append(
            Politico(
                chave=f"senado:{s.get('senado_id')}",
                senado_id=s.get("senado_id"),
                nome_civil=ident.get("nome_civil") or s.get("nome_civil") or s.get("nome_eleitoral") or "",
                nome_eleitoral=s.get("nome_eleitoral") or "",
                uf=(s.get("uf") or "").upper() or None,
                cargo="SENADOR",
                cpf=None,
                nascimento=parse_date(ident.get("data_nascimento")),
            )
        )
    vistos: Set[Tuple[str, str]] = set()
    for p in presidentes:
        nome = p.get("nome_civil") or p.get("nome_eleitoral") or ""
        pessoa = (normalize_plain(nome), str(p.get("data_nascimento") or ""))
        if not nome or pessoa in vistos:  # um mesmo presidente aparece em vários mandatos
            continue
        vistos.add(pessoa)
        universo.append(
            Politico(
                chave=f"presidente:{normalize_plain(nome)}",
                nome_civil=nome,
                nome_eleitoral=p.get("nome_eleitoral") or nome,
                uf="BR",
                cargo="PRESIDENTE",
                nascimento=parse_date(p.get("data_nascimento")),
            )
        )
    return universo


CANDIDATO_COLUNAS = {
    "ANO_ELEICAO",
    "SG_UF",
    "SG_UE",
    "DS_CARGO",
    "SQ_CANDIDATO",
    "NM_CANDIDATO",
    "NM_URNA_CANDIDATO",
    "NR_CPF_CANDIDATO",
    "DT_NASCIMENTO",
    "SG_PARTIDO",
    "DS_SITUACAO_CANDIDATURA",
    "DS_DETALHE_SITUACAO_CAND",
    "DS_SIT_TOT_TURNO",
    "NR_TURNO",
    "NR_PROCESSO",
}


def ler_candidatos(zip_path: Path) -> pd.DataFrame:
    """consulta_cand de um ano: uma linha por candidato, com colunas auxiliares de casamento."""
    blocos = list(ler_csv_zip(zip_path, usecols=lambda c: c in CANDIDATO_COLUNAS))
    if not blocos:
        return pd.DataFrame(columns=sorted(CANDIDATO_COLUNAS))
    df = pd.concat(blocos, ignore_index=True)
    for coluna in CANDIDATO_COLUNAS:
        if coluna not in df.columns:
            df[coluna] = ""
    df["cand_key"] = df["SG_UE"].astype(str) + "|" + df["SQ_CANDIDATO"].astype(str)
    # candidatos a presidente/governador aparecem uma vez por turno: mantém um registro por candidato
    df = df.drop_duplicates("cand_key", keep="first").reset_index(drop=True)
    df["_civil"] = df["NM_CANDIDATO"].map(normalize_plain)
    df["_urna"] = df["NM_URNA_CANDIDATO"].map(normalize_plain)
    df["_cpf"] = df["NR_CPF_CANDIDATO"].map(valid_cpf)
    df["_nasc"] = df["DT_NASCIMENTO"].map(parse_date)
    return df


@dataclass
class ResultadoCasamento:
    casados: Dict[str, int] = field(default_factory=dict)  # chave do político -> índice no DataFrame
    motivo: Dict[str, str] = field(default_factory=dict)
    ambiguos: int = 0
    sem_candidato: int = 0


def _uf_compativel(p: Politico, uf_candidato: str) -> bool:
    uf_candidato = (uf_candidato or "").upper()
    if p.cargo == "PRESIDENTE":
        return True  # presidentes disputaram sempre como "BR", mas podem ter disputado cargos estaduais
    return bool(p.uf) and uf_candidato in (p.uf, "BR")


def casar_candidatos(universo: Sequence[Politico], candidatos: pd.DataFrame) -> ResultadoCasamento:
    """
    Casa cada político a NO MÁXIMO um candidato do ano. Evidência, da mais forte para a mais fraca:
    CPF; nome (civil ou de urna) exato + data de nascimento; nome exato + mesma UF. Se houver mais de um
    candidato compatível (homônimos) o político fica sem casamento — melhor omitir do que errar a pessoa.
    """
    res = ResultadoCasamento()
    if candidatos.empty:
        res.sem_candidato = len(universo)
        return res

    por_civil: Dict[str, List[int]] = {}
    por_urna: Dict[str, List[int]] = {}
    cpfs = candidatos["_cpf"].tolist()
    civis = candidatos["_civil"].tolist()
    urnas = candidatos["_urna"].tolist()
    nascs = candidatos["_nasc"].tolist()
    ufs = candidatos["SG_UF"].tolist()
    cargos = candidatos["DS_CARGO"].str.upper().tolist()
    por_cpf: Dict[str, List[int]] = {}
    for idx, cpf in enumerate(cpfs):
        if cpf:
            por_cpf.setdefault(cpf, []).append(idx)
    for idx, (c, u) in enumerate(zip(civis, urnas)):
        if c:
            por_civil.setdefault(c, []).append(idx)
        if u:
            por_urna.setdefault(u, []).append(idx)

    reivindicacoes: Dict[int, List[str]] = {}
    for p in universo:
        escolhido: Optional[int] = None
        motivo = ""
        if p.cpf and p.cpf in por_cpf:
            achados = set(por_cpf[p.cpf])
            if len(achados) == 1:
                escolhido, motivo = next(iter(achados)), "cpf"
            else:
                res.ambiguos += 1
                continue
        else:
            n_civil, n_ele = normalize_plain(p.nome_civil), normalize_plain(p.nome_eleitoral)
            achados = set()
            if n_civil:
                achados |= set(por_civil.get(n_civil, ()))
            if n_ele:
                achados |= set(por_civil.get(n_ele, ())) | set(por_urna.get(n_ele, ()))
            aceitos: List[Tuple[int, str]] = []
            for idx in achados:
                if p.cpf and cpfs[idx] and cpfs[idx] != p.cpf:
                    continue
                if p.nascimento and nascs[idx]:
                    if p.nascimento == nascs[idx]:
                        aceitos.append((idx, "nascimento"))
                    elif (
                        p.cargo == "PRESIDENTE"
                        and ufs[idx] == "BR"
                        and civis[idx] == n_civil
                        and cargos[idx] in CARGOS_NACIONAIS
                    ):
                        # O cadastro do TSE pode divergir da biografia (ex.: Lula consta como nascido em 06/10/1945).
                        # Candidatura nacional + nome civil completo exato é evidência suficiente.
                        aceitos.append((idx, "nome+cargo_nacional"))
                    continue
                if _uf_compativel(p, ufs[idx]):
                    aceitos.append((idx, "nome+uf"))
            if len(aceitos) == 1:
                escolhido, motivo = aceitos[0]
            elif len(aceitos) > 1:
                res.ambiguos += 1
                continue
        if escolhido is None:
            res.sem_candidato += 1
            continue
        res.casados[p.chave] = escolhido
        res.motivo[p.chave] = motivo
        reivindicacoes.setdefault(escolhido, []).append(p.chave)

    # mesmo candidato reivindicado por políticos diferentes sem evidência forte: descarta todos (homônimos)
    for idx, chaves in reivindicacoes.items():
        if len(chaves) > 1:
            fracos = [c for c in chaves if res.motivo[c] in ("nome+uf", "nome+cargo_nacional")]
            for c in fracos:
                res.casados.pop(c, None)
                res.motivo.pop(c, None)
                res.ambiguos += 1
    return res
