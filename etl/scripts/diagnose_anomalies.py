"""
Diagnóstico de anomalias de autoria: políticos com muitas proposições ou cujo nome não aparece no `author_name`.

Compara nomes normalizados (sem acento/caixa/títulos). Nomes vazios são ignorados — antes, `"" in texto` era
sempre verdadeiro e escondia justamente os casos suspeitos.
"""

import argparse
import logging
from collections import defaultdict
from typing import Optional

from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.names import first_signatory, normalize_name_tokens

ensure_backend_on_path()

LIMITE_TOP = 50
LIMITE_VOLUME_ALTO = 100


def nome_aparece(nome_politico: Optional[str], autor: Optional[str]) -> bool:
    """True se TODOS os tokens do nome do político estão no primeiro signatário do autor."""
    toks = set(normalize_name_tokens(nome_politico).split())
    if not toks:
        return False
    return toks <= set(normalize_name_tokens(first_signatory(autor)).split())


def diagnose_anomalies() -> None:
    from app.core.database import engine

    from etl.pipelines import stg_tabela
    from etl.utils.copia import transacao_de_carga

    with transacao_de_carga(engine) as cursor:
        politicos = {p.id: p for p in stg_tabela.politicos().carregar(cursor)}
        proposicoes = list(stg_tabela.proposicoes().carregar(cursor))

    # Um único passe pelas proposições (antes: uma consulta por político)
    autores_por_pol = defaultdict(list)
    for prop in proposicoes:
        if prop.author_politician_id in politicos:
            autores_por_pol[prop.author_politician_id].append(prop.author_name)
    ranking = sorted(
        (
            (pol_id, politicos[pol_id].electoral_name, politicos[pol_id].civil_name, len(autores))
            for pol_id, autores in autores_por_pol.items()
        ),
        key=lambda r: r[3],
        reverse=True,
    )
    print(f"Total de políticos com proposições: {len(ranking)}")

    top = ranking[:LIMITE_TOP]
    print(f"\n=== TOP {LIMITE_TOP} POLÍTICOS COM MAIS PROPOSIÇÕES ===")
    for i, (pol_id, elec_name, civil_name, total) in enumerate(top, start=1):
        suspeitos = [
            a for a in autores_por_pol[pol_id] if not (nome_aparece(elec_name, a) or nome_aparece(civil_name, a))
        ]
        if not suspeitos and total <= LIMITE_VOLUME_ALTO:
            continue
        print(f"\n{i}. {elec_name} (ID: {pol_id}) - {total} proposições")
        print(f"   Nome Civil: {civil_name}")
        if suspeitos:
            print(f"   ALERTA: {len(suspeitos)} proposições suspeitas ({len(suspeitos) / total * 100:.1f}%)")
            print("   Exemplos de author_name suspeitos:")
            for nome in list(dict.fromkeys(suspeitos))[:10]:
                print(f"     - {nome}")


def main(argv: Optional[list] = None) -> None:
    argparse.ArgumentParser(description="Diagnostica anomalias de autoria (somente leitura).").parse_args(argv)
    diagnose_anomalies()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
