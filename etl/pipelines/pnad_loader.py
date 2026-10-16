"""
Carga da distribuição de renda da PNAD Contínua em `eco.pnad_*` a partir de `pnad_faixas_salario_minimo.json`.

O arquivo é calculado pelo ETL (`--pnad`) dos microdados do IBGE. Cada ano é regravado por inteiro; ano inválido (sem
salário mínimo ou sem as 8 faixas) é pulado e contado. Arquivo sem nenhum ano válido não apaga a base.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("PnadLoader")

DISTRIBUICOES = (
    "domicilios_renda_total",
    "pessoas_renda_domiciliar",
    "pessoas_renda_per_capita",
    "ocupados_renda_trabalho",
)
N_FAIXAS = 8


def percentual_valido(valor: Any) -> Optional[List[float]]:
    """Lista de 8 percentuais numéricos; qualquer outra coisa é None."""
    if not isinstance(valor, list) or len(valor) != N_FAIXAS:
        return None
    try:
        return [float(v) for v in valor]
    except (TypeError, ValueError):
        return None


def ano_valido(entrada: Any) -> bool:
    """O ano só entra com salário mínimo e as duas distribuições usadas nas classes (domicílios e pessoas)."""
    if not isinstance(entrada, dict) or not entrada.get("salario_minimo_brl"):
        return False
    nacional = entrada.get("nacional")
    if not isinstance(nacional, dict):
        return False
    return all(
        isinstance(nacional.get(c), dict) and percentual_valido(nacional[c].get("percentual")) is not None
        for c in ("domicilios_renda_total", "pessoas_renda_domiciliar")
    )


def linhas_do_ano(entrada: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Uma linha por escopo (BR ou UF) e distribuição com percentuais válidos."""
    escopos = {"BR": entrada.get("nacional") or {}}
    for uf, dados in (entrada.get("uf") or {}).items():
        escopos[str(uf).upper()] = dados or {}
    linhas = []
    for escopo, dados in escopos.items():
        for distribuicao in DISTRIBUICOES:
            info = dados.get(distribuicao) if isinstance(dados, dict) else None
            percentual = percentual_valido(info.get("percentual")) if isinstance(info, dict) else None
            if percentual is None:
                continue
            linhas.append(
                {
                    "escopo": escopo,
                    "distribuicao": distribuicao,
                    "total": info.get("total_estimado"),
                    "media": info.get("media_nominal_brl"),
                    "percentual": percentual,
                }
            )
    return linhas


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, int]:
    arquivo = Path(processed_dir or PROCESSED_DATA_DIR) / "pnad_faixas_salario_minimo.json"
    dados = load_json(arquivo)
    if not isinstance(dados, dict) or not isinstance(dados.get("anos"), dict):
        raise FileNotFoundError(f"Arquivo da PNAD ausente ou inválido: {arquivo}")
    validos = {ano: e for ano, e in dados["anos"].items() if ano_valido(e)}
    pulados = len(dados["anos"]) - len(validos)
    if not validos:
        logger.warning("Nenhum ano válido da PNAD no arquivo; a base não foi alterada.")
        return {"anos": 0, "pulados": pulados, "distribuicoes": 0}

    total = 0
    with engine.begin() as conn:
        for ano, entrada in sorted(validos.items()):
            conn.execute(text("DELETE FROM eco.pnad_ano WHERE ano = :a"), {"a": int(ano)})
            conn.execute(
                text(
                    "INSERT INTO eco.pnad_ano (ano, visita, salario_minimo_brl, arquivo_microdados, dicionario, "
                    "extraido_em, linhas_lidas, populacao_total_estimada) VALUES (:a, :v, :s, :ar, :d, :e, :l, :p)"
                ),
                {
                    "a": int(ano),
                    "v": int(entrada.get("visita") or 5),
                    "s": float(entrada["salario_minimo_brl"]),
                    "ar": entrada.get("arquivo_microdados"),
                    "d": entrada.get("dicionario"),
                    "e": entrada.get("data_extracao"),
                    "l": entrada.get("linhas_lidas"),
                    "p": entrada.get("populacao_total_estimada"),
                },
            )
            linhas = linhas_do_ano(entrada)
            conn.execute(
                text(
                    "INSERT INTO eco.pnad_distribuicao (ano, escopo, distribuicao, total_estimado, media_nominal_brl, "
                    "percentual) VALUES (:a, :e, :d, :t, :m, CAST(:p AS numeric[]))"
                ),
                [
                    {
                        "a": int(ano),
                        "e": linha["escopo"],
                        "d": linha["distribuicao"],
                        "t": linha["total"],
                        "m": linha["media"],
                        "p": json.dumps(linha["percentual"]).replace("[", "{").replace("]", "}"),
                    }
                    for linha in linhas
                ],
            )
            total += len(linhas)
        for chave, texto in (dados.get("metodologia") or {}).items():
            conn.execute(
                text(
                    "INSERT INTO eco.pnad_metodologia (chave, texto) VALUES (:c, :t) "
                    "ON CONFLICT (chave) DO UPDATE SET texto = EXCLUDED.texto"
                ),
                {"c": chave, "t": str(texto)},
            )
    logger.info("PNAD carregada: %d anos, %d distribuições (%d pulados)", len(validos), total, pulados)
    return {"anos": len(validos), "pulados": pulados, "distribuicoes": total}
