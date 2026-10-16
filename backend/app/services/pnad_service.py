"""Classes sociais por faixa de salário mínimo, a partir dos microdados da PNAD Contínua carregados em `eco.pnad_*`."""

from typing import Any, Dict, List, Optional

from app.core.errors import ErroDeDominio
from sqlalchemy import text
from sqlalchemy.orm import Session

_ANOS_SQL = text("SELECT ano FROM eco.pnad_ano ORDER BY ano")
_ANO_SQL = text("SELECT * FROM eco.pnad_ano WHERE ano = :ano")
_CLASSES_SQL = text("SELECT * FROM eco.classe_social ORDER BY ordem")
_FAIXAS_SQL = text("SELECT posicao, codigo AS id, rotulo, min_sm, max_sm FROM eco.pnad_faixa ORDER BY posicao")
_DISTRIBUICOES_SQL = text(
    """
    SELECT distribuicao, total_estimado, media_nominal_brl, percentual
    FROM eco.pnad_distribuicao WHERE ano = :ano AND escopo = 'BR'
    """
)
_METODOLOGIA_SQL = text("SELECT chave, texto FROM eco.pnad_metodologia")


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _renda_da_classe(minimo: float, maximo: Optional[float], salario: float) -> Dict[str, Any]:
    if maximo is None:
        formatada = f"Acima de {_brl(minimo * salario)}"
    elif minimo == 0:
        formatada = f"Até {_brl(maximo * salario)}"
    else:
        formatada = f"{_brl(minimo * salario)} a {_brl(maximo * salario)}"
    return {
        "renda_familiar_min_brl": round(minimo * salario, 2),
        "renda_familiar_max_brl": round(maximo * salario, 2) if maximo is not None else None,
        "faixa_renda_formatada": formatada,
    }


def anos_disponiveis(db: Session) -> List[int]:
    return [int(r[0]) for r in db.execute(_ANOS_SQL)]


def classes_sociais(db: Session, ano: Optional[int]) -> Dict[str, Any]:
    """Classes A a E do ano pedido (padrão: o mais recente). Sem microdados carregados, é erro, nunca estimativa."""
    anos = anos_disponiveis(db)
    if not anos:
        raise ErroDeDominio(404, "Microdados da PNAD ainda não processados (rode o ETL --pnad e --load-economia).")
    escolhido = ano if ano is not None else anos[-1]
    if escolhido not in anos:
        raise ErroDeDominio(404, f"Ano {escolhido} sem microdados da PNAD processados. Disponíveis: {anos}.")
    entrada = db.execute(_ANO_SQL, {"ano": escolhido}).mappings().first()
    if entrada is None or not entrada["salario_minimo_brl"]:
        raise ErroDeDominio(404, f"Ano {escolhido} sem salário mínimo de referência na PNAD processada.")
    salario = float(entrada["salario_minimo_brl"])
    distribuicoes = {
        r["distribuicao"]: {
            "total_estimado": int(r["total_estimado"]) if r["total_estimado"] is not None else None,
            "percentual": [float(p) for p in r["percentual"]],
            "media_nominal_brl": float(r["media_nominal_brl"]) if r["media_nominal_brl"] is not None else None,
        }
        for r in db.execute(_DISTRIBUICOES_SQL, {"ano": escolhido}).mappings()
    }
    if "domicilios_renda_total" not in distribuicoes or "pessoas_renda_domiciliar" not in distribuicoes:
        raise ErroDeDominio(404, f"Ano {escolhido} com distribuição de renda incompleta na PNAD processada.")
    domicilios = distribuicoes["domicilios_renda_total"]["percentual"]
    pessoas = distribuicoes["pessoas_renda_domiciliar"]["percentual"]

    classes: List[Dict[str, Any]] = []
    percentual_exato: Dict[str, float] = {}
    for c in db.execute(_CLASSES_SQL).mappings():
        minimo, maximo = float(c["min_sm"]), float(c["max_sm"]) if c["max_sm"] is not None else None
        dom_exato = sum(domicilios[i] for i in c["faixas_pnad"])
        percentual_exato[c["codigo"]] = dom_exato
        classes.append(
            {
                "classe": c["codigo"],
                "faixa_salarios_minimos": c["faixa_rotulo"],
                "faixa_salarios_minimos_min": minimo,
                "faixa_salarios_minimos_max": maximo,
                **_renda_da_classe(minimo, maximo, salario),
                "percentual_populacao": round(sum(pessoas[i] for i in c["faixas_pnad"]), 1),
                "percentual_domicilios": round(dom_exato, 1),
                "descricao": c["descricao"],
                "cor": c["cor_hex"],
                "destaque": c["destaque"],
            }
        )
    pct_d_e = round(sum(percentual_exato.get(c, 0.0) for c in ("Classe D", "Classe E")), 1)
    pct_a = round(percentual_exato.get("Classe A", 0.0), 1)
    return {
        "origem": "pnad",
        "salario_minimo_referencia_brl": salario,
        "ano_referencia": escolhido,
        "anos_disponiveis": anos,
        "fonte": (
            f"IBGE — PNAD Contínua anual {escolhido} (microdados, visita {entrada['visita']}), calculado pelo "
            f"LegisData com o peso amostral calibrado; salário mínimo de {escolhido}: {_brl(salario)}. "
            "Classes por rendimento habitual domiciliar total em múltiplos do salário mínimo."
        ),
        "metodologia": {r["chave"]: r["texto"] for r in db.execute(_METODOLOGIA_SQL).mappings()},
        "resumo_populacional": {
            "maioria_populacao_acumulada_d_e_pct": pct_d_e,
            "total_domicilios_estimado": distribuicoes["domicilios_renda_total"]["total_estimado"],
            "texto_educativo": (
                f"Em {escolhido}, {pct_d_e:g}% dos domicílios brasileiros viviam com renda domiciliar total de até 4 "
                f"salários mínimos (Classes D e E). Apenas {pct_a:g}% estavam na Classe A (acima de 20 salários "
                "mínimos), o que frequentemente distorce a percepção sobre o que é a 'classe média' no país."
            ),
        },
        "classes": classes,
        "faixas": [dict(f) for f in db.execute(_FAIXAS_SQL).mappings()],
        "distribuicoes": distribuicoes,
    }
