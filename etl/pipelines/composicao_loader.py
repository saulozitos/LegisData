"""
Carga da composição do Congresso por mandato presidencial e da produção legislativa do Executivo em `leg`.

Fontes (curadoria versionada em `etl/data/processed`):
- `composicao_congresso.json`: bancadas por partido, presidentes das Casas e conferência com o TSE de cada mandato;
- `producao_executivo.csv`: proposições do Executivo e vetos (insumo do IPLE).

Só mandatos que já existem em `core.mandato_presidencial` são carregados: mandato do arquivo sem identificador no banco
faz a carga falhar sem gravar nada. Cada par (mandato, Casa) é regravado por inteiro, e a Casa (ou o mandato) que sai
da curadoria sai do banco, então a carga é idempotente e o banco espelha o arquivo. A produção do Executivo segue a mesma
regra, mas um CSV sem nenhuma linha não apaga a base.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import inteiro, texto
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("ComposicaoLoader")

CASAS = {"camara": "CAMARA_DOS_DEPUTADOS", "senado": "SENADO_FEDERAL"}
ALINHAMENTOS = {"BASE_GOVERNO", "INDEPENDENTE_CENTRO", "OPOSICAO", "NAO_CLASSIFICADO"}


def bancadas_da_casa(casa: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Une as bancadas exibidas (`cadeiras`) e as eleitas segundo o TSE (`cadeiras_tse`) por partido."""
    por_partido: Dict[str, Dict[str, Any]] = {}
    for b in (x for x in casa.get("bancadas") or [] if isinstance(x, dict)):
        sigla = texto(b.get("partido"))
        if not sigla:
            continue
        alinhamento = texto(b.get("alinhamento")) or "NAO_CLASSIFICADO"
        por_partido[sigla] = {
            "sigla": sigla,
            "cadeiras": inteiro(b.get("cadeiras")),
            "cadeiras_tse": None,
            "alinhamento": alinhamento if alinhamento in ALINHAMENTOS else "NAO_CLASSIFICADO",
            "cor_hex": texto(b.get("cor_hex")),
        }
    for b in (x for x in casa.get("bancadas_eleitas_tse") or [] if isinstance(x, dict)):
        sigla = texto(b.get("partido"))
        if not sigla:
            continue
        linha = por_partido.setdefault(
            sigla, {"sigla": sigla, "cadeiras": None, "cadeiras_tse": None, "alinhamento": None, "cor_hex": None}
        )
        linha["cadeiras_tse"] = inteiro(b.get("cadeiras"))
    linhas = [b for b in por_partido.values() if b["cadeiras"] is not None or b["cadeiras_tse"] is not None]
    # a ordem da curadoria (desempates entre partidos de mesmo tamanho) é preservada
    for ordem, linha in enumerate(linhas):
        linha["ordem"] = ordem
    return linhas


def ler_producao(caminho: Path) -> List[Dict[str, str]]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de produção do Executivo ausente: {caminho}")
    with open(caminho, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, int]:
    pasta = Path(processed_dir or PROCESSED_DATA_DIR)
    composicao = load_json(pasta / "composicao_congresso.json")
    if not composicao:
        raise FileNotFoundError(f"Composição do Congresso ausente ou vazia: {pasta / 'composicao_congresso.json'}")
    producao = ler_producao(pasta / "producao_executivo.csv")

    contagem = {"mandatos": 0, "bancadas": 0, "presidentes": 0, "producao": 0}
    with engine.begin() as conn:
        mandatos = {
            slug: mid for mid, slug in conn.execute(text("SELECT mandato_id, slug FROM core.mandato_presidencial"))
        }
        casas = {codigo: cid for cid, codigo in conn.execute(text("SELECT id, codigo FROM ref.casa_legislativa"))}
        ausentes = sorted(
            (set(composicao) | {texto(r.get("mandato_slug")) or "(sem slug)" for r in producao}) - set(mandatos)
        )
        if ausentes:
            raise RuntimeError(f"Mandatos sem identificador no banco: {', '.join(ausentes)}")

        # A curadoria é a fonte completa: mandato ou Casa que saiu do arquivo (ou ficou sem total) também sai do banco
        for slug, mandato_id in mandatos.items():
            dados = composicao.get(slug) or {}
            contagem["mandatos"] += 1 if slug in composicao else 0
            for chave, codigo in CASAS.items():
                casa = dados.get(chave) or {}
                if casa.get("total_cadeiras"):
                    _gravar_casa(conn, mandato_id, casas[codigo], dados, casa, contagem)
                else:
                    _apagar_casa(conn, mandato_id, casas[codigo])
        _gravar_producao(conn, mandatos, producao, contagem)
    logger.info("Composição do Congresso carregada: %s", contagem)
    return contagem


COLUNAS_PRODUCAO = (
    "proposicoes_executivo",
    "proposicoes_aprovadas",
    "vetos_apreciados",
    "vetos_mantidos",
    "vetos_pendentes",
    "fonte",
)


def _linha_de_producao(linha: Dict[str, str]) -> Dict[str, Any]:
    """Valida a linha do CSV: contagens obrigatórias inteiras, ausência de coluna ou célula vazia é erro claro."""
    faltam = [c for c in COLUNAS_PRODUCAO if texto(linha.get(c)) is None]
    if faltam:
        raise ValueError(f"Produção do Executivo de '{linha.get('mandato_slug')}' sem: {', '.join(faltam)}")
    return {
        "pe": int(linha["proposicoes_executivo"]),
        "pa": int(linha["proposicoes_aprovadas"]),
        "va": int(linha["vetos_apreciados"]),
        "vm": int(linha["vetos_mantidos"]),
        "vp": int(linha["vetos_pendentes"]),
        "oc": inteiro(linha.get("oposicao_cadeiras_camara")),
        "tc": inteiro(linha.get("total_cadeiras_camara")),
        "f": texto(linha["fonte"]),
    }


def _gravar_producao(
    conn: Any, mandatos: Dict[str, int], producao: List[Dict[str, str]], contagem: Dict[str, int]
) -> None:
    """Grava a produção do CSV e remove a dos mandatos que saíram dele (o banco espelha o arquivo)."""
    linhas = [(mandatos[linha["mandato_slug"]], _linha_de_producao(linha)) for linha in producao]  # valida tudo antes
    if linhas:
        conn.execute(
            text("DELETE FROM leg.producao_executivo WHERE mandato_id <> ALL(CAST(:ids AS bigint[]))"),
            {"ids": [mandato_id for mandato_id, _ in linhas]},
        )
    for mandato_id, valores in linhas:
        conn.execute(
            text(
                "INSERT INTO leg.producao_executivo (mandato_id, proposicoes_executivo, proposicoes_aprovadas, "
                "vetos_apreciados, vetos_mantidos, vetos_pendentes, oposicao_cadeiras_camara, "
                "total_cadeiras_camara, fonte_texto) VALUES (:m, :pe, :pa, :va, :vm, :vp, :oc, :tc, :f) "
                "ON CONFLICT (mandato_id) DO UPDATE SET proposicoes_executivo = EXCLUDED.proposicoes_executivo, "
                "proposicoes_aprovadas = EXCLUDED.proposicoes_aprovadas, vetos_apreciados = EXCLUDED.vetos_apreciados, "
                "vetos_mantidos = EXCLUDED.vetos_mantidos, vetos_pendentes = EXCLUDED.vetos_pendentes, "
                "oposicao_cadeiras_camara = EXCLUDED.oposicao_cadeiras_camara, "
                "total_cadeiras_camara = EXCLUDED.total_cadeiras_camara, fonte_texto = EXCLUDED.fonte_texto"
            ),
            {"m": mandato_id, **valores},
        )
        contagem["producao"] += 1


def _apagar_casa(conn: Any, mandato_id: int, casa_id: int) -> None:
    """Remove a composição (bancadas em cascata) e os presidentes da Casa no mandato."""
    conn.execute(
        text("DELETE FROM leg.composicao_mandato WHERE mandato_id = :m AND casa_id = :c"),
        {"m": mandato_id, "c": casa_id},
    )
    conn.execute(
        text(
            "DELETE FROM leg.presidencia_casa_mandato WHERE mandato_id = :m AND presidencia_id IN "
            "(SELECT id FROM leg.presidencia_casa WHERE casa_id = :c)"
        ),
        {"m": mandato_id, "c": casa_id},
    )


def _gravar_casa(
    conn: Any, mandato_id: int, casa_id: int, mandato: Dict[str, Any], casa: Dict[str, Any], contagem: Dict[str, int]
) -> None:
    _apagar_casa(conn, mandato_id, casa_id)
    _gravar_composicao(conn, mandato_id, casa_id, mandato, casa)
    _gravar_bancadas(conn, mandato_id, casa_id, casa, contagem)
    _gravar_presidentes(conn, mandato_id, casa_id, casa, contagem)


def _gravar_composicao(conn: Any, mandato_id: int, casa_id: int, mandato: Dict[str, Any], casa: Dict[str, Any]) -> None:
    verificacao = casa.get("verificacao_tse") or {}
    origem = "TSE" if str(casa.get("bancadas_origem") or "").upper().startswith("TSE") else "CURADORIA"
    conn.execute(
        text(
            "INSERT INTO leg.composicao_mandato (mandato_id, casa_id, total_cadeiras, bancadas_origem, tse_status, "
            "tse_ano_legislatura, tse_total_eleitos, tse_total_esperado, tse_conferido, tse_nota, tse_motivo, "
            "tse_divergencias, observacao, fonte_texto) "
            "VALUES (:m, :c, :t, :o, :s, :a, :te, :tx, :cf, :n, :mo, CAST(:dv AS jsonb), :ob, :f)"
        ),
        {
            "m": mandato_id,
            "c": casa_id,
            "t": int(casa["total_cadeiras"]),
            "o": origem,
            "s": texto(verificacao.get("status")),
            "a": inteiro(verificacao.get("ano_legislatura")),
            "te": inteiro(verificacao.get("total_eleitos_tse")),
            "tx": inteiro(verificacao.get("total_esperado")),
            "cf": verificacao.get("conferido") if isinstance(verificacao.get("conferido"), bool) else None,
            "n": texto(verificacao.get("nota")),
            "mo": texto(verificacao.get("motivo")),
            "dv": (
                json.dumps(verificacao["divergencias"], ensure_ascii=False) if verificacao.get("divergencias") else None
            ),
            "ob": texto(mandato.get("observacao")),
            "f": texto(mandato.get("fonte_curadoria")),
        },
    )


def _gravar_bancadas(conn: Any, mandato_id: int, casa_id: int, casa: Dict[str, Any], contagem: Dict[str, int]) -> None:
    bancadas = bancadas_da_casa(casa)
    if not bancadas:
        return
    conn.execute(
        text(
            "INSERT INTO leg.bancada_mandato (mandato_id, casa_id, partido_sigla, cadeiras, cadeiras_tse, "
            "alinhamento, cor_hex, ordem) VALUES (:m, :c, :s, :ca, :ct, :al, :cor, :o)"
        ),
        [
            {
                "m": mandato_id,
                "c": casa_id,
                "s": b["sigla"],
                "ca": b["cadeiras"],
                "ct": b["cadeiras_tse"],
                "al": b["alinhamento"],
                "cor": b["cor_hex"],
                "o": b["ordem"],
            }
            for b in bancadas
        ],
    )
    contagem["bancadas"] += len(bancadas)


def _gravar_presidentes(
    conn: Any, mandato_id: int, casa_id: int, casa: Dict[str, Any], contagem: Dict[str, int]
) -> None:
    for ordem, p in enumerate(casa.get("presidentes") or []):
        nome = texto(p.get("nome"))
        rotulo = texto(p.get("periodo"))
        if nome is None or rotulo is None:
            continue
        presidencia_id = conn.execute(
            text(
                "INSERT INTO leg.presidencia_casa (casa_id, nome, partido_sigla, uf, foto_url) "
                "VALUES (:c, :n, :p, :uf, :f) ON CONFLICT (casa_id, nome, partido_sigla) DO UPDATE SET "
                "uf = COALESCE(EXCLUDED.uf, leg.presidencia_casa.uf), "
                "foto_url = COALESCE(EXCLUDED.foto_url, leg.presidencia_casa.foto_url) RETURNING id"
            ),
            {
                "c": casa_id,
                "n": nome,
                "p": texto(p.get("partido")),
                "uf": texto(p.get("uf")),
                "f": texto(p.get("foto_url")),
            },
        ).scalar()
        conn.execute(
            text(
                "INSERT INTO leg.presidencia_casa_mandato (mandato_id, presidencia_id, ordem, rotulo_periodo) "
                "VALUES (:m, :p, :o, :r) ON CONFLICT DO NOTHING"
            ),
            {"m": mandato_id, "p": presidencia_id, "o": ordem, "r": rotulo},
        )
        contagem["presidentes"] += 1
