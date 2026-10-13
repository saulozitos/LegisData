"""
Saneamento de vínculos de autoria legislativa (proposição -> político).

Reaplica a MESMA regra do loader (`AuthorResolver`): primeiro signatário, nome completo normalizado e inequívoco.
Corrige falsos positivos de versões antigas — como as proposições atribuídas a Eduardo Bolsonaro por colisão de
tokens ("Flávio Dino" -> "Flávio") — sem nomes hardcoded e sem remover vínculos corretos.

Diferenças em relação à versão anterior:
  * comparações normalizadas (acentos/caixa): "João" não deixa de casar com "Joao" nem apaga o vínculo certo;
  * sem `curr_pol.electoral_name.lower()` em None, sem N+1 (um carregamento de políticos);
  * só desvincula quando o político atual NÃO compartilha nenhum token com o primeiro signatário;
  * por padrão é DRY-RUN: nada é gravado sem `--apply`.
"""

import argparse
import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.names import NON_PERSON_AUTHORS, first_signatory, normalize_name_tokens

ensure_backend_on_path()

logger = logging.getLogger("fix_author_associations")


def tokens_do_politico(pol: Any) -> set:
    toks: set = set()
    for nome in (pol.electoral_name, pol.civil_name):
        toks |= set(normalize_name_tokens(nome).split())
    return toks


def sanitize_all_proposition_authors(db: Session, apply: bool = False) -> Dict[str, int]:
    from app.models.legislative import Proposition
    from app.models.politician import Politician

    from etl.pipelines.db_loader import AuthorResolver

    politicos = db.query(Politician).all()
    por_id = {p.id: p for p in politicos}
    # camara_id/senado_id vazios: aqui só a regra por nome é necessária
    resolver = AuthorResolver(politicos, deputy_map={}, senator_map={})

    props = db.query(Proposition).filter(Proposition.author_politician_id.isnot(None)).all()
    resultado = {"total_analisado": len(props), "total_corrigidos": 0, "reatribuidos": 0, "desvinculados": 0}

    for prop in props:
        autor_raw = prop.author_name or ""
        primeiro = first_signatory(autor_raw)
        norm = normalize_name_tokens(primeiro)
        atual = por_id.get(prop.author_politician_id)
        if not atual or not norm:
            continue

        if norm in NON_PERSON_AUTHORS:
            novo: Optional[Any] = None
        else:
            novo = resolver.resolve(autor_raw)

        if novo is not None:
            if novo != prop.author_politician_id:
                prop.author_politician_id = novo
                resultado["reatribuidos"] += 1
                resultado["total_corrigidos"] += 1
            continue

        # Não há político único para o nome do autor: só desfaz o vínculo se o atual não tem NADA a ver com ele.
        if norm in NON_PERSON_AUTHORS or not (tokens_do_politico(atual) & set(norm.split())):
            prop.author_politician_id = None
            resultado["desvinculados"] += 1
            resultado["total_corrigidos"] += 1

    if apply:
        db.commit()
    else:
        db.rollback()
        logger.warning("DRY-RUN: nenhuma alteração gravada. Use --apply para persistir.")
    return resultado


def main(argv: Optional[list] = None) -> Dict[str, int]:
    parser = argparse.ArgumentParser(description="Saneia vínculos proposição -> autor.")
    parser.add_argument("--apply", action="store_true", help="Grava as correções (padrão: apenas simula).")
    args = parser.parse_args(argv)

    from app.core.database import SessionLocal

    with SessionLocal() as session:
        res = sanitize_all_proposition_authors(session, apply=args.apply)
    print("Resultado do saneamento de autoria:")
    print(f"  Proposições analisadas: {res['total_analisado']}")
    print(f"  Vínculos reatribuídos:  {res['reatribuidos']}")
    print(f"  Vínculos desfeitos:     {res['desvinculados']}")
    print(f"  Total corrigido:        {res['total_corrigidos']}{'' if args.apply else ' (simulação)'}")
    return res


if __name__ == "__main__":
    main()
