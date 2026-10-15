"""Catálogo de partidos lido do schema `core` (fonte única: o banco, sem constantes no código)."""

from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.orm import Session

# Cor neutra quando o partido não tem cor cadastrada em core.partido.cor_hex
DEFAULT_PARTY_COLOR = "#64748b"
# Partido-sentinela para parlamentares sem legenda: não é um partido do catálogo
SEM_PARTIDO_SIGLA = "S.PART."

_CATALOG_SQL = text(
    """
    SELECT p.uid::text AS id, p.sigla, p.nome AS nome_completo, p.numero_eleitoral,
           p.espectro_politico, p.ideologia_texto AS ideologia, p.lema, p.logo_url, p.cor_hex,
           coalesce(dep.total, 0) AS total_deputados,
           coalesce(sen.total, 0) AS total_senadores,
           coalesce(fil.total, 0) AS total_filiados_ativos
    FROM core.vw_partido p
    LEFT JOIN core.vw_bancada_atual dep
           ON dep.partido_id = p.id AND dep.cargo_id = (SELECT id FROM ref.cargo WHERE codigo = 'DEPUTADO_FEDERAL')
    LEFT JOIN core.vw_bancada_atual sen
           ON sen.partido_id = p.id AND sen.cargo_id = (SELECT id FROM ref.cargo WHERE codigo = 'SENADOR')
    LEFT JOIN core.vw_filiados_ativos fil ON fil.partido_id = p.id
    WHERE p.sigla <> :sem_partido
      AND p.catalogo AND p.linhagem_id IS NULL
    ORDER BY coalesce(dep.total, 0) + coalesce(sen.total, 0) DESC, coalesce(fil.total, 0) DESC, p.sigla
    """
)


def list_party_catalog(db: Session) -> List[Dict[str, Any]]:
    """Partidos com bancada atual (deputados/senadores em mandato vigente) e filiados ativos."""
    result = []
    for row in db.execute(_CATALOG_SQL, {"sem_partido": SEM_PARTIDO_SIGLA}).mappings():
        total_deputados = row["total_deputados"]
        total_senadores = row["total_senadores"]
        result.append(
            {
                "id": row["id"],
                "sigla": row["sigla"],
                "nome_completo": row["nome_completo"],
                "numero_eleitoral": row["numero_eleitoral"],
                "espectro_politico": row["espectro_politico"],
                "ideologia": row["ideologia"],
                "lema": row["lema"],
                "logo_url": row["logo_url"],
                "total_deputados": total_deputados,
                "total_senadores": total_senadores,
                "total_parlamentares": total_deputados + total_senadores,
                "total_filiados_ativos": row["total_filiados_ativos"],
                "cor_hex": row["cor_hex"] or DEFAULT_PARTY_COLOR,
            }
        )
    return result
