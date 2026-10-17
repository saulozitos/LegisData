"""
Reconciliação (somente leitura) dos arquivos oficiais do ETL com o schema `fin`.

Compara, por ano, o total que está no arquivo com o total gravado no banco:
- emendas: todas as linhas entram (autor sem pessoa fica com `pessoa_id` nulo), então a diferença esperada é zero;
- CEAP, remuneração e doações: só entra quem tem pessoa em `core`; a diferença é o valor de quem não foi vinculado
  e vem listada com o número de parlamentares/prestações de fora.

Uso: python -m etl.scripts.reconciliar_financas [--json]
Sai com código 1 quando as emendas divergem ou quando um total do banco passa do total do arquivo.
"""

import argparse
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.financas_loader import (
    CEAP_ARQUIVO,
    DOACOES_ARQUIVO,
    EMENDAS_ARQUIVO,
    REMUNERACAO_ARQUIVO,
    ler_emenda,
)
from etl.pipelines.loader_helpers import LIMITE_REMUNERACAO, LIMITE_TSE, decimal_de, inteiro_em
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json
from etl.utils.provenance import is_trusted

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

CENTAVO = Decimal("0.01")


def _soma(destino: Dict[int, Decimal], ano: Optional[int], valor: Optional[Decimal]) -> None:
    if ano is not None and valor is not None:
        destino[ano] += valor


def totais_ceap_do_arquivo(ceap: Any) -> Dict[int, Decimal]:
    totais: Dict[int, Decimal] = defaultdict(Decimal)
    for dados in ceap.values() if isinstance(ceap, dict) else []:
        if not isinstance(dados, dict) or not is_trusted(dados):
            continue
        por_ano_tipo = dados.get("por_ano_tipo")
        for ano, tipos in (por_ano_tipo if isinstance(por_ano_tipo, dict) else {}).items():
            for valor in (tipos if isinstance(tipos, dict) else {}).values():
                _soma(totais, inteiro_em(ano, 1995, 2100), decimal_de(valor))
    return totais


def totais_emendas_do_arquivo(emendas: Any) -> Dict[int, Dict[str, Decimal]]:
    totais: Dict[int, Dict[str, Decimal]] = defaultdict(lambda: {"empenhado": Decimal(0), "pago": Decimal(0)})
    for bruta in emendas if isinstance(emendas, list) else []:
        lida, _motivo = ler_emenda(bruta)  # a mesma regra de elegibilidade do loader
        if lida is None:
            continue
        totais[lida["ano"]]["empenhado"] += lida["empenhado"]
        totais[lida["ano"]]["pago"] += lida["pago"]
    return totais


def totais_remuneracao_do_arquivo(corpo: Any) -> Dict[int, Decimal]:
    totais: Dict[int, Decimal] = defaultdict(Decimal)
    registros = corpo.get("registros") if isinstance(corpo, dict) else None
    for r in registros if isinstance(registros, list) else []:
        if not isinstance(r, dict):
            continue
        _soma(totais, inteiro_em(r.get("ano"), 1995, 2100), decimal_de(r.get("salario_bruto"), LIMITE_REMUNERACAO))
    return totais


def totais_doacoes_do_arquivo(prestacoes: Any) -> Dict[int, Decimal]:
    totais: Dict[int, Decimal] = defaultdict(Decimal)
    for item in prestacoes if isinstance(prestacoes, list) else []:
        if not isinstance(item, dict) or not is_trusted(item):
            continue
        ano = inteiro_em(item.get("ano_eleicao"), 1995, 2100)
        doadores = item.get("doadores")
        for doador in doadores if isinstance(doadores, list) else []:
            _soma(totais, ano, decimal_de(doador.get("valor_doado"), LIMITE_TSE) if isinstance(doador, dict) else None)
    return totais


def _banco(conn: Connection, sql: str) -> Dict[int, Decimal]:
    return {int(ano): Decimal(valor) for ano, valor in conn.execute(text(sql))}


def comparar(arquivo: Dict[int, Decimal], banco: Dict[int, Decimal]) -> List[Dict[str, Any]]:
    """Uma linha por ano: total no arquivo, total no banco e a diferença (arquivo - banco)."""
    linhas = []
    for ano in sorted(set(arquivo) | set(banco)):
        a, b = arquivo.get(ano, Decimal(0)).quantize(CENTAVO), banco.get(ano, Decimal(0)).quantize(CENTAVO)
        linhas.append({"ano": ano, "arquivo": a, "banco": b, "diferenca": a - b})
    return linhas


def reconciliar(conn: Connection, pasta: Path) -> Dict[str, Any]:
    emendas = totais_emendas_do_arquivo(load_json(pasta / EMENDAS_ARQUIVO, []))
    relatorio: Dict[str, Any] = {
        "emendas_empenhado": comparar(
            {a: t["empenhado"] for a, t in emendas.items()},
            _banco(conn, "SELECT ano, sum(valor_empenhado) FROM fin.emenda GROUP BY ano"),
        ),
        "emendas_pago": comparar(
            {a: t["pago"] for a, t in emendas.items()},
            _banco(conn, "SELECT ano, sum(valor_pago) FROM fin.emenda GROUP BY ano"),
        ),
        "ceap": comparar(
            totais_ceap_do_arquivo(load_json(pasta / CEAP_ARQUIVO, {})),
            _banco(conn, "SELECT ano, sum(valor_liquido) FROM fin.despesa_cota GROUP BY ano"),
        ),
        "remuneracao_bruta": comparar(
            totais_remuneracao_do_arquivo(load_json(pasta / REMUNERACAO_ARQUIVO, {})),
            _banco(conn, "SELECT ano, sum(salario_bruto) FROM fin.remuneracao GROUP BY ano"),
        ),
        "doacoes": comparar(
            totais_doacoes_do_arquivo(load_json(pasta / DOACOES_ARQUIVO, [])),
            _banco(conn, "SELECT ano_eleicao, sum(valor) FROM fin.doacao_campanha GROUP BY ano_eleicao"),
        ),
    }
    relatorio["emendas_sem_pessoa"] = {
        situacao: n
        for situacao, n in conn.execute(
            text("SELECT autor_situacao, count(*) FROM fin.emenda GROUP BY autor_situacao ORDER BY 1")
        )
    }
    return relatorio


def divergencias(relatorio: Dict[str, Any]) -> List[str]:
    """Problemas que a reconciliação não explica: emendas diferentes do arquivo ou banco com mais do que o arquivo."""
    problemas = []
    for chave in ("emendas_empenhado", "emendas_pago"):
        problemas += [
            f"{chave} {linha['ano']}: diferença de {linha['diferenca']}"
            for linha in relatorio[chave]
            if linha["diferenca"]
        ]
    for chave in ("ceap", "remuneracao_bruta", "doacoes"):
        problemas += [
            f"{chave} {linha['ano']}: banco acima do arquivo ({linha['diferenca']})"
            for linha in relatorio[chave]
            if linha["diferenca"] < 0
        ]
    return problemas


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcilia os arquivos oficiais com o schema fin.")
    parser.add_argument("--json", action="store_true", help="Saída em JSON")
    args = parser.parse_args(argv)

    from app.core.database import engine

    with engine.connect() as conn:
        relatorio = reconciliar(conn, Path(PROCESSED_DATA_DIR))
    problemas = divergencias(relatorio)
    if args.json:
        print(json.dumps({**relatorio, "problemas": problemas}, default=str, ensure_ascii=False, indent=2))
    else:
        for nome, linhas in relatorio.items():
            if nome == "emendas_sem_pessoa":
                print(f"\n{nome}: {linhas}")
                continue
            print(f"\n{nome}")
            for linha in linhas:
                print(
                    f"  {linha['ano']}  arquivo {linha['arquivo']:>20}  banco {linha['banco']:>20}  diferença {linha['diferenca']:>18}"
                )
        print("\n" + ("OK" if not problemas else "DIVERGÊNCIAS:\n  " + "\n  ".join(problemas)))
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
