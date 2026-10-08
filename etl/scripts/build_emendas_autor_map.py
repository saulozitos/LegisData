#!/usr/bin/env python
"""
Gera/atualiza etl/data/reference/emendas_autor_map.csv: proposta de vínculo entre o
autor da emenda no Portal da Transparência (código/nome SIAFI) e o parlamentar
(camara_id / senado_id), para REVISÃO HUMANA.

Regras (ver etl/parsers/nomes.py):
  * só propõe vínculo se o nome normalizado (sem acento, maiúsculo, sem pontuação)
    for IGUAL ao nome eleitoral ou civil de UM ÚNICO parlamentar em
    deputados_camara.json + senadores_senado.json;
  * nomes que batem com mais de um cadastro ficam vazios (observacao=ambiguo);
  * se a UF predominante dos destinos das emendas do autor diferir da UF do
    parlamentar, o vínculo é descartado (observacao=uf_divergente) — homônimo provável;
  * todas as linhas novas saem com revisado=nao. Linhas já existentes com
    revisado=sim ou revisado=rejeitado são PRESERVADAS como estão.

Só usa a biblioteca padrão. Entrada: emendas_parlamentares_cgu.json (gerado por
etl/extractors/emendas_cgu_extractor.py) ou, com --zip, o EmendasParlamentares.zip.

Uso:
    python etl/scripts/build_emendas_autor_map.py
    python etl/scripts/build_emendas_autor_map.py --zip etl/data/raw/EmendasParlamentares.zip
"""

import argparse
import csv
import io
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from etl.parsers.emendas import ENCODING_EMENDAS_CSV, filtrar_linhas  # noqa: E402
from etl.parsers.nomes import (  # noqa: E402
    CAMPOS_MAPA,
    destinos_por_autor,
    indexar_parlamentares,
    propor_mapa,
    ufs_parlamentares,
)

DATA_DIR = PROJECT_ROOT / "etl" / "data"
PROCESSED = DATA_DIR / "processed"
MAPA_PADRAO = DATA_DIR / "reference" / "emendas_autor_map.csv"


def carregar_registros(zip_path: "Path | None" = None):
    if zip_path:
        with zipfile.ZipFile(zip_path) as z, z.open("EmendasParlamentares.csv") as f:
            leitor = csv.DictReader(io.TextIOWrapper(f, encoding=ENCODING_EMENDAS_CSV, newline=""), delimiter=";")
            return list(filtrar_linhas(leitor))
    with open(PROCESSED / "emendas_parlamentares_cgu.json", encoding="utf-8") as f:
        return json.load(f)


def ler_mapa(caminho: Path):
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def gravar_mapa(caminho: Path, linhas):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_MAPA, delimiter=";", extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for ln in linhas:
            w.writerow({c: ln.get(c, "") for c in CAMPOS_MAPA})


def construir(registros, deputados, senadores, existentes):
    indice = indexar_parlamentares(deputados, senadores)
    ufs = ufs_parlamentares(deputados, senadores)
    destinos = destinos_por_autor(registros)
    autores = {(r["codigo_autor_siafi"], r["nome_autor"]) for r in registros}
    propostas = propor_mapa(autores, indice, ufs, destinos)

    # Preserva decisões humanas já registradas
    revisadas = {
        (ln.get("codigo_autor_siafi"), ln.get("nome_autor")): ln
        for ln in existentes
        if (ln.get("revisado") or "").strip().lower() not in ("", "nao", "não")
    }
    final = [revisadas.get((p["codigo_autor_siafi"], p["nome_autor"]), p) for p in propostas]
    # Mantém linhas revisadas de autores que sumiram do arquivo atual
    chaves = {(p["codigo_autor_siafi"], p["nome_autor"]) for p in propostas}
    final.extend(ln for k, ln in revisadas.items() if k not in chaves)
    return final


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", type=Path, help="Lê direto do EmendasParlamentares.zip (sem pandas)")
    ap.add_argument("--saida", type=Path, default=MAPA_PADRAO)
    args = ap.parse_args()

    registros = carregar_registros(args.zip)
    with open(PROCESSED / "deputados_camara.json", encoding="utf-8") as f:
        deputados = json.load(f)
    with open(PROCESSED / "senadores_senado.json", encoding="utf-8") as f:
        senadores = json.load(f)

    linhas = construir(registros, deputados, senadores, ler_mapa(args.saida))
    gravar_mapa(args.saida, linhas)

    obs = Counter(ln.get("observacao") or "vinculo_proposto" for ln in linhas)
    print(f"{len(linhas)} autores no mapa -> {args.saida}")
    for k, v in sorted(obs.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
