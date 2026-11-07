"""Câmara: histórico de mandatos por deputado (eventos da API) e proposições com autores (CSV anuais)."""

import csv
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from etl.carga.base import Resultado, contagem_de, criar_rejeitos, executar_sql, ler_rejeitos, tabela_temporaria
from etl.utils.copia import contar_linhas_csv

logger = logging.getLogger("CargaCamara")
csv.field_size_limit(sys.maxsize)

COLUNAS_EVENTO = [
    "id", "uri", "nome", "nomeEleitoral", "siglaPartido", "uriPartido", "siglaUf", "idLegislatura", "email", "urlFoto",
    "dataHora", "situacao", "condicaoEleitoral", "descricaoStatus",
]  # fmt: skip
OBRIGATORIAS_PROPOSICAO = (
    "id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao", "urlInteiroTeor",
    "ultimoStatus_descricaoSituacao", "ultimoStatus_dataHora",
)  # fmt: skip
OBRIGATORIAS_AUTOR = (
    "idProposicao", "idDeputadoAutor", "tipoAutor", "nomeAutor", "siglaPartidoAutor", "siglaUFAutor", "ordemAssinatura",
    "proponente",
)  # fmt: skip


def carregar_historico(cursor: Any, raw_dir: Path) -> Resultado:
    """Eventos baixados por `CamaraHistoricoExtractor` (`raw/camara_historico/*.json` + `_legislaturas.json`)."""
    raw_dir = Path(raw_dir)
    legislaturas = json.loads((raw_dir / "_legislaturas.json").read_text(encoding="utf-8"))
    eventos: List[Dict[str, Any]] = []
    for caminho in sorted(raw_dir.glob("[0-9]*.json")):
        eventos.extend(json.loads(caminho.read_text(encoding="utf-8")))
    return carregar_eventos(cursor, eventos, legislaturas)


def carregar_eventos(cursor: Any, eventos: List[Dict[str, Any]], legislaturas: List[Dict[str, Any]]) -> Resultado:
    """Os eventos de posse, saída, licença e troca de partido de cada deputado e as legislaturas que os delimitam."""
    criar_rejeitos(cursor)
    tabela_temporaria(
        cursor,
        "_in_historico",
        {c: "text" for c in COLUNAS_EVENTO},
        ([e.get(c) for c in COLUNAS_EVENTO] for e in eventos),
    )
    tabela_temporaria(
        cursor,
        "_in_legislatura",
        {"id": "text", "dataInicio": "text", "dataFim": "text"},
        ([str(leg["id"]), leg["dataInicio"], leg["dataFim"]] for leg in legislaturas),
    )
    executar_sql(cursor, "camara_historico")
    return Resultado(contagem_de(len(eventos), ler_rejeitos(cursor)), extras={"eventos": len(eventos)})


def _copiar_csv(cursor: Any, tabela: str, arquivos: Sequence[Path], obrigatorias: Iterable[str]) -> int:
    """
    Copia CSVs anuais (mesmo cabeçalho) para uma tabela temporária de texto puro. Falta de coluna obrigatória é layout
    mudado na fonte: a carga para em vez de gravar coluna trocada. Devolve as linhas de dados lidas dos arquivos.
    """
    cabecalho: Optional[List[str]] = None
    lidas = 0
    for caminho in arquivos:
        with open(caminho, encoding="utf-8-sig", newline="") as arquivo:
            atual = next(csv.reader(arquivo, delimiter=";"), [])
        faltam = [c for c in obrigatorias if c not in atual]
        if faltam:
            raise ValueError(f"Cabeçalho inesperado em {caminho.name}: faltam {faltam}; o layout da fonte mudou.")
        if cabecalho is None:
            cabecalho = atual
            cursor.execute(
                f"CREATE TEMP TABLE {tabela} ("  # nosec B608 - nomes constantes dos módulos
                + ", ".join('"' + c.replace('"', '""') + '" text' for c in cabecalho)
                + ") ON COMMIT DROP"
            )
        elif atual != cabecalho:
            raise ValueError(f"{caminho.name} tem colunas diferentes dos outros arquivos do mesmo recurso.")
        lista = ", ".join('"' + c.replace('"', '""') + '"' for c in cabecalho)
        lidas += contar_linhas_csv(caminho)
        with open(caminho, "rb") as conteudo:
            cursor.copy_expert(
                f"COPY {tabela} ({lista}) FROM STDIN WITH (FORMAT csv, DELIMITER ';', QUOTE '\"', HEADER true, ENCODING 'UTF8')",
                conteudo,
            )
    if cabecalho is not None:
        cursor.execute(f"ANALYZE {tabela}")  # nosec B608
    if cabecalho is None:
        cursor.execute(
            f"CREATE TEMP TABLE {tabela} (" + ", ".join(f'"{c}" text' for c in obrigatorias) + ") ON COMMIT DROP"
        )
    return lidas


def carregar_lote(cursor: Any, proposicoes: Sequence[Path], autores: Sequence[Path], execucao_id: int = 0) -> Resultado:
    """Proposições e autores dos CSV anuais (`dadosabertos.camara.leg.br/arquivos/`)."""
    criar_rejeitos(cursor)
    tabela_temporaria(cursor, "_ctx", {"execucao_id": "bigint"}, [[execucao_id]])
    lidas = _copiar_csv(cursor, "_in_camara_proposicao", proposicoes, OBRIGATORIAS_PROPOSICAO)
    lidas_autores = _copiar_csv(cursor, "_in_camara_autor", autores, OBRIGATORIAS_AUTOR)
    cursor.execute(
        'SELECT "siglaTipo", count(*) FROM _in_camara_proposicao '
        'WHERE "siglaTipo" NOT IN (SELECT codigo FROM ref.tipo_proposicao) GROUP BY 1 ORDER BY 1'
    )
    fora_do_escopo = {tipo: int(n) for tipo, n in cursor.fetchall()}
    executar_sql(cursor, "camara_lote")
    return Resultado(
        contagem_de(lidas + lidas_autores, ler_rejeitos(cursor)),
        ate=date.today(),
        extras={"proposicoes_lidas": lidas, "autores_lidos": lidas_autores, "fora_de_escopo_por_tipo": fora_do_escopo},
    )
