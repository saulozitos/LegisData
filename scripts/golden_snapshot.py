#!/usr/bin/env python3
"""
Snapshot ("golden files") das respostas da API para comparar antes/depois da refatoração do banco.

Uso:
    python3 scripts/golden_snapshot.py snapshot etl/data/golden/baseline --base-url http://127.0.0.1:8001
    python3 scripts/golden_snapshot.py compare etl/data/golden/baseline etl/data/golden/atual

Só usa a biblioteca padrão. As respostas são gravadas ordenadas e com chaves ordenadas para que a
comparação aponte diferenças reais (campos de timestamp de execução são ignorados).
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

API = "/api/v1"
IGNORED_KEYS = {"atualizado_em", "iniciado_em", "finalizado_em", "started_at", "finished_at", "duracao_segundos"}
AMOSTRA_POLITICOS = 8
AMOSTRA_PROPOSICOES = 5

ENDPOINTS_FIXOS: List[str] = [
    "/parties",
    "/parties/ippm-ranking",
    "/politicians/presidents",
    "/politicians?limit=50",
    "/politicians?limit=20&office=SENADOR",
    "/politicians?limit=20&party=PT",
    "/economic/annual-summary",
    "/economic/ipca-monthly",
    "/analytics/mandates-performance",
    "/analytics/party-fidelity",
    "/analytics/wage-disparity",
    "/analytics/congress-composition",
    "/analytics/federal-transfers",
    "/analytics/social-indicators",
    "/analytics/social-classes",
    "/analytics/social-elections",
    "/legislative/propositions",
    "/legislative/ranking/authors",
    "/legislative/network",
    "/legislative/explorer",
    "/legislative/calendar",
    "/executivo/mandates",
    "/executivo/iple",
    "/emendas/resumo",
    "/cidadania",
]


def _slug(path: str) -> str:
    return urllib.parse.quote(path.strip("/") or "root", safe="").replace("%", "_")[:150] + ".json"


def _fetch(base: str, path: str) -> Dict[str, Any]:
    url = base.rstrip("/") + API + urllib.parse.quote(path, safe="/?&=%")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:  # nosec B310 - URL controlada pelo operador
            return {"status": response.status, "body": json.loads(response.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "body": None}
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"status": None, "erro": str(exc)}


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in sorted(value.items()) if k not in IGNORED_KEYS}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _first_ids(body: Any, key: Optional[str], limit: int) -> List[str]:
    items = body.get(key, []) if isinstance(body, dict) and key else body
    ids = [str(i["id"]) for i in (items or []) if isinstance(i, dict) and i.get("id")]
    return ids[:limit]


def snapshot(out_dir: Path, base: str) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = list(ENDPOINTS_FIXOS)

    politicos = _fetch(base, "/politicians?limit=50")
    for pid in _first_ids(politicos.get("body"), "politicos", AMOSTRA_POLITICOS):
        paths += [f"/politicians/{pid}"] + [f"/politicians/{pid}/{s}" for s in ("ceap", "emendas", "certidoes", "doacoes")]
        paths.append(f"/legislative/politicians/{pid}/productivity")

    props = _fetch(base, "/legislative/propositions")
    for prop in _first_ids(props.get("body"), None, AMOSTRA_PROPOSICOES):
        paths += [f"/legislative/propositions/{prop}/votes", f"/legislative/propositions/{prop}/deliberacoes"]

    parties = _fetch(base, "/parties")
    for sigla in [p["sigla"] for p in (parties.get("body") or [])[:6] if isinstance(p, dict)]:
        paths.append(f"/parties/{sigla}/historico-bancada")

    index: Dict[str, Any] = {}
    for path in paths:
        result = _fetch(base, path)
        (out_dir / _slug(path)).write_text(
            json.dumps(_clean(result), ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        index[path] = result.get("status")
    (out_dir / "_index.json").write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    falhas = [p for p, s in index.items() if s is None or s >= 500]
    print(f"{len(index)} endpoints gravados em {out_dir}; {len(falhas)} com falha de servidor/rede")
    for p in falhas:
        print("  FALHA:", p)
    return 1 if falhas else 0


def compare(dir_a: Path, dir_b: Path) -> int:
    files_a = {p.name for p in dir_a.glob("*.json")}
    files_b = {p.name for p in dir_b.glob("*.json")}
    diffs = 0
    for name in sorted(files_a | files_b):
        if name not in files_a or name not in files_b:
            print(f"AUSENTE em {'B' if name in files_a else 'A'}: {name}")
            diffs += 1
        elif (dir_a / name).read_text(encoding="utf-8") != (dir_b / name).read_text(encoding="utf-8"):
            print(f"DIFERENTE: {name}")
            diffs += 1
    print(f"{len(files_a | files_b)} arquivos comparados, {diffs} diferenças")
    return 1 if diffs else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot")
    snap.add_argument("out_dir", type=Path)
    snap.add_argument("--base-url", default="http://127.0.0.1:8000")
    comp = sub.add_parser("compare")
    comp.add_argument("dir_a", type=Path)
    comp.add_argument("dir_b", type=Path)
    args = parser.parse_args()
    if args.cmd == "snapshot":
        return snapshot(args.out_dir, args.base_url)
    return compare(args.dir_a, args.dir_b)


if __name__ == "__main__":
    sys.exit(main())
