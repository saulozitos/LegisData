"""
Extrator de REMUNERAÇÃO de parlamentares a partir de fontes oficiais.

1. Senado Federal (nominal, contracheque real):
   GET https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/remuneracoes/{ano}/{mes}
   (OpenAPI: https://adm.senado.gov.br/adm-dadosabertos/v3/api-docs)
   - Uma linha por (servidor/parlamentar, tipo_folha). Há várias folhas no mês
     ("Normal", "Suplementar" com 13º etc.): somamos por pessoa/mês porque a tabela
     remuneracoes_politicos é única por (político, ano, mês). A quebra por folha
     fica no JSON processado.
   - Vínculo: nome civil completo normalizado (sem acento/caixa) contra
     ``nome_civil`` de senadores_senado.json. Nomes que aparecem com mais de um
     ``sequencial`` no mês são descartados como ambíguos (homônimos).
   - Valores vêm como string BR ("46.366,19").

2. Câmara dos Deputados: o CSV mensal da Câmara é anonimizado ("Deputado NNNN")
   e o número não corresponde à matrícula; NÃO há como atribuir contracheque a uma
   pessoa. Não gravamos nada individual. A API expõe o subsídio constitucional de
   referência (backend/app/core/subsidios.py), que este script também exporta
   para subsidios_referencia.json, com o ato normativo citado.

CEAP NÃO é remuneração (é reembolso de despesa) e nunca é somada aqui.

Uso:
  PYTHONPATH=. python etl/extractors/remuneracao_extractor.py --de 2025-02 --ate 2026-08
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from etl.http_oficial import CachedHttpClient  # noqa: E402
from etl.vinculos import normalizar  # noqa: E402

logger = logging.getLogger("RemuneracaoExtractor")

SENADO_REMUNERACOES_URL = "https://adm.senado.gov.br/adm-dadosabertos/api/v1/servidores/remuneracoes/{ano}/{mes}"
FONTE_SENADO = "Senado Federal - ADM Dados Abertos (servidores/remuneracoes)"

# Composição verificada em 31.976 linhas reais (12/2025 e 08/2026):
# remuneracao_liquida == soma(PROVENTOS) + soma(DESCONTOS), sem exceção.
PROVENTOS = (
    "remuneracao_basica", "vantagens_pessoais", "funcao_comissionada",
    "gratificacao_natalina", "horas_extras", "outras_eventuais", "abono_permanencia",
)
DESCONTOS = ("reversao_teto_constitucional", "imposto_renda", "previdencia", "faltas")
# Pagos à parte, fora do líquido (indenizações): diárias, auxílios, vantagens indenizatórias.
INDENIZATORIAS = ("diarias", "auxilios", "vantagens_indenizatorias")
CAMPOS_VALOR = PROVENTOS + DESCONTOS + INDENIZATORIAS + ("remuneracao_liquida",)


def parse_valor_br(valor) -> Decimal:
    """'46.366,19' -> Decimal('46366.19'); '-7.600,54' -> negativo; vazio -> 0.

    Também aceita números já convertidos (int/float/Decimal). Levanta ValueError
    para texto que não é número no formato brasileiro.
    """
    if valor is None:
        return Decimal("0")
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    texto = str(valor).strip().replace("R$", "").replace("\u00a0", "").replace(" ", "")
    if texto in ("", "-"):
        return Decimal("0")
    negativo = texto.startswith("(") and texto.endswith(")")
    texto = texto.strip("()")
    texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"valor monetário inválido: {valor!r}") from exc
    return -numero if negativo else numero


def resumir_folha(linha: dict) -> dict:
    v = {c: parse_valor_br(linha.get(c)) for c in CAMPOS_VALOR}
    bruto = sum((v[c] for c in PROVENTOS), Decimal("0"))
    descontos = sum((v[c] for c in DESCONTOS), Decimal("0"))
    indenizatorias = sum((v[c] for c in INDENIZATORIAS), Decimal("0"))
    return {
        "tipo_folha": linha.get("tipo_folha"),
        "bruto": bruto,
        "descontos": descontos,
        "liquido": v["remuneracao_liquida"],
        "indenizatorias": indenizatorias,
        "liquido_confere": (bruto + descontos) == v["remuneracao_liquida"],
    }


def agregar_folhas_senado(
    linhas: Iterable[dict],
    nomes_alvo: Dict[str, int],
) -> Tuple[List[dict], Dict[str, int]]:
    """Soma as folhas de cada parlamentar por (ano, mês).

    ``nomes_alvo``: nome civil NORMALIZADO -> senado_id. Linhas de outras pessoas
    são ignoradas. Retorna (registros, estatísticas).
    """
    por_nome_mes: Dict[Tuple[str, int, int], List[dict]] = defaultdict(list)
    for linha in linhas:
        nome = normalizar(linha.get("nome"))
        if nome in nomes_alvo:
            por_nome_mes[(nome, int(linha["ano"]), int(linha["mes"]))].append(linha)

    stats: Counter = Counter()
    registros = []
    for (nome, ano, mes), grupo in sorted(por_nome_mes.items()):
        sequenciais = {g.get("sequencial") for g in grupo}
        if len(sequenciais) > 1:
            stats["descartado_homonimo"] += 1
            continue
        folhas = [resumir_folha(g) for g in grupo]
        if not all(f["liquido_confere"] for f in folhas):
            stats["aviso_liquido_nao_confere"] += 1
        total = lambda k: sum((f[k] for f in folhas), Decimal("0"))  # noqa: E731
        registros.append({
            "senado_id": nomes_alvo[nome],
            "nome_folha": grupo[0].get("nome"),
            "sequencial": next(iter(sequenciais)),
            "ano": ano,
            "mes": mes,
            "salario_bruto": str(total("bruto")),
            "descontos_obrigatorios": str(total("descontos")),
            "salario_liquido": str(total("liquido")),
            "outros_beneficios": str(total("indenizatorias")),
            "folhas": [
                {"tipo_folha": f["tipo_folha"], "bruto": str(f["bruto"]),
                 "descontos": str(f["descontos"]), "liquido": str(f["liquido"]),
                 "indenizatorias": str(f["indenizatorias"])}
                for f in folhas
            ],
        })
        stats["registros"] += 1
    stats["sem_folha_no_periodo"] = len(set(nomes_alvo) - {k[0] for k in por_nome_mes})
    return registros, dict(stats)


def meses(de: Tuple[int, int], ate: Tuple[int, int]) -> List[Tuple[int, int]]:
    (a, m), saida = de, []
    while (a, m) <= ate:
        saida.append((a, m))
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return saida


class RemuneracaoExtractor:
    def __init__(self, raw_dir: Path = RAW_DATA_DIR / "remuneracao", out_dir: Path = PROCESSED_DATA_DIR,
                 min_interval_s: float = 1.1):
        self.http = CachedHttpClient(raw_dir, min_interval_s=min_interval_s, timeout_s=180)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _senadores_alvo(self) -> Dict[str, int]:
        arq = self.out_dir / "senadores_senado.json"
        if not arq.exists():
            raise FileNotFoundError(f"{arq} não existe: rode antes a extração do Senado (--senado).")
        senadores = json.loads(arq.read_text(encoding="utf-8"))
        pares = [(normalizar(s.get("nome_civil")), int(s["senado_id"])) for s in senadores if s.get("nome_civil")]
        alvo: Dict[str, int] = {}
        for nome, sid in pares:
            if nome in alvo and alvo[nome] != sid:
                logger.warning("Nome civil repetido entre senadores, ignorado: %s", nome)
                alvo[nome] = -1
            else:
                alvo[nome] = sid
        return {n: s for n, s in alvo.items() if s != -1}

    def extrair_senado(self, de: Tuple[int, int], ate: Tuple[int, int]) -> dict:
        alvo = self._senadores_alvo()
        todos, stats_total = [], Counter()
        for ano, mes in meses(de, ate):
            corpo = self.http.get_bytes(SENADO_REMUNERACOES_URL.format(ano=ano, mes=mes),
                                        accept="application/json", suffix=".json")
            linhas = json.loads(corpo.decode("utf-8")) or []
            regs, stats = agregar_folhas_senado(linhas, alvo)
            todos.extend(regs)
            stats_total.update({k: v for k, v in stats.items() if k != "sem_folha_no_periodo"})
            logger.info("Senado %02d/%d: %d linhas na folha, %d parlamentares vinculados", mes, ano, len(linhas), len(regs))
        resultado = {
            "fonte": FONTE_SENADO,
            "fonte_url": SENADO_REMUNERACOES_URL,
            "coletado_em": datetime.now().isoformat(timespec="seconds"),
            "periodo": {"de": "%d-%02d" % de, "ate": "%d-%02d" % ate},
            "metodo_vinculo": "nome civil completo normalizado (senadores_senado.json); homônimos descartados",
            "composicao": {"bruto": list(PROVENTOS), "descontos": list(DESCONTOS),
                           "fora_do_liquido": list(INDENIZATORIAS)},
            "estatisticas": dict(stats_total),
            "registros": todos,
        }
        self._salvar("remuneracao_senado.json", resultado)
        return resultado

    def exportar_subsidios(self) -> dict:
        from app.core.subsidios import historico_subsidios  # noqa: WPS433 (import tardio)
        conteudo = {
            "natureza": "Subsídio constitucional de referência (valor legal do cargo, não contracheque).",
            "cargos": {c: historico_subsidios(c) for c in ("DEPUTADO_FEDERAL", "SENADOR", "PRESIDENTE")},
        }
        self._salvar("subsidios_referencia.json", conteudo)
        return conteudo

    def _salvar(self, nome: str, conteudo: dict) -> None:
        with open(self.out_dir / nome, "w", encoding="utf-8") as f:
            json.dump(conteudo, f, ensure_ascii=False, indent=1)


def _ano_mes(texto: str) -> Tuple[int, int]:
    ano, mes = texto.split("-")
    return int(ano), int(mes)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    hoje = date.today()
    ap = argparse.ArgumentParser(description="Extrai remuneração nominal de senadores e subsídios de referência.")
    ap.add_argument("--de", type=_ano_mes, default=(2023, 2), help="AAAA-MM (padrão 2023-02)")
    ap.add_argument("--ate", type=_ano_mes, default=(hoje.year, hoje.month), help="AAAA-MM")
    ap.add_argument("--saida", type=Path, default=PROCESSED_DATA_DIR)
    ap.add_argument("--cache", type=Path, default=RAW_DATA_DIR / "remuneracao")
    args = ap.parse_args(argv)

    ext = RemuneracaoExtractor(raw_dir=args.cache, out_dir=args.saida)
    ext.exportar_subsidios()
    ext.extrair_senado(args.de, args.ate)
    logger.info("Requisições HTTP feitas nesta execução: %d", ext.http.requests_made)


if __name__ == "__main__":
    main()
