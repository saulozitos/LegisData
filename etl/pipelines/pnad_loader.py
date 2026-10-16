"""
Carga da distribuição de renda da PNAD Contínua em `eco.pnad_*` a partir de `pnad_faixas_salario_minimo.json`.

O arquivo é calculado pelo ETL (`--pnad`) dos microdados do IBGE. Cada ano é regravado por inteiro; ano inválido (sem
visita, salário mínimo ou as 8 faixas) é pulado e contado. Arquivo sem nenhum ano válido não apaga a base.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from etl.config import PROCESSED_DATA_DIR
from etl.pipelines.loader_helpers import (  # noqa: F401 - os validadores seguem acessíveis daqui
    ano_pnad_valido,
    linhas_pnad_do_ano,
    percentual_valido,
)
from etl.utils.bootstrap import ensure_backend_on_path
from etl.utils.datafiles import load_json

ensure_backend_on_path()

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

logger = logging.getLogger("PnadLoader")


def carregar(engine: Engine, processed_dir: Optional[Path] = None) -> Dict[str, int]:
    arquivo = Path(processed_dir or PROCESSED_DATA_DIR) / "pnad_faixas_salario_minimo.json"
    dados = load_json(arquivo)
    if not isinstance(dados, dict) or not isinstance(dados.get("anos"), dict):
        raise FileNotFoundError(f"Arquivo da PNAD ausente ou inválido: {arquivo}")
    validos = {ano: e for ano, e in dados["anos"].items() if ano_pnad_valido(ano, e)}
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
                    "v": int(entrada["visita"]),
                    "s": float(entrada["salario_minimo_brl"]),
                    "ar": entrada.get("arquivo_microdados"),
                    "d": entrada.get("dicionario"),
                    "e": entrada.get("data_extracao"),
                    "l": entrada.get("linhas_lidas"),
                    "p": entrada.get("populacao_total_estimada"),
                },
            )
            linhas = linhas_pnad_do_ano(entrada)
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
                        "p": linha["percentual"],
                    }
                    for linha in linhas
                ],
            )
            total += len(linhas)
        metodologia = dados.get("metodologia")
        for chave, texto in metodologia.items() if isinstance(metodologia, dict) else []:
            if not isinstance(texto, str) or not texto.strip():
                continue  # texto ausente não vira a string "None"
            conn.execute(
                text(
                    "INSERT INTO eco.pnad_metodologia (chave, texto) VALUES (:c, :t) "
                    "ON CONFLICT (chave) DO UPDATE SET texto = EXCLUDED.texto"
                ),
                {"c": chave, "t": texto},
            )
    logger.info("PNAD carregada: %d anos, %d distribuições (%d pulados)", len(validos), total, pulados)
    return {"anos": len(validos), "pulados": pulados, "distribuicoes": total}
