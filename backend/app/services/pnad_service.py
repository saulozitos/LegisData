"""Classes sociais por faixa de salário mínimo, a partir dos microdados da PNAD Contínua carregados em `eco.pnad_*`."""

from typing import Any, Dict, List, Optional, Tuple

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
# Teto (em salários mínimos) das classes que formam a base da pirâmide no resumo educativo (D e E)
LIMITE_BASE_SM = 4.0
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


def _carregar_ano(db: Session, ano: Optional[int]) -> Tuple[int, List[int], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Ano escolhido (padrão: o mais recente), suas informações e as distribuições; 404 se faltar qualquer parte."""
    anos = anos_disponiveis(db)
    if not anos:
        raise ErroDeDominio(404, "Microdados da PNAD ainda não processados (rode o ETL --pnad e --load-economia).")
    escolhido = ano if ano is not None else anos[-1]
    if escolhido not in anos:
        raise ErroDeDominio(404, f"Ano {escolhido} sem microdados da PNAD processados. Disponíveis: {anos}.")
    entrada = db.execute(_ANO_SQL, {"ano": escolhido}).mappings().first()
    if entrada is None or not entrada["salario_minimo_brl"]:
        raise ErroDeDominio(404, f"Ano {escolhido} sem salário mínimo de referência na PNAD processada.")
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
    return escolhido, anos, dict(entrada), distribuicoes


def _montar_classes(db: Session, salario: float, domicilios: List[float], pessoas: List[float]) -> List[Dict[str, Any]]:
    """Classes sociais com a renda em reais e o percentual exato (sem arredondar) de domicílios, para os resumos."""
    classes: List[Dict[str, Any]] = []
    for c in db.execute(_CLASSES_SQL).mappings():
        minimo, maximo = float(c["min_sm"]), float(c["max_sm"]) if c["max_sm"] is not None else None
        dom_exato = sum(domicilios[i] for i in c["faixas_pnad"])
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
                "_domicilios_exato": dom_exato,
            }
        )
    return classes


def _resumo_populacional(ano: int, classes: List[Dict[str, Any]], total_domicilios: Optional[int]) -> Dict[str, Any]:
    """
    Resumo educativo: a base (classes de renda até o teto mais baixo) e o topo (classe sem teto) saem das próprias
    classes cadastradas, não de nomes ou limites fixos no código.
    """
    teto_base = max(
        (
            c["faixa_salarios_minimos_max"]
            for c in classes
            if c["faixa_salarios_minimos_max"] is not None and c["faixa_salarios_minimos_max"] <= LIMITE_BASE_SM
        ),
        default=None,
    )
    base = [
        c
        for c in classes
        if c["faixa_salarios_minimos_max"] is not None and c["faixa_salarios_minimos_max"] <= LIMITE_BASE_SM
    ]
    topo = next((c for c in classes if c["faixa_salarios_minimos_max"] is None), None)
    pct_base = round(sum(c["_domicilios_exato"] for c in base), 1)
    nomes_base = " e ".join(c["classe"].replace("Classe ", "") for c in base)
    texto = None
    if base and topo is not None and teto_base is not None:
        pct_topo = round(topo["_domicilios_exato"], 1)
        texto = (
            f"Em {ano}, {pct_base:g}% dos domicílios brasileiros viviam com renda domiciliar total de até "
            f"{teto_base:g} salários mínimos (Classes {nomes_base}). Apenas {pct_topo:g}% estavam na {topo['classe']} "
            f"(acima de {topo['faixa_salarios_minimos_min']:g} salários mínimos), o que frequentemente distorce a "
            "percepção sobre o que é a 'classe média' no país."
        )
    return {
        "maioria_populacao_acumulada_d_e_pct": pct_base,
        "total_domicilios_estimado": total_domicilios,
        "texto_educativo": texto,
    }


def classes_sociais(db: Session, ano: Optional[int]) -> Dict[str, Any]:
    """Classes A a E do ano pedido (padrão: o mais recente). Sem microdados carregados, é erro, nunca estimativa."""
    escolhido, anos, entrada, distribuicoes = _carregar_ano(db, ano)
    salario = float(entrada["salario_minimo_brl"])
    domicilios = distribuicoes["domicilios_renda_total"]["percentual"]
    pessoas = distribuicoes["pessoas_renda_domiciliar"]["percentual"]
    classes = _montar_classes(db, salario, domicilios, pessoas)
    resumo = _resumo_populacional(escolhido, classes, distribuicoes["domicilios_renda_total"]["total_estimado"])
    for c in classes:
        c.pop("_domicilios_exato")
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
        "resumo_populacional": resumo,
        "classes": classes,
        "faixas": [dict(f) for f in db.execute(_FAIXAS_SQL).mappings()],
        "distribuicoes": distribuicoes,
    }
