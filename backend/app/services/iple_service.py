"""
Serviço do Índice de Poder Legislativo do Executivo (IPLE).

Implementação matemática e metodológica rigorosa conforme a Especificação Técnica:
- Taxa de Sucesso Legislativo (TS): |P_exec_aprov| / |P_exec|
- Taxa de Manutenção de Vetos (TMV): |V_mantidos| / |V_total_apreciados|
- IPLE: (TS + TMV) / 2 (estritamente entre 0.0 e 1.0)
- Variáveis contextuais QCA:
  - X1: Tamanho da Oposição (% cadeiras)
  - X2: Fragmentação Partidária (NEP de Laakso & Taagepera)
  - X3: Polarização Ideológica Ponderada (IPP)
- Calibragem Crisp-set QCA com pontos de corte científicos validados.
"""

import logging
import unicodedata
from typing import Any, Dict, List, Optional

from app.services.periodos import nome_do_mandato
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Parâmetros de corte Crisp-set (Tabela 4)
CORTE_TS = 0.87
CORTE_TMV = 0.70
CORTE_IPLE = 0.785
CORTE_OPOSICAO_X1 = 0.334  # > 33.4% (Quórum CPI)
CORTE_FRAGMENTACAO_X2 = 8.45  # NEP >= 8.45
CORTE_POLARIZACAO_X3 = 2.2  # IPP > 2.2


def calculate_ts(p_exec: int, p_exec_aprov: int) -> float:
    """
    Taxa de Sucesso Legislativo (TS) = |P_exec_aprov| / |P_exec|
    """
    if p_exec <= 0:
        return 0.0
    return round(min(1.0, max(0.0, p_exec_aprov / p_exec)), 4)


def calculate_tmv(v_mantidos: int, v_total_apreciados: int, fallback_ts: Optional[float] = None) -> float:
    """
    Taxa de Manutenção de Vetos (TMV) = |V_mantidos| / |V_total_apreciados|
    Regra de Consistência: Excluir vetos não apreciados pelo plenário.
    Salvaguarda: Se |V_total_apreciados| == 0, adotar 1.0 ou imputar TS conforme literatura.
    """
    if v_total_apreciados <= 0:
        return fallback_ts if fallback_ts is not None else 1.0
    return round(min(1.0, max(0.0, v_mantidos / v_total_apreciados)), 4)


def calculate_iple(ts: float, tmv: float) -> float:
    """
    Índice de Poder Legislativo do Executivo (IPLE) = (TS + TMV) / 2
    Varia estritamente de 0.0 a 1.0.
    """
    return round(min(1.0, max(0.0, (ts + tmv) / 2.0)), 4)


def calculate_nep(bancadas: List[Dict[str, Any]]) -> float:
    """
    Fragmentação Partidária - Número Efetivo de Partidos (NEP de Laakso & Taagepera):
    NEP = 1 / sum(p_i^2)
    """
    total = sum(b.get("cadeiras", 0) for b in bancadas)
    if total <= 0:
        return 1.0
    sum_sq = sum(((b.get("cadeiras", 0) / total) ** 2) for b in bancadas)
    if sum_sq <= 0:
        return 1.0
    return round(1.0 / sum_sq, 2)


def calculate_ipp(bancadas: List[Dict[str, Any]], scale: Dict[str, float]) -> float:
    """
    Polarização Ideológica Ponderada (IPP):
    IPP = sum(p_i * (x_i - mean_x)^2)
    onde p_i é a proporção de cadeiras, x_i é a escala de 1 a 10 e mean_x é a média ponderada.
    """
    scale = {chave_sigla(k): v for k, v in scale.items()}
    valid_b = [b for b in bancadas if chave_sigla(b.get("partido", "")) in scale and b.get("cadeiras", 0) > 0]
    total = sum(b["cadeiras"] for b in valid_b)
    if total <= 0:
        return 0.0

    mean_x = sum((b["cadeiras"] / total) * scale[chave_sigla(b["partido"])] for b in valid_b)
    ipp = sum((b["cadeiras"] / total) * ((scale[chave_sigla(b["partido"])] - mean_x) ** 2) for b in valid_b)
    return round(ipp, 2)


def calculate_opposition_share(opposition_seats: int, total_seats: int) -> float:
    """
    Tamanho da Oposição (X1) = Total Oposição / Total Assentos
    """
    if total_seats <= 0:
        return 0.0
    return round(min(1.0, max(0.0, opposition_seats / total_seats)), 4)


def _item(score: Optional[float], corte: float, ativo: Optional[bool], alto: str, baixo: str) -> Dict[str, Any]:
    """Item da calibragem; score ausente vira `crisp_val` None e classificação "Indisponível" (nunca um 0 inventado)."""
    if score is None:
        return {"score": None, "corte": corte, "crisp_val": None, "classificacao": "Indisponível"}
    return {"score": score, "corte": corte, "crisp_val": int(bool(ativo)), "classificacao": alto if ativo else baixo}


def calibrate_crisp_set(
    ts: float, tmv: float, iple: float, x1: Optional[float], x2: Optional[float], x3: Optional[float]
) -> Dict[str, Any]:
    """
    Classificação categórica booleana (Crisp-set QCA) conforme os limiares da Tabela 4.
    As variáveis contextuais (X1, X2, X3) podem faltar quando as bancadas não foram levantadas.
    """
    return {
        "ts": _item(ts, CORTE_TS, ts >= CORTE_TS, "Sucesso Alto", "Sucesso Baixo"),
        "tmv": _item(tmv, CORTE_TMV, tmv >= CORTE_TMV, "Manutenção Alta", "Manutenção Baixa"),
        "iple": _item(iple, CORTE_IPLE, iple >= CORTE_IPLE, "Executivo Forte / Poderoso", "Executivo Fraco"),
        "oposicao_x1": _item(
            x1,
            CORTE_OPOSICAO_X1,
            x1 is not None and x1 > CORTE_OPOSICAO_X1,
            "Oposição Numerosa (Quórum CPI)",
            "Oposição Fraca",
        ),
        "fragmentacao_x2": _item(
            x2,
            CORTE_FRAGMENTACAO_X2,
            x2 is not None and x2 >= CORTE_FRAGMENTACAO_X2,
            "Parlamento Fragmentado",
            "Baixa Fragmentação",
        ),
        "polarizacao_x3": _item(
            x3,
            CORTE_POLARIZACAO_X3,
            x3 is not None and x3 > CORTE_POLARIZACAO_X3,
            "Parlamento Polarizado",
            "Baixa Polarização",
        ),
    }


CASAS_IPLE = {"CAMARA": "CAMARA_DOS_DEPUTADOS", "SENADO": "SENADO_FEDERAL"}

_PRODUCAO_SQL = text(
    """
    SELECT mp.slug, p.nome_exibicao, mp.rotulo, m.inicio, m.fim, pe.proposicoes_executivo, pe.proposicoes_aprovadas,
           pe.vetos_apreciados, pe.vetos_mantidos, pe.vetos_pendentes, pe.oposicao_cadeiras_camara,
           pe.total_cadeiras_camara
    FROM leg.producao_executivo pe
    JOIN core.mandato m ON m.id = pe.mandato_id
    JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id
    JOIN core.pessoa p ON p.id = m.pessoa_id
    ORDER BY m.inicio
    """
)

_ESCALA_SQL = text(
    """
    SELECT p.sigla_normalizada, pp.valor
    FROM core.partido_posicao_ideologica pp JOIN core.partido p ON p.id = pp.partido_id
    WHERE pp.escala = 'ESCALA_1_10'
    """
)


def chave_sigla(sigla: str) -> str:
    """Chave de comparação de siglas: sem acento, sem espaço, maiúsculas ('PC do B' e 'PCdoB' são o mesmo partido)."""
    sem_acento = unicodedata.normalize("NFKD", sigla).encode("ascii", "ignore").decode()
    return sem_acento.replace(" ", "").upper()


def escala_ideologica(db: Session) -> Dict[str, float]:
    """Escala 1 (esquerda) a 10 (direita) por partido, da tabela `core.partido_posicao_ideologica`."""
    return {chave_sigla(sigla): float(valor) for sigla, valor in db.execute(_ESCALA_SQL)}


def _periodo(inicio: Any, fim: Any) -> str:
    """Anos do mandato; o fim é exclusivo (1º de janeiro do sucessor), então o último ano é o anterior."""
    ate = fim.year - 1 if fim else "Presente"
    return f"{inicio.year} - {ate}"


def _producao_do_mandato(db: Session, mandate_id: str) -> Optional[Dict[str, Any]]:
    for r in db.execute(_PRODUCAO_SQL).mappings():
        if r["slug"] == mandate_id:
            return dict(r)
    return None


def _lista_de_mandatos(db: Session) -> List[str]:
    return [r["slug"] for r in db.execute(_PRODUCAO_SQL).mappings()]


def get_mandate_iple(db: Session, mandate_id: str, casa: str = "CAMARA") -> Optional[Dict[str, Any]]:
    """
    Calcula e consolida os indicadores do IPLE, as variáveis contextuais e a calibragem QCA de um mandato.

    A produção do Executivo vem de `leg.producao_executivo`; as bancadas, de `leg.bancada_mandato` na Casa pedida.
    Quando a oposição ou as bancadas não existem na base, a variável contextual sai `None` (nunca um valor inventado).
    """
    raw = _producao_do_mandato(db, mandate_id)
    if not raw:
        return None

    p_exec = raw["proposicoes_executivo"]
    p_exec_aprov = raw["proposicoes_aprovadas"]
    v_total = raw["vetos_apreciados"]
    v_mantidos = raw["vetos_mantidos"]
    v_pendentes = raw["vetos_pendentes"] or 0

    # No mandato corrente, as proposições reais do Executivo na base podem superar a curadoria
    if mandate_id == "lula-2023":
        try:
            from app.models.leg import Proposicao

            db_exec_props = db.query(Proposicao).filter(Proposicao.iniciativa_executivo.is_(True)).all()
            db_substantivas = [
                p
                for p in db_exec_props
                if not (p.ementa and any(kw in p.ementa.lower() for kw in ("denominar", "dia nacional", "homenageia")))
            ]
            db_aprov = [
                p for p in db_substantivas if p.status_codigo in ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA")
            ]
            if db_substantivas:
                p_exec = max(p_exec, len(db_substantivas))
                p_exec_aprov = max(p_exec_aprov, len(db_aprov))
        except Exception as e:  # noqa: BLE001 - enriquecimento opcional; a curadoria segue valendo
            logger.debug("Falha ao consultar proposicoes do banco para calculo do IPLE: %s", e)

    ts = calculate_ts(p_exec, p_exec_aprov)
    tmv = calculate_tmv(v_mantidos, v_total, fallback_ts=ts)
    iple = calculate_iple(ts, tmv)

    from app.services import composicao_service

    codigo_casa = CASAS_IPLE.get(casa, CASAS_IPLE["CAMARA"])
    bancadas = composicao_service.bancadas_da_casa(db, mandate_id, codigo_casa)
    total_cadeiras = composicao_service.total_de_cadeiras(db, mandate_id, codigo_casa)
    if total_cadeiras is None and casa == "CAMARA":
        total_cadeiras = raw["total_cadeiras_camara"]
    oposicao = composicao_service.cadeiras_da_oposicao(bancadas)
    if oposicao is None and casa == "CAMARA":
        oposicao = raw["oposicao_cadeiras_camara"]  # curadoria: sobra quando as bancadas não foram classificadas

    x1 = calculate_opposition_share(oposicao, total_cadeiras) if oposicao is not None and total_cadeiras else None
    com_cadeiras = [b for b in bancadas if b.get("cadeiras")]
    x2 = calculate_nep(com_cadeiras) if com_cadeiras else None
    x3 = calculate_ipp(com_cadeiras, escala_ideologica(db)) if com_cadeiras else None

    crisp = calibrate_crisp_set(ts, tmv, iple, x1, x2, x3)

    return {
        "mandato_id": mandate_id,
        "presidente": nome_do_mandato(raw["nome_exibicao"], raw["rotulo"]),
        "periodo": _periodo(raw["inicio"], raw["fim"]),
        "indicadores_base": {
            "proposicoes_executivo_total": p_exec,
            "proposicoes_executivo_aprovadas": p_exec_aprov,
            "vetos_total_apreciados": v_total,
            "vetos_mantidos": v_mantidos,
            "vetos_pendentes_pauta": v_pendentes,
            "taxa_sucesso_ts": ts,
            "taxa_manutencao_vetos_tmv": tmv,
            "iple_score": iple,
        },
        "variaveis_contextuais": {
            "tamanho_oposicao_x1": x1,
            "oposicao_cadeiras": oposicao,
            "total_cadeiras": total_cadeiras,
            "fragmentacao_nep_x2": x2,
            "polarizacao_ipp_x3": x3,
        },
        "calibragem_crisp_set": crisp,
        "classificacao_geral": crisp["iple"]["classificacao"],
    }


def get_all_mandates_iple(db: Session) -> List[Dict[str, Any]]:
    """IPLE de todos os mandatos presidenciais com produção do Executivo carregada."""
    resultados = (get_mandate_iple(db, slug) for slug in _lista_de_mandatos(db))
    return [r for r in resultados if r]
