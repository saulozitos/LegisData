"""
Situação do registro de candidatura dos parlamentares e presidentes da base (consulta_cand do TSE).

É o único dado de "ficha limpa" verificável em fonte aberta e oficial: o TSE publica se o registro foi deferido
ou se foi indeferido/cancelado/cassado. Registro DEFERIDO não prova "nada consta" em todos os tribunais, então
NÃO gera registro (o status continua desconhecido). Só entram ocorrências adversas, descritas exatamente como o
TSE as publica. Não há fonte aberta unificada de processos judiciais (DataJud/CNJ exige chave de acesso).
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.tse_core import (
    TSE_RAW_DIR,
    Politico,
    baixar,
    carregar_universo,
    casar_candidatos,
    fonte,
    ler_candidatos,
)
from etl.utils.io_utils import write_json_if_valid
from etl.utils.provenance import mark_official

logger = logging.getLogger("TSECandidaturasExtractor")

ANOS_PADRAO = (2002, 2006, 2010, 2014, 2018, 2022, 2024)
SAIDA = "certidoes_tse.json"
ORGAO = "TSE"
TIPO = "Registro de candidatura"
# Situações que o TSE publica e que indicam registro NEGADO/CANCELADO/CASSADO (renúncia e falecimento não entram)
ADVERSAS = (
    ("INDEFERID", "indeferido"),
    ("REGISTRO NEGADO", "indeferido"),
    ("CASSAD", "cassado"),
    ("CANCELAD", "cancelado"),
)
NULOS = {"", "#NULO", "#NULO#", "#NE", "-1", "-3"}


def _limpo(valor: Any) -> str:
    texto = str(valor if valor is not None else "").strip()
    return "" if texto in NULOS else texto


def classificar(detalhe: str, situacao_total: str, situacao: str) -> Optional[str]:
    """'indeferido' | 'cancelado' | 'cassado' quando o TSE registra isso; None caso contrário."""
    campos = " | ".join(c.upper() for c in (detalhe, situacao_total, situacao) if c)
    for trecho, rotulo in ADVERSAS:
        if re.search(trecho, campos):
            return rotulo
    return None


class TSECandidaturasExtractor:
    def __init__(self, processed_dir: Path = PROCESSED_DATA_DIR, raw_dir: Path = TSE_RAW_DIR):
        self.processed_dir = Path(processed_dir)
        self.raw_dir = Path(raw_dir)

    def _ano(self, ano: int, universo: Sequence[Politico], force: bool) -> List[Dict[str, Any]]:
        cand_zip = baixar("consulta_cand", f"consulta_cand_{ano}.zip", self.raw_dir, force)
        if not cand_zip:
            return []
        candidatos = ler_candidatos(cand_zip)
        casamento = casar_candidatos(universo, candidatos)
        por_chave = {p.chave: p for p in universo}
        origem = fonte("consulta_cand", f"consulta_cand_{ano}.zip")
        registros: List[Dict[str, Any]] = []
        for chave, idx in casamento.casados.items():
            row = candidatos.iloc[idx]
            situacao = _limpo(row["DS_SITUACAO_CANDIDATURA"])
            detalhe = _limpo(row["DS_DETALHE_SITUACAO_CAND"])
            resultado = _limpo(row["DS_SIT_TOT_TURNO"])
            rotulo = classificar(detalhe, resultado, situacao)
            if not rotulo:
                continue
            cargo = str(row["DS_CARGO"]).title()
            partes = [f"Situação da candidatura: {situacao or 'não informada'}"]
            if detalhe:
                partes.append(f"detalhe: {detalhe}")
            if resultado:
                partes.append(f"resultado: {resultado}")
            registros.append(
                mark_official(
                    {
                        **por_chave[chave].identificadores(),
                        "ano_eleicao": ano,
                        "orgao": ORGAO,
                        "tipo_certidao": f"{TIPO} {ano} - {cargo}",
                        "status_ficha": f"Declarada: registro {rotulo}",
                        "detalhes": f"Eleição {ano}, {cargo} ({row['SG_UF']}). " + "; ".join(partes) + ".",
                        "numero_processo": _limpo(row.get("NR_PROCESSO")) or None,
                    },
                    origem,
                )
            )
        logger.info(
            "[%s] %d ocorrências adversas entre %d políticos casados.", ano, len(registros), len(casamento.casados)
        )
        return registros

    def run(
        self,
        anos: Optional[Iterable[int]] = None,
        universo: Optional[Sequence[Politico]] = None,
        force: bool = False,
        **_ignorado: Any,
    ) -> List[Dict[str, Any]]:
        universo = universo if universo is not None else carregar_universo(self.processed_dir)
        registros: List[Dict[str, Any]] = []
        for ano in anos or ANOS_PADRAO:
            registros.extend(self._ano(int(ano), universo, force))
        registros.sort(key=lambda r: (r["nome_eleitoral"], r["ano_eleicao"]))
        destino = self.processed_dir / SAIDA
        if write_json_if_valid(destino, registros):
            logger.info("%d ocorrências do TSE salvas em %s.", len(registros), destino)
        else:
            logger.warning("Nenhuma ocorrência adversa encontrada: %s preservado.", SAIDA)
        return registros


if __name__ == "__main__":
    TSECandidaturasExtractor().run()
