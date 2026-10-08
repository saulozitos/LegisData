"""
Script de Saneamento e Correção de Vínculos de Autoria Legislativa.
Corrige falsos positivos gerados por colisão de tokens em proposições do Senado e da Câmara,
com ênfase na reatribuição correta das 61 PECs atribuídas erroneamente a Eduardo Bolsonaro.
"""

import re
import logging
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("fix_author_associations")


def clean_author_name(author_str: str) -> str:
    """Extrai e normaliza o nome do primeiro signatário/autor principal."""
    if not author_str:
        return ""
    # Pega o primeiro autor antes de vírgula ou ponto-e-vírgula
    first_author = re.split(r"[,;]", author_str)[0].strip()
    # Remove títulos honoríficos / parlamentares
    first_author = re.sub(r"^(Senador[a]?|Deputad[oa]|Ministr[oa]|Presidente)\s+", "", first_author, flags=re.IGNORECASE)
    # Remove sigla partidária e UF: (PL/SP), (REPUBLICANOS/MG), etc.
    first_author = re.sub(r"\s*\([^\)]*\)", "", first_author).strip()
    return first_author


def sanitize_all_proposition_authors(db: Session) -> Dict[str, int]:
    try:
        from backend.app.models.politician import Politician
        from backend.app.models.legislative import Proposition
    except ModuleNotFoundError:
        from app.models.politician import Politician
        from app.models.legislative import Proposition

    all_pols = db.query(Politician).all()
    pol_by_elec = {p.electoral_name.lower().strip(): p for p in all_pols}
    pol_by_civil = {p.civil_name.lower().strip(): p for p in all_pols}

    props = db.query(Proposition).filter(Proposition.author_politician_id.isnot(None)).all()
    total_props = len(props)
    corrigidos = 0
    eduardo_corrigidos = 0

    pol_edu = db.query(Politician).filter(Politician.electoral_name.ilike("%Eduardo Bolsonaro%")).first()
    edu_id = pol_edu.id if pol_edu else None

    for p in props:
        aut_raw = p.author_name or ""
        aut_lower = aut_raw.lower()
        curr_pol = db.query(Politician).filter(Politician.id == p.author_politician_id).first()
        if not curr_pol:
            continue

        curr_elec = curr_pol.electoral_name.lower().strip()
        curr_civil = curr_pol.civil_name.lower().strip()

        # 1. Caso Eduardo Bolsonaro: checagem rigorosa
        if edu_id and p.author_politician_id == edu_id:
            if "eduardo bolsonaro" not in aut_lower:
                # É falso positivo! Reatribuir ao primeiro signatário real
                clean_name = clean_author_name(aut_raw).lower()
                real_author = pol_by_elec.get(clean_name) or pol_by_civil.get(clean_name)
                if not real_author:
                    for name, cand in pol_by_elec.items():
                        if clean_name in name or name in clean_name:
                            real_author = cand
                            break

                p.author_politician_id = real_author.id if real_author else None
                corrigidos += 1
                eduardo_corrigidos += 1
                continue

        # 2. Caso Flávio Dino atribuído a "Dr Flávio"
        if "flávio dino" in aut_lower or "flavio dino" in aut_lower:
            if curr_elec != "flávio dino" and curr_elec != "flavio dino":
                real_dino = pol_by_elec.get("flávio dino") or pol_by_elec.get("flavio dino")
                p.author_politician_id = real_dino.id if real_dino else None
                corrigidos += 1
                continue

        # 3. Caso geral de colisão de palavras soltas:
        # Se nem o nome eleitoral nem o civil aparecem como frase coerente e não é variação direta
        first_author_clean = clean_author_name(aut_raw).lower()
        if curr_elec not in aut_lower and curr_civil not in aut_lower:
            # Checar se o primeiro signatário é outra pessoa conhecida
            real_cand = pol_by_elec.get(first_author_clean) or pol_by_civil.get(first_author_clean)
            if real_cand and real_cand.id != p.author_politician_id:
                p.author_politician_id = real_cand.id
                corrigidos += 1
            elif not real_cand and len(first_author_clean.split()) >= 2:
                # Se o autor explícito é claramente outro e não bate com o atual
                # ex: "Senador Mecias de Jesus" não pode ser atribuído a deputado X
                toks_curr = set(curr_elec.split())
                toks_first = set(first_author_clean.split())
                if not toks_curr.intersection(toks_first):
                    p.author_politician_id = None
                    corrigidos += 1

    db.commit()
    return {
        "total_analisado": total_props,
        "total_corrigidos": corrigidos,
        "eduardo_bolsonaro_corrigidos": eduardo_corrigidos
    }


if __name__ == "__main__":
    try:
        from backend.app.core.database import SessionLocal
    except ModuleNotFoundError:
        from app.core.database import SessionLocal

    with SessionLocal() as session:
        res = sanitize_all_proposition_authors(session)
        print("Resultado do saneamento de autoria:")
        print(f"  Total de proposições analisadas: {res['total_analisado']}")
        print(f"  Total de vínculos corrigidos: {res['total_corrigidos']}")
        print(f"  Falsos positivos de Eduardo Bolsonaro expurgados: {res['eduardo_bolsonaro_corrigidos']}")
