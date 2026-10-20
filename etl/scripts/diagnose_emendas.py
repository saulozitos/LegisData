"""
Diagnóstico das emendas parlamentares sem vínculo com um político da base (somente leitura).

Usa o MESMO critério do `DatabaseLoader._load_emendas_parlamentares` (nome normalizado único entre nomes
eleitorais e civis) e separa o que ficou de fora em:
  - institucional: bancadas estaduais, Relator-Geral, comissões, mesa — não são pessoas e não têm `Politician`;
  - ambiguo: o nome normalizado casa com mais de um político (o loader recusa de propósito);
  - ausente: nenhum político com esse nome (ex-parlamentar não carregado ou grafia diferente).

Uso: python -m etl.scripts.diagnose_emendas [--json]
"""

import argparse
import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json
from etl.utils.names import normalize_name_tokens

ensure_backend_on_path()

INSTITUCIONAL = re.compile(r"^(BANCADA|RELATOR|COMISS|MESA|LIDERAN|BLOCO|CONGRESSO|PODER)\w*", re.IGNORECASE)


def classificar(nome: str, contagem_nomes: Dict[str, int]) -> str:
    if INSTITUCIONAL.match((nome or "").strip()):
        return "institucional"
    chave = normalize_name_tokens(nome)
    if not chave:
        return "ausente"
    return "ambiguo" if contagem_nomes.get(chave, 0) > 1 else "ausente"


def diagnosticar(emendas: Iterable[Dict[str, Any]], nomes_politicos: Iterable[Tuple[Any, str]]) -> Dict[str, Any]:
    """`nomes_politicos`: pares (id do político, nome) — eleitoral e civil. O mesmo nome do mesmo político conta uma vez."""
    ids_por_chave: Dict[str, set] = defaultdict(set)
    for pid, nome in nomes_politicos:
        chave = normalize_name_tokens(nome)
        if chave:
            ids_por_chave[chave].add(pid)
    contagem: Dict[str, int] = {k: len(v) for k, v in ids_por_chave.items()}
    unicos = {k for k, v in contagem.items() if v == 1}

    por_categoria: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"emendas": 0, "valor_empenhado": 0.0, "autores": set()}
    )
    vinculadas = {"emendas": 0, "valor_empenhado": 0.0}
    for e in emendas:
        valor = float(e.get("valor_empenhado") or 0)
        nome = e.get("politician_name") or ""
        if normalize_name_tokens(nome) in unicos:
            vinculadas["emendas"] += 1
            vinculadas["valor_empenhado"] += valor
            continue
        cat = classificar(nome, contagem)
        por_categoria[cat]["emendas"] += 1
        por_categoria[cat]["valor_empenhado"] += valor
        por_categoria[cat]["autores"].add(nome)
    return {
        "vinculadas": vinculadas,
        "sem_vinculo": {
            cat: {
                "emendas": v["emendas"],
                "valor_empenhado": round(v["valor_empenhado"], 2),
                "autores_distintos": len(v["autores"]),
                "exemplos": sorted(v["autores"])[:10],
            }
            for cat, v in sorted(por_categoria.items())
        },
    }


def nomes_da_base() -> List[Tuple[Any, str]]:
    from app.core.database import SessionLocal
    from app.models import Politician

    with SessionLocal() as db:
        pares: List[Tuple[Any, str]] = []
        for pid, eleitoral, civil in db.query(Politician.id, Politician.electoral_name, Politician.civil_name).all():
            pares.extend((pid, n) for n in (eleitoral, civil) if n)
        return pares


def main(argv: Optional[List[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--json", action="store_true", help="Imprime o resultado em JSON")
    args = parser.parse_args(argv)
    emendas = load_json(PROCESSED_DATA_DIR / "emendas_parlamentares_2019_2026.json", []) or []
    resultado = diagnosticar(emendas, nomes_da_base())
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
    else:
        v = resultado["vinculadas"]
        print(f"Vinculadas: {v['emendas']} emendas, R$ {v['valor_empenhado']:,.2f} empenhados")
        for cat, d in resultado["sem_vinculo"].items():
            print(
                f"Sem vínculo [{cat}]: {d['emendas']} emendas, R$ {d['valor_empenhado']:,.2f}, "
                f"{d['autores_distintos']} autores — ex.: {', '.join(d['exemplos'][:5])}"
            )
    return resultado


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
