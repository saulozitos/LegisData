"""
Extrator e Normalizador de Emendas Parlamentares (Trilha do Dinheiro).

Fonte oficial: Portal da Transparência (download de dados de emendas parlamentares, CSV público).
O gerador sintético abaixo existe apenas para demonstração local e fica DESLIGADO por padrão:
nenhum valor, taxa de execução ou cidade de destino pode ser apresentado como dado oficial.
"""

import io
import logging
import zipfile
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.names import normalize_plain
from etl.utils.provenance import mark_official, mark_synthetic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("EmendasExtractor")

PORTAL_EMENDAS_URL = "https://portaldatransparencia.gov.br/download-de-dados/emendas-parlamentares/UNICO"
FONTE_PORTAL = "Portal da Transparência — Emendas Parlamentares (CSV oficial)"

# Cabeçalhos esperados (comparados já normalizados, sem acento/caixa) -> campo interno
_COLUNAS = {
    "codigo da emenda": "codigo_emenda",
    "ano da emenda": "ano",
    "tipo de emenda": "tipo_emenda",
    "codigo do autor da emenda": "autor_codigo",
    "nome do autor da emenda": "politician_name",
    "localidade de aplicacao do recurso": "localidade_destino",
    "municipio": "municipio",
    "uf": "uf",
    "funcao": "funcao",
    "nome funcao": "funcao",
    "valor empenhado": "valor_empenhado",
    "valor pago": "valor_pago",
}


def parse_brl(valor: Any) -> Optional[float]:
    """'1.234.567,89' -> 1234567.89. Aceita também float/int; vazio -> None."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def parse_emendas_csv(conteudo: bytes, encoding: str = "latin-1") -> List[Dict[str, Any]]:
    """Converte o CSV do Portal em registros oficiais. Linhas sem autor/ano/valor são descartadas."""
    df = pd.read_csv(io.BytesIO(conteudo), sep=";", encoding=encoding, dtype=str, low_memory=False).fillna("")
    renomear = {col: _COLUNAS[normalize_plain(col)] for col in df.columns if normalize_plain(col) in _COLUNAS}
    df = df.rename(columns=renomear)

    obrigatorias = {"ano", "politician_name", "valor_empenhado", "valor_pago"}
    faltando = obrigatorias - set(df.columns)
    if faltando:
        raise ValueError(f"CSV de emendas sem colunas esperadas: {sorted(faltando)}")

    # O CSV tem uma linha por (emenda, localidade, função, programa/ação...). Como o banco guarda (emenda,
    # localidade, função), linhas que diferem só em campos que não guardamos são SOMADAS: assim a chave natural é
    # única, a carga é idempotente e nenhum valor é perdido (antes, duplicatas se sobrescreveriam).
    agregados: Dict[tuple, Dict[str, Any]] = {}
    for row in df.to_dict(orient="records"):
        nome = (row.get("politician_name") or "").strip()
        try:
            ano = int(str(row.get("ano")).strip())
        except (TypeError, ValueError):
            continue
        empenhado = parse_brl(row.get("valor_empenhado"))
        pago = parse_brl(row.get("valor_pago"))
        if not nome or normalize_plain(nome) == "sem informacao" or empenhado is None:
            continue  # emendas sem autor identificado não podem ser atribuídas a ninguém
        codigo = (row.get("codigo_emenda") or "").strip()
        if normalize_plain(codigo) == "sem informacao":
            codigo = ""
        localidade = (row.get("localidade_destino") or row.get("municipio") or "").strip() or "Não informado"
        tipo = (row.get("tipo_emenda") or "").strip() or "NÃO INFORMADO"
        funcao = (row.get("funcao") or "").strip() or None

        chave = (nome, ano, codigo or None, tipo, localidade, funcao)
        if chave in agregados:
            agregados[chave]["valor_empenhado"] += empenhado
            agregados[chave]["valor_pago"] += pago or 0.0
            continue
        agregados[chave] = mark_official(
            {
                "politician_name": nome,
                "autor_codigo": (row.get("autor_codigo") or "").strip() or None,
                "ano": ano,
                "codigo_emenda": codigo or None,
                "tipo_emenda": tipo,
                "valor_empenhado": empenhado,
                "valor_pago": pago if pago is not None else 0.0,
                "localidade_destino": localidade,
                "funcao": funcao,
            },
            FONTE_PORTAL,
        )
    registros = list(agregados.values())
    for r in registros:
        r["valor_empenhado"] = round(r["valor_empenhado"], 2)
        r["valor_pago"] = round(r["valor_pago"], 2)
    return registros


# ---- Gerador SINTÉTICO (desligado por padrão) -------------------------------------------------------------

CIDADES_UF = {
    "RJ": ["Rio de Janeiro/RJ", "Niterói/RJ", "Duque de Caxias/RJ"],
    "SP": ["São Paulo/SP", "Campinas/SP", "Guarulhos/SP"],
    "MG": ["Belo Horizonte/MG", "Uberlândia/MG", "Contagem/MG"],
    "BA": ["Salvador/BA", "Feira de Santana/BA", "Camaçari/BA"],
    "DF": ["Brasília/DF", "Ceilândia/DF", "Taguatinga/DF"],
}
TETOS_ANUAIS = {2023: 32_000_000.0, 2024: 37_500_000.0, 2025: 39_200_000.0}
TAXA_EXECUCAO = {2023: 0.91, 2024: 0.86, 2025: 0.72}
DISTRIBUICAO_AREAS = [
    ("INDIVIDUAL - ESPECIAL (PIX)", "Saúde Pública (Atenção Primária / SUS)", 0.35),
    ("INDIVIDUAL - FINALIDADE DEFINIDA", "Infraestrutura Urbana e Pavimentação", 0.25),
    ("INDIVIDUAL - FINALIDADE DEFINIDA", "Educação Básica e Creches", 0.15),
    ("BANCADA ESTADUAL", "Equipamentos Hospitalares e UTIs", 0.15),
    ("COMISSÃO", "Assistência Social e Segurança Pública", 0.10),
]


def stable_id(*parts: Any) -> int:
    """Identificador determinístico entre execuções (o `hash()` do Python varia com PYTHONHASHSEED)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8")) % 100000


class EmendasExtractor:
    """Obtém emendas parlamentares do Portal da Transparência."""

    def __init__(
        self, raw_dir: Path = RAW_DATA_DIR, processed_dir: Path = PROCESSED_DATA_DIR, http: Optional[HttpClient] = None
    ):
        self.raw_dir = raw_dir
        self.processed_dir = processed_dir
        self.http = http or HttpClient(timeout=120.0, max_retries=3)

    def fetch_portal(self) -> List[Dict[str, Any]]:
        """Baixa e converte o CSV oficial. Falha => lista vazia (quem grava deve preservar o arquivo anterior)."""
        logger.info("Baixando emendas parlamentares do Portal da Transparência...")
        try:
            bruto = self.http.get_bytes(PORTAL_EMENDAS_URL)
            with zipfile.ZipFile(io.BytesIO(bruto)) as zf:
                nome_csv = next(
                    (n for n in zf.namelist() if n.lower().endswith(".csv") and "emenda" in n.lower()), None
                )
                if nome_csv is None:
                    nome_csv = zf.namelist()[0]
                conteudo = zf.read(nome_csv)
            registros = parse_emendas_csv(conteudo)
        except (HttpError, zipfile.BadZipFile, ValueError, IndexError) as exc:
            logger.error("Não foi possível obter emendas do Portal da Transparência: %s", exc)
            return []
        logger.info("%d emendas oficiais obtidas.", len(registros))
        return registros

    def generate_emendas_for_politician(
        self,
        politician_name: str,
        uf: str = "BR",
        camara_id: Optional[int] = None,
        allow_synthetic: bool = False,
    ) -> List[Dict[str, Any]]:
        """Portfólio FICTÍCIO de emendas (demonstração). Retorna [] a menos que `allow_synthetic=True`."""
        if not allow_synthetic:
            return []

        uf_clean = uf if uf and uf != "BR" else "DF"
        cidades = CIDADES_UF.get(uf_clean, [f"Capital/{uf_clean}"])
        ident = camara_id or stable_id(politician_name)

        emendas = []
        for ano, teto in TETOS_ANUAIS.items():
            for idx, (tipo, area, peso) in enumerate(DISTRIBUICAO_AREAS, start=1):
                val_emp = round(teto * peso, 2)
                emendas.append(
                    mark_synthetic(
                        {
                            "politician_name": politician_name,
                            "ano": ano,
                            "codigo_emenda": f"{ano}.{ident}.{idx:04d}",
                            "tipo_emenda": tipo,
                            "valor_empenhado": val_emp,
                            "valor_pago": round(val_emp * TAXA_EXECUCAO.get(ano, 0.8), 2),
                            "localidade_destino": cidades[(idx - 1) % len(cidades)],
                            "funcao": area,
                        }
                    )
                )
        return emendas
