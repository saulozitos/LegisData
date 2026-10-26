"""
Extrator de declarações de patrimônio (bens de candidatos) a partir dos dados abertos oficiais do TSE.

Fontes por ano de eleição (cdn.tse.jus.br/estatistica/sead/odsele):
- `bem_candidato/bem_candidato_{ano}.zip`  — um registro por bem declarado (tipo, descrição, valor);
- `consulta_cand/consulta_cand_{ano}.zip`  — candidatos (nome, UF, nascimento, CPF) para ligar `SQ_CANDIDATO`.

O vínculo com os políticos da base usa CPF, nascimento e nome EXATO (ver `tse_core.casar_candidatos`); não há
mais valores digitados à mão nem gerados por hash do nome. Anos sem arquivo no TSE (ex.: 2002) ficam sem
registro — a lacuna é do dado público, não é preenchida.
"""

import logging
from collections import defaultdict
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
    ler_csv_zip,
    parse_brl,
)
from etl.utils.io_utils import write_json_if_valid
from etl.utils.provenance import mark_official

logger = logging.getLogger("TSEPatrimonioExtractor")

# Eleições com bens declarados disponíveis no TSE (2002 não tem arquivo `bem_candidato`).
ANOS_PADRAO = (2006, 2010, 2014, 2018, 2022, 2024)
BEM_COLUNAS = {"SG_UE", "SQ_CANDIDATO", "VR_BEM_CANDIDATO", "DS_TIPO_BEM_CANDIDATO", "DS_BEM_CANDIDATO"}
TOP_TIPOS = 6


def _moeda(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resumir_bens(por_tipo: Dict[str, float], quantidade: int) -> str:
    """'Casa (R$ 1.000,00); Veículo (R$ 50.000,00) … — N bens declarados', do maior valor para o menor."""
    ordenados = sorted(por_tipo.items(), key=lambda kv: kv[1], reverse=True)
    partes = [f"{tipo.capitalize()} ({_moeda(v)})" for tipo, v in ordenados[:TOP_TIPOS]]
    restante = len(ordenados) - TOP_TIPOS
    if restante > 0:
        partes.append(f"outros {restante} tipos")
    return "; ".join(partes) + f" — {quantidade} bens declarados"


def agregar_bens(bem_zip: Path, chaves: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Soma e agrupa por tipo os bens dos candidatos `chaves` (formato `SG_UE|SQ_CANDIDATO`)."""
    alvo = set(chaves)
    totais: Dict[str, float] = defaultdict(float)
    quantidades: Dict[str, int] = defaultdict(int)
    tipos: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for bloco in ler_csv_zip(bem_zip, usecols=lambda c: c in BEM_COLUNAS):
        bloco = bloco.assign(_key=bloco["SG_UE"].astype(str) + "|" + bloco["SQ_CANDIDATO"].astype(str))
        bloco = bloco[bloco["_key"].isin(alvo)]
        for key, tipo, valor in zip(bloco["_key"], bloco["DS_TIPO_BEM_CANDIDATO"], bloco["VR_BEM_CANDIDATO"]):
            numero = parse_brl(valor)
            if numero is None or numero < 0:
                continue
            totais[key] += numero
            quantidades[key] += 1
            tipos[key][str(tipo or "Outros bens").strip() or "Outros bens"] += numero
    return {
        key: {"total": round(totais[key], 2), "quantidade": quantidades[key], "por_tipo": dict(tipos[key])}
        for key in quantidades
    }


class TSEPatrimonioExtractor:
    """Consolida as declarações de bens ao TSE dos parlamentares e presidentes da base."""

    def __init__(self, processed_dir: Path = PROCESSED_DATA_DIR, raw_dir: Path = TSE_RAW_DIR):
        self.data_dir = processed_dir
        self.raw_dir = raw_dir

    def _ano(self, ano: int, universo: Sequence[Politico], force: bool) -> List[Dict[str, Any]]:
        cand_zip = baixar("consulta_cand", f"consulta_cand_{ano}.zip", self.raw_dir, force)
        bem_zip = baixar("bem_candidato", f"bem_candidato_{ano}.zip", self.raw_dir, force)
        if not cand_zip or not bem_zip:
            logger.warning("Eleição %s sem arquivos completos no TSE: ignorada.", ano)
            return []

        candidatos = ler_candidatos(cand_zip)
        casamento = casar_candidatos(universo, candidatos)
        chaves = {candidatos.at[i, "cand_key"] for i in casamento.casados.values()}
        bens = agregar_bens(bem_zip, chaves)
        logger.info(
            "[%s] %d candidatos; %d políticos casados (%d ambíguos); %d com bens declarados.",
            ano,
            len(candidatos),
            len(casamento.casados),
            casamento.ambiguos,
            len(bens),
        )

        por_chave = {p.chave: p for p in universo}
        origem = f"{fonte('bem_candidato', f'bem_candidato_{ano}.zip')} + consulta_cand/consulta_cand_{ano}.zip"
        registros: List[Dict[str, Any]] = []
        for chave, idx in casamento.casados.items():
            resumo = bens.get(candidatos.at[idx, "cand_key"])
            if not resumo:
                continue  # candidato sem bens declarados no arquivo: não há dado, não há registro
            politico = por_chave[chave]
            registros.append(
                mark_official(
                    {
                        **politico.identificadores(),
                        "ano_eleicao": ano,
                        "valor_declarado_brl": resumo["total"],
                        "detalhes_bens": resumir_bens(resumo["por_tipo"], resumo["quantidade"]),
                        "quantidade_bens": resumo["quantidade"],
                        "cargo_disputado": str(candidatos.at[idx, "DS_CARGO"]).title(),
                        "uf_candidatura": candidatos.at[idx, "SG_UF"],
                        "criterio_vinculo": casamento.motivo[chave],
                    },
                    origem,
                )
            )
        return registros

    def run(
        self,
        anos: Optional[Iterable[int]] = None,
        universo: Optional[Sequence[Politico]] = None,
        force: bool = False,
        **_ignorado: Any,
    ) -> List[Dict[str, Any]]:
        logger.info("Extraindo declarações de patrimônio dos dados abertos do TSE...")
        universo = universo if universo is not None else carregar_universo(self.data_dir)
        declaracoes: List[Dict[str, Any]] = []
        for ano in anos or ANOS_PADRAO:
            declaracoes.extend(self._ano(int(ano), universo, force))
        declaracoes.sort(key=lambda r: (r["nome_eleitoral"], r["ano_eleicao"]))

        output_file = self.data_dir / "declaracoes_patrimonio.json"
        if write_json_if_valid(output_file, declaracoes):
            logger.info("Sucesso: %d declarações de patrimônio salvas em %s.", len(declaracoes), output_file)
        else:
            logger.warning("Nenhuma declaração obtida: %s preservado.", output_file.name)
        return declaracoes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    TSEPatrimonioExtractor().run()
