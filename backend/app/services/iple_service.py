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
from typing import Any, Dict, Iterable, List, Optional

from app.core.errors import ErroDeDominio
from app.models.leg import Proposicao
from app.services import bancadas_service
from app.services.periodos import nome_do_mandato, rotulo_do_periodo
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

STATUS_APROVADA = ("APROVADA_E_SANCIONADA", "APROVADA_E_PROMULGADA")

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


def calculate_ipp(bancadas: List[Dict[str, Any]], scale: Dict[str, float]) -> Optional[float]:
    """
    Polarização Ideológica Ponderada (IPP):
    IPP = sum(p_i * (x_i - mean_x)^2)
    onde p_i é a proporção de cadeiras, x_i é a escala de 1 a 10 e mean_x é a média ponderada. Só entram partidos com
    posição na escala; se nenhum tiver, o IPP é indeterminado (`None`), nunca zero.
    """
    scale = {chave_sigla(k): v for k, v in scale.items()}
    valid_b = [b for b in bancadas if chave_sigla(b.get("partido", "")) in scale and b.get("cadeiras", 0) > 0]
    total = sum(b["cadeiras"] for b in valid_b)
    if total <= 0:
        return None

    mean_x = sum((b["cadeiras"] / total) * scale[chave_sigla(b["partido"])] for b in valid_b)
    ipp = sum((b["cadeiras"] / total) * ((scale[chave_sigla(b["partido"])] - mean_x) ** 2) for b in valid_b)
    return round(ipp, 2)


def cobertura_da_escala(bancadas: List[Dict[str, Any]], scale: Dict[str, float]) -> Optional[float]:
    """Percentual das cadeiras cujo partido tem posição na escala ideológica (base do IPP); None sem cadeiras."""
    total = sum(b["cadeiras"] for b in bancadas)
    if total <= 0:
        return None
    chaves = {chave_sigla(k) for k in scale}
    coberto = sum(b["cadeiras"] for b in bancadas if chave_sigla(b.get("partido", "")) in chaves)
    return round(coberto / total * 100, 1)


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


_PRODUCAO_SQL = text(
    """
    SELECT mp.slug, p.nome_exibicao, mp.rotulo, m.inicio, m.fim, pe.proposicoes_executivo, pe.proposicoes_aprovadas,
           pe.vetos_apreciados, pe.vetos_mantidos, pe.vetos_pendentes, pe.oposicao_cadeiras_camara,
           pe.total_cadeiras_camara
    FROM leg.producao_executivo pe
    JOIN core.mandato m ON m.id = pe.mandato_id
    JOIN core.mandato_presidencial mp ON mp.mandato_id = m.id
    JOIN core.pessoa p ON p.id = m.pessoa_id
    WHERE (CAST(:slug AS text) IS NULL OR mp.slug = :slug)
    ORDER BY m.inicio
    """
)

_ESCALA_SQL = text(
    """
    SELECT p.sigla_normalizada, pp.valor
    FROM core.partido_posicao_ideologica pp JOIN core.partido p ON p.id = pp.partido_id
    WHERE pp.escala = 'ESCALA_1_10' AND pp.valor IS NOT NULL AND p.sigla_normalizada IS NOT NULL
    """
)

# Palavras que marcam proposição simbólica (homenagens, datas comemorativas): não contam como "substantiva".
_PALAVRAS_SIMBOLICAS = ("denominar", "dia nacional", "homenageia")


def chave_sigla(sigla: str) -> str:
    """Chave de comparação de siglas: sem acento, sem espaço, maiúsculas ('PC do B' e 'PCdoB' são o mesmo partido)."""
    sem_acento = unicodedata.normalize("NFKD", sigla).encode("ascii", "ignore").decode()
    return sem_acento.replace(" ", "").upper()


def escala_ideologica(db: Session) -> Dict[str, float]:
    """Escala 1 (esquerda) a 10 (direita) por partido, da tabela `core.partido_posicao_ideologica`."""
    return {chave_sigla(sigla): float(valor) for sigla, valor in db.execute(_ESCALA_SQL)}


def producoes(db: Session, slug: Optional[str] = None) -> List[Dict[str, Any]]:
    """Produção legislativa do Executivo (insumo do IPLE) de um mandato ou de todos, do mais antigo ao mais recente."""
    return [dict(r) for r in db.execute(_PRODUCAO_SQL, {"slug": slug}).mappings()]


def _contagem_com_proposicoes_reais(db: Session, raw: Dict[str, Any]) -> Dict[str, int]:
    """
    Proposições do Executivo e aprovadas: a curadoria, ou a contagem real da base quando esta a supera (mandato em
    curso, sem `fim`). Falha de consulta não derruba o IPLE: usa um savepoint e fica com a curadoria.
    """
    contagem = {"total": raw["proposicoes_executivo"], "aprovadas": raw["proposicoes_aprovadas"]}
    if raw["fim"] is not None:
        return contagem
    try:
        with db.begin_nested():
            # Só as proposições apresentadas dentro do mandato (a base cobre desde 1995)
            base = db.query(Proposicao).filter(
                Proposicao.iniciativa_executivo.is_(True), Proposicao.data_apresentacao >= raw["inicio"]
            )
            for palavra in _PALAVRAS_SIMBOLICAS:
                base = base.filter(~func.coalesce(func.lower(Proposicao.ementa), "").contains(palavra))
            total = base.count()
            aprovadas = base.filter(Proposicao.status_codigo.in_(STATUS_APROVADA)).count()
        contagem = {"total": max(contagem["total"], total), "aprovadas": max(contagem["aprovadas"], aprovadas)}
    except SQLAlchemyError as exc:
        logger.warning("Falha ao contar proposições do Executivo para o IPLE; usando a curadoria: %s", exc)
    return contagem


def calcular_iple(
    raw: Dict[str, Any],
    contagem: Dict[str, int],
    total_cadeiras: Optional[int],
    bancadas: List[Dict[str, Any]],
    escala: Dict[str, float],
    oposicao_reserva: Optional[int] = None,
) -> Dict[str, Any]:
    """
    IPLE, variáveis contextuais e calibragem QCA de um mandato numa Casa, a partir dos dados já lidos.

    Quando as bancadas ou a oposição não foram levantadas (ou só em parte), a variável contextual sai `None` (nunca um
    valor inventado ou um piso apresentado como total); `oposicao_reserva` é a oposição curada que a Câmara usa nesse caso.
    """
    ts = calculate_ts(contagem["total"], contagem["aprovadas"])
    tmv = calculate_tmv(raw["vetos_mantidos"], raw["vetos_apreciados"], fallback_ts=ts)
    iple = calculate_iple(ts, tmv)

    oposicao = bancadas_service.cadeiras_da_oposicao(bancadas, total_cadeiras)
    if oposicao is None:
        oposicao = oposicao_reserva

    x1 = calculate_opposition_share(oposicao, total_cadeiras) if oposicao is not None and total_cadeiras else None
    com_cadeiras = [b for b in bancadas if b.get("cadeiras")]
    x2 = calculate_nep(com_cadeiras) if com_cadeiras else None
    x3 = calculate_ipp(com_cadeiras, escala) if com_cadeiras else None
    crisp = calibrate_crisp_set(ts, tmv, iple, x1, x2, x3)
    return {
        "mandato_id": raw["slug"],
        "presidente": nome_do_mandato(raw["nome_exibicao"], raw["rotulo"]),
        "periodo": rotulo_do_periodo(raw["inicio"], raw["fim"]),
        "indicadores_base": {
            "proposicoes_executivo_total": contagem["total"],
            "proposicoes_executivo_aprovadas": contagem["aprovadas"],
            "vetos_total_apreciados": raw["vetos_apreciados"],
            "vetos_mantidos": raw["vetos_mantidos"],
            "vetos_pendentes_pauta": raw["vetos_pendentes"] or 0,
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
            "cobertura_ipp_pct": cobertura_da_escala(com_cadeiras, escala),
        },
        "calibragem_crisp_set": crisp,
        "classificacao_geral": crisp["iple"]["classificacao"],
    }


def iple_das_casas(
    db: Session,
    raw: Dict[str, Any],
    escala: Optional[Dict[str, float]] = None,
    casas: Optional[Iterable[str]] = None,
    metas: Optional[Dict[str, Dict[str, Any]]] = None,
    linhas: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    IPLE do mandato em cada Casa pedida (padrão: `camara` e `senado`). Bancadas e totais são lidos uma única vez, ou
    reaproveitados de quem já os leu (`metas` e `linhas`). Só a Câmara usa os totais e a oposição curados da produção.
    """
    escala = escala if escala is not None else escala_ideologica(db)
    contagem = _contagem_com_proposicoes_reais(db, raw)
    metas = metas if metas is not None else bancadas_service.composicoes(db, raw["slug"])
    linhas = linhas if linhas is not None else bancadas_service.linhas_de_bancada(db, raw["slug"])
    resultado = {}
    for casa in casas or bancadas_service.CASAS:
        codigo = bancadas_service.CASAS[casa]
        meta = metas.get(codigo)
        total = int(meta["total_cadeiras"]) if meta else None
        reserva = None
        if casa == "camara":
            total = total if total is not None else raw["total_cadeiras_camara"]
            reserva = raw["oposicao_cadeiras_camara"]
        bancadas = bancadas_service.bancadas_exibidas([r for r in linhas if r["casa_codigo"] == codigo], total or 0)
        resultado[casa] = calcular_iple(raw, contagem, total, bancadas, escala, reserva)
    return resultado


def get_mandate_iple(db: Session, mandate_id: str, casa: str = "camara") -> Optional[Dict[str, Any]]:
    """IPLE de um mandato na Casa pedida (`camara` ou `senado`); None se o mandato não tem produção carregada."""
    if casa not in bancadas_service.CASAS:
        raise ErroDeDominio(422, f"Casa inválida '{casa}'. Use: {', '.join(bancadas_service.CASAS)}.")
    lista = producoes(db, mandate_id)
    return iple_das_casas(db, lista[0], casas=(casa,))[casa] if lista else None


def get_all_mandates_iple(db: Session) -> List[Dict[str, Any]]:
    """IPLE (Câmara) de todos os mandatos com produção do Executivo carregada; a escala ideológica é lida uma vez."""
    escala = escala_ideologica(db)
    return [iple_das_casas(db, raw, escala, casas=("camara",))["camara"] for raw in producoes(db)]
