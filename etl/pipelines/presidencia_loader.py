"""
Carga dos metadados dos mandatos presidenciais em `core.mandato_presidencial` e `core.marco_governo`.

A fonte é o catálogo curado `presidentes_historico.json` (vice, como o mandato começou, situação e marcos econômicos).
Os mandatos e os identificadores públicos (`slug`) já existem no banco: entrada do catálogo sem mandato correspondente
faz a carga falhar (nada é gravado), e nada é criado às escondidas. Os marcos de um mandato são regravados por inteiro, mas só
quando o catálogo traz ao menos um.

Campo ausente no catálogo (vice, motivo, situação) não apaga o que já está no banco.
Idempotente: duas execuções seguidas deixam as tabelas iguais.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("PresidenciaLoader")

STATUS_VALIDOS = {"CONCLUIDO", "IMPEACHMENT", "TITULAR_ATIVO", "RENUNCIA", "FALECIMENTO"}


def texto(valor: Any) -> Optional[str]:
    """Texto sem espaços nas pontas; vazio vira None."""
    limpo = str(valor).strip() if valor is not None else ""
    return limpo or None


def marcos(entrada: Dict[str, Any]) -> List[str]:
    return [m for m in (texto(item) for item in entrada.get("marcos_economicos") or []) if m]


def _foto(conn, mandato_id: int, caminho: Optional[str]) -> None:
    """Associa a foto (arquivo em `frontend/public`) à pessoa do mandato."""
    if not caminho:
        return
    midia_id = conn.execute(
        text(
            "INSERT INTO core.midia (tipo, url_origem, caminho, fonte_id) "
            "VALUES ('FOTO_PESSOA', :u, :u, (SELECT id FROM etl.fonte WHERE codigo = 'CURADORIA')) "
            "ON CONFLICT (tipo, url_origem) DO UPDATE SET caminho = EXCLUDED.caminho RETURNING id"
        ),
        {"u": caminho},
    ).scalar()
    conn.execute(
        text("UPDATE core.pessoa SET foto_midia_id = :f WHERE id = (SELECT pessoa_id FROM core.mandato WHERE id = :m)"),
        {"f": midia_id, "m": mandato_id},
    )


def _papeis(conn, mandato_id: int, entrada: Dict[str, Any]) -> None:
    """Papel de cada ministro da Fazenda/Economia do mandato (nomeado por ele, mesmo nome e mesma posse)."""
    for ministro in entrada.get("ministros_fazenda_chave") or []:
        conn.execute(
            text(
                "UPDATE core.mandato m SET papel = :papel FROM core.pessoa pe "
                "WHERE pe.id = m.pessoa_id AND m.nomeado_por_mandato_id = :mandato AND m.inicio = :inicio "
                "AND ref.normalizar_texto(pe.nome_exibicao) = ref.normalizar_texto(:nome)"
            ),
            {
                "papel": texto(ministro.get("papel")),
                "mandato": mandato_id,
                "inicio": ministro.get("inicio"),
                "nome": ministro.get("nome") or "",
            },
        )


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, int]:
    arquivo = Path(processed_dir or PROCESSED_DATA_DIR) / "presidentes_historico.json"
    catalogo = load_json(arquivo)
    if not catalogo:
        raise FileNotFoundError(f"Catálogo de presidentes ausente ou vazio: {arquivo}")

    atualizados = 0
    ausentes: List[str] = []
    with engine.begin() as conn:
        for entrada in catalogo:
            slug = texto(entrada.get("id_referencia"))
            mandato_id = conn.execute(
                text("SELECT mandato_id FROM core.mandato_presidencial WHERE slug = :s"), {"s": slug}
            ).scalar()
            if mandato_id is None:
                logger.error("Presidente do catálogo sem mandato no banco: %s", slug)
                ausentes.append(str(slug))
                continue
            status = texto(entrada.get("status_mandato"))
            conn.execute(
                text(
                    "UPDATE core.mandato_presidencial SET vice_texto = coalesce(:v, vice_texto), "
                    "motivo_inicio = coalesce(:m, motivo_inicio), status = coalesce(:st, status) "
                    "WHERE mandato_id = :id"
                ),
                {
                    "v": texto(entrada.get("vice_presidente")),
                    "m": texto(entrada.get("motivo_inicio")),
                    "st": status if status in STATUS_VALIDOS else None,
                    "id": mandato_id,
                },
            )
            _foto(conn, mandato_id, texto(entrada.get("foto_url")))
            _papeis(conn, mandato_id, entrada)
            lista = marcos(entrada)
            if lista:
                conn.execute(text("DELETE FROM core.marco_governo WHERE mandato_id = :id"), {"id": mandato_id})
                conn.execute(
                    text("INSERT INTO core.marco_governo (mandato_id, ordem, texto) VALUES (:id, :o, :t)"),
                    [{"id": mandato_id, "o": i, "t": t} for i, t in enumerate(lista, start=1)],
                )
            atualizados += 1
        if ausentes:
            # Falha alto, e a transação inteira volta: mandato ausente costuma ser carga fora de ordem
            # (`make db-migrate`, depois `--load-db`, depois `--load-economia`), e seguir sem ele esvaziaria o painel.
            raise RuntimeError(f"Mandatos presidenciais ausentes no banco: {', '.join(ausentes)}")
    logger.info("Mandatos presidenciais atualizados: %d", atualizados)
    return {"atualizados": atualizados}
