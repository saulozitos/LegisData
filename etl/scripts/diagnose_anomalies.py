"""
Diagnóstico de anomalias de autoria: políticos com muitas proposições ou cujo nome não aparece no `author_name`.

Compara nomes normalizados (sem acento/caixa/títulos). Nomes vazios são ignorados — antes, `"" in texto` era
sempre verdadeiro e escondia justamente os casos suspeitos.
"""

import argparse
import logging
from types import SimpleNamespace
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


SQL_AUTORIA = (
    "SELECT pe.id, pe.nome_exibicao, "
    "(SELECT n.nome FROM core.pessoa_nome n WHERE n.pessoa_id = pe.id AND n.tipo = 'CIVIL' ORDER BY n.id LIMIT 1), "
    "array_agg(l.autor_nome) FROM leg.proposicao l JOIN core.pessoa pe ON pe.id = l.autor_pessoa_id "
    "GROUP BY pe.id, pe.nome_exibicao"
)


def diagnose_anomalies() -> None:
    from app.core.database import engine
    from sqlalchemy import text

    with engine.connect() as conexao:
        linhas = conexao.execute(text(SQL_AUTORIA)).all()
    politicos = {
        pessoa_id: SimpleNamespace(electoral_name=eleitoral, civil_name=civil)
        for pessoa_id, eleitoral, civil, _ in linhas
    }
    autores_por_pol = {pessoa_id: list(autores) for pessoa_id, _, _, autores in linhas}

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
