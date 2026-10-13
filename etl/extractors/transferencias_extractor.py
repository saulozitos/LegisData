"""
Repasses federais por UF a partir dos CSVs OFICIAIS do Portal da Transparência (CGU).

Fonte: https://portaldatransparencia.gov.br/download-de-dados/transferencias/{AAAAMM} — transferências da
União a estados, Distrito Federal, municípios e entidades, por UF do favorecido, função e tipo de transferência.
Cobertura do portal: a partir de 2014-01. Meses anteriores não existem (HTTP 403) e ficam FORA do resultado.

O arquivo substitui o antigo modelo estatístico (população × peso FPE × fator inventado), que era apresentado
como execução orçamentária. Aqui só entra valor efetivamente transferido, somado por mês/UF/área.
"""

import csv
import io
import logging
import time
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.ibge_demografia import populacao_no_ano, populacao_uf
from etl.extractors.ufs import NOME_POR_UF, REGIAO_POR_UF
from etl.utils.datafiles import load_json
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_bytes, atomic_write_json, atomic_write_text
from etl.utils.provenance import mark_official
from etl.utils.sidra import SidraClient

logger = logging.getLogger("TransferenciasExtractor")

URL_MES = "https://portaldatransparencia.gov.br/download-de-dados/transferencias/{ym}"
PRIMEIRO_MES_DISPONIVEL = (2014, 1)
FONTE = "Portal da Transparência (CGU) — Transferências da União, CSV mensal"
METODOLOGIA = (
    "Soma do VALOR TRANSFERIDO por UF do favorecido, no período do mandato coberto pelo portal (a partir de 2014-01). "
    "Mandato atribuído pelo mês de referência; per capita = total do período / população da UF no último ano coberto. "
    "Áreas: Saúde, Educação, Assistência Social, Segurança Pública e Infraestrutura (agrupamento por função orçamentária); "
    "'Constitucionais e Royalties' reúne FPE/FPM/cota-parte/royalties; demais funções em 'Outras funções'."
)

COL_UF = "UF"
COL_TIPO = "TIPO TRANSFERÊNCIA"
COL_FUNCAO = "NOME FUNÇÃO"
COL_VALOR = "VALOR TRANSFERIDO"
COLUNAS = [COL_UF, COL_TIPO, COL_FUNCAO, COL_VALOR]

MAX_TENTATIVAS_BLOQUEIO = 8
ESPERA_BLOQUEIO_S = 60
ESPERA_MAXIMA_S = 600
MESES_TOLERADOS_SEM_PUBLICACAO = 2  # os últimos meses podem ainda não ter sido publicados

AREA_CONSTITUCIONAIS = "Constitucionais e Royalties"
AREA_OUTRAS = "Outras funções"
FUNCOES_INFRAESTRUTURA = {"urbanismo", "habitação", "saneamento", "transporte", "energia", "comunicações"}
FUNCOES_DIRETAS = {
    "saúde": "Saúde",
    "educação": "Educação",
    "assistência social": "Assistência Social",
    "segurança pública": "Segurança Pública",
}


def area_tematica(tipo_transferencia: str, funcao: str) -> str:
    """Agrupa tipo de transferência + função orçamentária numa área temática estável."""
    if str(tipo_transferencia).strip().lower().startswith("constitucionais"):
        return AREA_CONSTITUCIONAIS
    f = str(funcao).strip().lower()
    if f in FUNCOES_DIRETAS:
        return FUNCOES_DIRETAS[f]
    if f in FUNCOES_INFRAESTRUTURA:
        return "Infraestrutura"
    return AREA_OUTRAS


def meses_no_intervalo(inicio: Tuple[int, int], fim: Tuple[int, int]) -> List[str]:
    saida = []
    ano, mes = inicio
    while (ano, mes) <= fim:
        saida.append(f"{ano:04d}{mes:02d}")
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    return saida


def mandato_do_mes(ym: str, mandatos: List[Dict[str, Any]]) -> Optional[str]:
    """Mandato vigente no 1º dia do mês (usa as datas de `presidentes_historico.json`)."""
    dia = f"{ym[:4]}-{ym[4:]}-01"
    for m in mandatos:
        if m["data_inicio"] <= dia < m["data_fim"]:
            return m["id_referencia"]
    return None


def agregar_zip(conteudo: bytes) -> Dict[Tuple[str, str], float]:
    """Soma VALOR TRANSFERIDO por (UF, área) de um zip mensal. Linhas sem UF válida são descartadas."""
    totais: Dict[Tuple[str, str], float] = defaultdict(float)
    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        nome = zf.namelist()[0]
        with zf.open(nome) as bruto:
            texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
            leitor = csv.DictReader(texto, delimiter=";")
            for linha in leitor:
                uf = (linha.get(COL_UF) or "").strip().upper()
                if uf not in NOME_POR_UF:
                    continue
                valor = (linha.get(COL_VALOR) or "").strip().replace(".", "").replace(",", ".")
                try:
                    v = float(valor)
                except ValueError:
                    continue
                totais[(uf, area_tematica(linha.get(COL_TIPO, ""), linha.get(COL_FUNCAO, "")))] += v
    return dict(totais)


class TransferenciasExtractor:
    """Baixa os CSVs mensais, agrega por mandato/UF/área e grava `repasses_federais_uf.{json,csv}`."""

    def __init__(
        self,
        output_dir: Path = PROCESSED_DATA_DIR,
        raw_dir: Path = RAW_DATA_DIR / "transferencias",
        http: Optional[HttpClient] = None,
        sidra: Optional[SidraClient] = None,
        hoje: Optional[date] = None,
        sleep=time.sleep,
    ):
        self.output_dir = Path(output_dir)
        self.raw_dir = Path(raw_dir)
        # O WAF do portal responde 405 a rajadas de requisições: intervalo generoso entre downloads.
        self.http = http or HttpClient(timeout=180.0, max_retries=4, min_interval=2.0)
        self.sidra = sidra or SidraClient()
        self.hoje = hoje or date.today()
        self._sleep = sleep
        self.meses_faltantes: List[str] = []

    # ------------------------------------------------------------------ download
    def _arquivo(self, ym: str) -> Path:
        return self.raw_dir / f"{ym}_Transferencias.zip"

    def _recente(self, ym: str) -> bool:
        """Os 3 últimos meses ainda são revisados pelo portal: são rebaixados a cada execução."""
        ano, mes = int(ym[:4]), int(ym[4:])
        meses_atras = (self.hoje.year - ano) * 12 + (self.hoje.month - mes)
        return meses_atras <= 2

    def baixar_mes(self, ym: str, use_cache: bool = True) -> Optional[bytes]:
        arquivo = self._arquivo(ym)
        if use_cache and arquivo.exists() and not self._recente(ym):
            return arquivo.read_bytes()
        conteudo = self._baixar_com_espera(ym)
        if conteudo is None:
            if arquivo.exists():
                logger.warning("Falha ao atualizar %s: usando o arquivo em cache.", ym)
                return arquivo.read_bytes()
            return None
        atomic_write_bytes(arquivo, conteudo)
        return conteudo

    def _baixar_com_espera(self, ym: str) -> Optional[bytes]:
        """GET do mês. Status 405 (bloqueio temporário do WAF) é retentado com espera longa e crescente."""
        for tentativa in range(MAX_TENTATIVAS_BLOQUEIO):
            try:
                conteudo = self.http.get_bytes(URL_MES.format(ym=ym))
            except HttpError as exc:
                if exc.status == 405 and tentativa < MAX_TENTATIVAS_BLOQUEIO - 1:
                    espera = min(ESPERA_BLOQUEIO_S * 2**tentativa, ESPERA_MAXIMA_S)
                    logger.warning("Portal bloqueou temporariamente (405) em %s; aguardando %ds...", ym, espera)
                    self._sleep(espera)
                    continue
                logger.warning("Mês %s indisponível no portal: %s", ym, exc)
                return None
            if not zipfile.is_zipfile(io.BytesIO(conteudo)):
                logger.warning("Mês %s não retornou um ZIP válido; ignorado.", ym)
                return None
            return conteudo
        return None

    # ------------------------------------------------------------------ agregação
    def agregar(
        self, ano_inicio: int = PRIMEIRO_MES_DISPONIVEL[0], use_cache: bool = True
    ) -> Tuple[Dict[Tuple[str, str, str], float], Dict[str, Dict[str, Any]]]:
        """Devolve ({(mandato, uf, área): valor}, {mandato: {meses, inicio, fim}})."""
        mandatos = load_json(PROCESSED_DATA_DIR / "presidentes_historico.json", []) or []
        if not mandatos:
            raise RuntimeError("presidentes_historico.json ausente: rode a etapa --economic antes de --orcamento.")
        inicio = max((ano_inicio, 1), PRIMEIRO_MES_DISPONIVEL)
        fim = (self.hoje.year, self.hoje.month)
        totais: Dict[Tuple[str, str, str], float] = defaultdict(float)
        cobertura: Dict[str, Dict[str, Any]] = {}
        self.meses_faltantes = []
        for ym in meses_no_intervalo(inicio, fim):
            conteudo = self.baixar_mes(ym, use_cache=use_cache)
            if conteudo is None:
                self.meses_faltantes.append(ym)
                continue
            mandato = mandato_do_mes(ym, mandatos)
            if mandato is None:
                continue
            for (uf, area), valor in agregar_zip(conteudo).items():
                totais[(mandato, uf, area)] += valor
            c = cobertura.setdefault(mandato, {"meses": 0, "inicio": ym, "fim": ym})
            c["meses"] += 1
            c["inicio"] = min(c["inicio"], ym)
            c["fim"] = max(c["fim"], ym)
        return dict(totais), cobertura

    def montar_registros(
        self, totais: Dict[Tuple[str, str, str], float], cobertura: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        pop = populacao_uf(self.sidra)
        registros: List[Dict[str, Any]] = []
        for (mandato, uf, area), valor in sorted(totais.items()):
            cob = cobertura[mandato]
            ano_fim = int(cob["fim"][:4])
            habitantes = populacao_no_ano(pop.get(uf, {}), ano_fim)
            meses_mandato = self._meses_decorridos(mandato)
            registro = {
                "mandato_id_ref": mandato,
                "ano": ano_fim,
                "uf": uf,
                "estado_nome": NOME_POR_UF[uf],
                "regiao": REGIAO_POR_UF[uf],
                "area_tematica": area,
                "valor_pago_brl": round(valor, 2),
                "populacao_estimada": habitantes,
                "valor_per_capita_brl": round(valor / habitantes, 2) if habitantes else None,
                "populacao_referencia": ano_fim,
                "periodo_inicio": f"{cob['inicio'][:4]}-{cob['inicio'][4:]}",
                "periodo_fim": f"{cob['fim'][:4]}-{cob['fim'][4:]}",
                "meses_cobertos": cob["meses"],
                "parcial": cob["meses"] < meses_mandato,
                "metodologia": METODOLOGIA,
            }
            registros.append(mark_official(registro, FONTE))
        return registros

    def _tolerado(self, ym: str) -> bool:
        ano, mes = int(ym[:4]), int(ym[4:])
        meses_atras = (self.hoje.year - ano) * 12 + (self.hoje.month - mes)
        return meses_atras < MESES_TOLERADOS_SEM_PUBLICACAO

    def _meses_decorridos(self, mandato: str) -> int:
        """Quantos meses do mandato já ocorreram até hoje (para sinalizar cobertura parcial do portal)."""
        mandatos = load_json(PROCESSED_DATA_DIR / "presidentes_historico.json", []) or []
        meses = meses_no_intervalo((1992, 1), (self.hoje.year, self.hoje.month))
        return sum(1 for ym in meses if mandato_do_mes(ym, mandatos) == mandato)

    # ------------------------------------------------------------------ execução
    def run(self, ano_inicio: int = PRIMEIRO_MES_DISPONIVEL[0], use_cache: bool = True) -> Dict[str, Any]:
        logger.info("Extraindo transferências da União (Portal da Transparência) por UF...")
        totais, cobertura = self.agregar(ano_inicio=ano_inicio, use_cache=use_cache)
        if not totais:
            logger.error("Nenhuma transferência obtida: arquivos anteriores preservados.")
            return {"total_registros": 0, "json_path": None, "gerado": False}
        # Meses faltantes antigos deixariam o total de um mandato subestimado SEM aviso: não grava.
        graves = [ym for ym in self.meses_faltantes if not self._recente(ym) or not self._tolerado(ym)]
        if graves:
            logger.error(
                "Transferências incompletas (%d meses sem download: %s...). Arquivos anteriores preservados; "
                "reexecute (os meses já baixados ficam em cache).",
                len(graves),
                ", ".join(graves[:6]),
            )
            return {"total_registros": 0, "json_path": None, "gerado": False, "meses_faltantes": graves}
        registros = self.montar_registros(totais, cobertura)
        json_path = self.output_dir / "repasses_federais_uf.json"
        csv_path = self.output_dir / "repasses_federais_uf.csv"
        atomic_write_json(json_path, registros)
        atomic_write_text(csv_path, pd.DataFrame(registros).to_csv(index=False))
        logger.info("-> %d registros (mandato × UF × área) em %s", len(registros), json_path)
        return {
            "total_registros": len(registros),
            "json_path": str(json_path),
            "gerado": True,
            "cobertura": cobertura,
        }
