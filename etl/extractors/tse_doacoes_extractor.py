"""
Extrator de financiamento de campanha (receitas de candidatos) a partir da prestação de contas oficial do TSE.

Cada ano tem um layout próprio nos dados abertos; `LAYOUTS` mapeia os arquivos e as colunas de 2002 a 2022
para um formato único. Para cada político da base casado com um candidato (ver `tse_core.casar_candidatos`) são
gravados os maiores doadores e uma linha agregada "Demais doadores", de modo que a soma das linhas é o total
arrecadado. CPF de doador pessoa física é gravado MASCARADO (`***.123.456-**`); CNPJ é público.
Eleições municipais (2020/2024) não são carregadas: os arquivos têm mais de 1 GB e não envolvem os cargos
federais tratados pelo projeto.
"""

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd

from etl.config import PROCESSED_DATA_DIR
from etl.extractors.tse_core import (
    TSE_RAW_DIR,
    Politico,
    baixar,
    carregar_universo,
    casar_candidatos,
    fonte,
    ler_candidatos,
    ler_csv_zip,
    parse_brl,
)
from etl.utils.io_utils import write_json_if_valid
from etl.utils.provenance import mark_official

logger = logging.getLogger("TseDoacoesExtractor")

TOP_DOADORES = 20
SAIDA = "tse_doacoes_campanha.json"

# ano -> (dataset, arquivo, regex dos membros, colunas de origem -> colunas normalizadas)
LAYOUTS: Dict[int, Dict[str, Any]] = {
    2002: {
        "arquivo": "prestacao_contas_2002.zip",
        "membros": r"Candidato/Receita/ReceitaCandidato\.csv$",
        "cols": {
            "SEQUENCIAL_CANDIDATO": "sq",
            "SG_UF": "uf",
            "CD_CPF_CGC": "doc",
            "NO_DOADOR": "nome",
            "VR_RECEITA": "valor",
            "TP_RECURSO": "origem",
        },
    },
    2006: {
        "arquivo": "prestacao_contas_2006.zip",
        "membros": r"Candidato/Receita/ReceitaCandidato\.csv$",
        "cols": {
            "SEQUENCIAL_CANDIDATO": "sq",
            "UNIDADE_ELEITORAL_CANDIDATO": "uf",
            "NUMERO_CPF_CGC_DOADOR": "doc",
            "NOME_DOADOR": "nome",
            "VALOR_RECEITA": "valor",
            "TIPO_RECEITA": "origem",
        },
    },
    2010: {
        "arquivo": "prestacao_contas_2010.zip",
        "membros": r"candidato/[A-Z]{2}/ReceitasCandidatos\.txt$",
        "cols": {
            "Sequencial Candidato": "sq",
            "UF": "uf",
            "CPF/CNPJ do doador": "doc",
            "Nome do doador": "nome",
            "Valor receita": "valor",
            "Tipo receita": "origem",
        },
    },
    2014: {
        "arquivo": "prestacao_final_2014.zip",
        "membros": r"receitas_candidatos_2014_[A-Z]{2}\.txt$",
        "cols": {
            "Sequencial Candidato": "sq",
            "UF": "uf",
            "CPF/CNPJ do doador": "doc",
            "Nome do doador": "nome",
            "Valor receita": "valor",
            "Tipo receita": "origem",
        },
    },
    2018: {
        "arquivo": "prestacao_de_contas_eleitorais_candidatos_2018.zip",
        "membros": r"receitas_candidatos_2018_[A-Z]{2}\.csv$",
        "cols": {
            "SQ_CANDIDATO": "sq",
            "SG_UE": "uf",
            "NR_CPF_CNPJ_DOADOR": "doc",
            "NM_DOADOR": "nome",
            "VR_RECEITA": "valor",
            "DS_ORIGEM_RECEITA": "origem",
        },
    },
    2022: {
        "arquivo": "prestacao_de_contas_eleitorais_candidatos_2022.zip",
        "membros": r"receitas_candidatos_2022_[A-Z]{2}\.csv$",
        "cols": {
            "SQ_CANDIDATO": "sq",
            "SG_UE": "uf",
            "NR_CPF_CNPJ_DOADOR": "doc",
            "NM_DOADOR": "nome",
            "VR_RECEITA": "valor",
            "DS_ORIGEM_RECEITA": "origem",
        },
    },
}
ANOS_PADRAO = tuple(sorted(LAYOUTS))
NULOS = {"", "#NULO", "#NULO#", "#NE", "-1", "-3", "-4"}


def mascarar_documento(valor: Any) -> Optional[str]:
    """CPF (11 dígitos) -> '***.123.456-**'; CNPJ (14) fica íntegro; qualquer outro formato é descartado."""
    texto = str(valor if valor is not None else "").strip()
    if texto in NULOS:
        return None
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) == 11:
        return f"***.{digitos[3:6]}.{digitos[6:9]}-**"
    if len(digitos) == 14:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"
    return None


def _limpo(valor: Any) -> str:
    texto = str(valor if valor is not None else "").strip()
    return "" if texto in NULOS else texto


def ler_receitas(zip_path: Path, layout: Dict[str, Any]) -> Iterable[pd.DataFrame]:
    """Blocos normalizados (colunas sq, uf, doc, nome, valor, origem) das receitas de candidatos do ano."""
    mapa = layout["cols"]
    for bloco in ler_csv_zip(zip_path, membros=layout["membros"], usecols=lambda c: c in mapa):
        bloco = bloco.rename(columns=mapa)
        for coluna in mapa.values():
            if coluna not in bloco.columns:
                bloco[coluna] = ""
        yield bloco[list(mapa.values())]


def agregar_receitas(
    blocos: Iterable[pd.DataFrame], chaves_por_sq: Dict[str, str], chaves_por_uf_sq: Dict[str, str]
) -> Dict[str, Dict[str, Any]]:
    """
    Soma receitas por candidato casado. Liga a receita ao candidato por `UF|SQ` (ou só `SQ` quando o sequencial
    é único no ano). Devolve {cand_key: {total, quantidade, doadores: {(doc, nome, origem): valor}}}.
    """
    resultado: Dict[str, Dict[str, Any]] = {}
    for bloco in blocos:
        for sq, uf, doc, nome, valor, origem in zip(
            bloco["sq"], bloco["uf"], bloco["doc"], bloco["nome"], bloco["valor"], bloco["origem"]
        ):
            key = chaves_por_uf_sq.get(f"{str(uf).strip().upper()}|{str(sq).strip()}") or chaves_por_sq.get(
                str(sq).strip()
            )
            if key is None:
                continue
            numero = parse_brl(valor)
            if numero is None or numero <= 0:
                continue
            item = resultado.setdefault(key, {"total": 0.0, "quantidade": 0, "doadores": defaultdict(float)})
            item["total"] += numero
            item["quantidade"] += 1
            item["doadores"][
                (mascarar_documento(doc), _limpo(nome) or "Doador não identificado", _limpo(origem))
            ] += numero
    return resultado


def linhas_do_candidato(resumo: Dict[str, Any], top: Optional[int] = None) -> List[Dict[str, Any]]:
    """Maiores doadores + linha 'Demais doadores' que preserva o total arrecadado."""
    top = TOP_DOADORES if top is None else top
    ordenados = sorted(resumo["doadores"].items(), key=lambda kv: kv[1], reverse=True)
    linhas = [
        {
            "nome_doador": nome,
            "cpf_cnpj_doador": doc,
            "valor_doado": round(valor, 2),
            "tipo_receita": origem or "Doação eleitoral",
        }
        for (doc, nome, origem), valor in ordenados[:top]
    ]
    restantes = ordenados[top:]
    if restantes:
        linhas.append(
            {
                "nome_doador": f"Demais doadores ({len(restantes)})",
                "cpf_cnpj_doador": None,
                "valor_doado": round(sum(v for _, v in restantes), 2),
                "tipo_receita": "Agregado",
            }
        )
    return linhas


class TseDoacoesExtractor:
    """Receitas de campanha dos parlamentares e presidentes da base (prestação de contas oficial do TSE)."""

    def __init__(self, processed_dir: Path = PROCESSED_DATA_DIR, raw_dir: Path = TSE_RAW_DIR):
        self.processed_dir = Path(processed_dir)
        self.raw_dir = Path(raw_dir)

    def _ano(self, ano: int, universo: Sequence[Politico], force: bool) -> List[Dict[str, Any]]:
        layout = LAYOUTS[ano]
        cand_zip = baixar("consulta_cand", f"consulta_cand_{ano}.zip", self.raw_dir, force)
        dataset = "prestacao_contas"
        contas_zip = baixar(dataset, layout["arquivo"], self.raw_dir, force)
        if not cand_zip or not contas_zip:
            logger.warning("Eleição %s sem arquivos completos no TSE: ignorada.", ano)
            return []

        candidatos = ler_candidatos(cand_zip)
        casamento = casar_candidatos(universo, candidatos)
        alvo = {int(i): chave for chave, i in casamento.casados.items()}
        por_uf_sq: Dict[str, str] = {}
        for i in alvo:
            row = candidatos.iloc[i]
            por_uf_sq[f"{row['SG_UE'].upper()}|{row['SQ_CANDIDATO']}"] = row["cand_key"]
        # `SQ` sozinho só quando ele identifica um único candidato do ano inteiro (evita colisão entre UFs)
        todos_sq = candidatos["SQ_CANDIDATO"].astype(str).value_counts()
        por_sq = {
            str(candidatos.iloc[i]["SQ_CANDIDATO"]): candidatos.iloc[i]["cand_key"]
            for i in alvo
            if todos_sq.get(str(candidatos.iloc[i]["SQ_CANDIDATO"]), 0) == 1
        }

        receitas = agregar_receitas(ler_receitas(contas_zip, layout), por_sq, por_uf_sq)
        por_chave = {p.chave: p for p in universo}
        origem = f"{fonte(dataset, layout['arquivo'])} + consulta_cand/consulta_cand_{ano}.zip"
        registros: List[Dict[str, Any]] = []
        for chave, idx in casamento.casados.items():
            resumo = receitas.get(candidatos.at[idx, "cand_key"])
            if not resumo:
                continue
            registros.append(
                mark_official(
                    {
                        **por_chave[chave].identificadores(),
                        "ano_eleicao": ano,
                        "total_arrecadado": round(resumo["total"], 2),
                        "quantidade_receitas": resumo["quantidade"],
                        "doadores": linhas_do_candidato(resumo),
                    },
                    origem,
                )
            )
        logger.info(
            "[%s] %d políticos casados (%d ambíguos); %d com receitas de campanha.",
            ano,
            len(casamento.casados),
            casamento.ambiguos,
            sum(1 for r in registros if r["ano_eleicao"] == ano),
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
        if write_json_if_valid(destino, registros, indent=None):
            logger.info("%d prestações de contas de campanha salvas em %s.", len(registros), destino)
        else:
            logger.warning("Nenhuma receita obtida: %s preservado.", SAIDA)
        return registros


if __name__ == "__main__":
    TseDoacoesExtractor().run()
