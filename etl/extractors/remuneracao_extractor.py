"""
Extrator da remuneração mensal dos deputados — SOMENTE dados oficiais do portal da Câmara.

Fonte: https://www.camara.leg.br/deputados/{id}/remuneracao?ano={ano}
  * a tabela anual traz, por mês, a "Remuneração Fixa" do parlamentar (o subsídio fixado por decreto legislativo,
    proporcional aos dias em exercício no mês: suplentes e parlamentares que assumem/deixam a vaga no meio do mês
    aparecem com valor parcial). Os valores são lidos da página, nunca de uma tabela embutida no código.
  * para o mês mais recente de cada deputado em exercício, a página detalhada
    (`remuneracao-deputado-detalhado?mesAno=MMAAAA`, FOLHA NORMAL) informa a remuneração após descontos obrigatórios
    (líquido). Nos demais meses o líquido NÃO é coletado e permanece `null`.

Senado Federal: o portal de transparência só oferece consulta em HTML (por servidor/mês), sem arquivo estruturado
nem API estável. Por isso não há extrator do Senado: a remuneração de senadores fica `null` (lacuna documentada).
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from html import unescape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR
from etl.extractors.presenca_extractor import (
    LEGISLATURAS,
    PoliteHttpClient,
    PresencaExtractor,
    _agora,
    _cache_vale,
    ids_deputados_conhecidos,
)
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import EmptyResultError, atomic_write_json

logger = logging.getLogger("RemuneracaoExtractor")

URL_ANUAL = "https://www.camara.leg.br/deputados/{id}/remuneracao?ano={ano}"
URL_DETALHE = "https://www.camara.leg.br/deputados/{id}/remuneracao-deputado-detalhado?mesAno={mes:02d}{ano}"
FONTE = "Câmara dos Deputados — Portal da Transparência: remuneração de deputados (folha de pagamento)"
ARQ_REMUNERACAO = "remuneracao_parlamentares.json"
PRIMEIRO_ANO = 2019

_RE_LINHA_MES = re.compile(r'<td class="text-center">\s*(\d{2})\s*</td>\s*<td class="text-right">(.*?)</td>', re.S)
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_ESPACOS = re.compile(r"\s+")
# Valor monetário brasileiro com exatamente duas casas decimais. A página anexa o marcador de nota de rodapé ao
# número sem separador (ex.: "41.650,922" = 41.650,92 + nota "2"), então só os dois primeiros decimais valem.
_RE_VALOR_BR = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")


def parse_valor_br(texto: str) -> Optional[float]:
    m = _RE_VALOR_BR.search(texto or "")
    if not m:
        return None
    return float(m.group(0).replace(".", "").replace(",", "."))


def parse_remuneracao_anual(html_text: str) -> Dict[int, float]:
    """{mês: remuneração fixa (R$)} da tabela anual; vazio quando a página não traz dados."""
    meses: Dict[int, float] = {}
    for mes, bruto in _RE_LINHA_MES.findall(html_text):
        valor = parse_valor_br(_RE_ESPACOS.sub(" ", unescape(_RE_TAGS.sub("", bruto))))
        if valor is not None and 1 <= int(mes) <= 12:
            meses[int(mes)] = valor
    return meses


def parse_remuneracao_detalhe(html_text: str) -> Optional[Dict[str, Optional[float]]]:
    """Fixa e líquido (após descontos obrigatórios) da FOLHA NORMAL da página detalhada; None se ausente."""
    texto = _RE_ESPACOS.sub(
        " ", unescape(_RE_TAGS.sub(" ", re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)))
    )
    inicio = texto.find("FOLHA NORMAL")
    if inicio < 0:
        return None
    fim = texto.find("Mês/Ano de Referência", inicio + 10)
    secao = texto[inicio : fim if fim > 0 else len(texto)]

    def valor_apos(rotulo: str) -> Optional[float]:
        i = secao.find(rotulo)
        return parse_valor_br(secao[i + len(rotulo) :]) if i >= 0 else None

    liquido = valor_apos("Remuneração após Descontos Obrigatórios")
    # "5 - Remuneração após Descontos Obrigatórios a - Remuneração após Descontos Obrigatórios 27.548,35":
    # o primeiro rótulo é o título do grupo; o valor vem depois do segundo.
    ultimo = secao.rfind("Remuneração após Descontos Obrigatórios")
    if ultimo >= 0:
        liquido = parse_valor_br(secao[ultimo + len("Remuneração após Descontos Obrigatórios") :])
    return {"fixa": valor_apos("Remuneração Fixa"), "liquido": liquido}


class RemuneracaoExtractor:
    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        http: Optional[HttpClient] = None,
        workers: int = 1,
        hoje: Optional[date] = None,
    ):
        self.processed_dir = Path(processed_dir)
        self.hoje = hoje or date.today()
        # O portal da Câmara responde 429 a rajadas: 1 requisição/s, uma por vez, com backoff longo.
        self.http = http or PoliteHttpClient()
        self.workers = max(1, workers)
        self._presenca = PresencaExtractor(raw_dir, processed_dir, http=self.http, workers=workers, hoje=self.hoje)
        self.raw_dir = Path(raw_dir) / "remuneracao"

    def _ler(self, caminho: Path) -> Optional[Dict[str, Any]]:
        return self._presenca._ler_cache(caminho)

    def _anual(self, camara_id: int, ano: int, usar_cache: bool) -> Dict[int, float]:
        caminho = self.raw_dir / str(ano) / f"{camara_id}.json"
        if usar_cache:
            cache = self._ler(caminho)
            if cache and _cache_vale(cache.get("fetched_at"), ano, self.hoje):
                return {int(k): v for k, v in cache["meses"].items()}
        bruto = self.http.get_bytes(URL_ANUAL.format(id=camara_id, ano=ano))
        meses = parse_remuneracao_anual(bruto.decode("utf-8", errors="replace"))
        atomic_write_json(
            caminho, {"fetched_at": _agora().isoformat(), "meses": meses}, indent=None, separators=(",", ":")
        )
        return meses

    def _detalhe(self, camara_id: int, ano: int, mes: int, usar_cache: bool) -> Optional[Dict[str, Optional[float]]]:
        caminho = self.raw_dir / "detalhe" / f"{camara_id}_{ano}{mes:02d}.json"
        if usar_cache:
            cache = self._ler(caminho)
            if cache and _cache_vale(cache.get("fetched_at"), ano, self.hoje):
                return cache.get("detalhe")
        bruto = self.http.get_bytes(URL_DETALHE.format(id=camara_id, ano=ano, mes=mes))
        detalhe = parse_remuneracao_detalhe(bruto.decode("utf-8", errors="replace"))
        atomic_write_json(
            caminho, {"fetched_at": _agora().isoformat(), "detalhe": detalhe}, indent=None, separators=(",", ":")
        )
        return detalhe

    def run(
        self,
        anos: Optional[List[int]] = None,
        usar_cache: bool = True,
        ids_permitidos: Optional[Iterable[int]] = None,
    ) -> Dict[str, Any]:
        anos = sorted(anos or range(PRIMEIRO_ANO, self.hoje.year + 1))
        permitidos = set(ids_permitidos) if ids_permitidos is not None else None
        tarefas: List[Tuple[int, str, int]] = []
        for legislatura, (ini, fim) in LEGISLATURAS.items():
            anos_leg = [a for a in anos if ini <= a <= min(fim, self.hoje.year)]
            if not anos_leg:
                continue
            for dep in self._presenca.listar_deputados(legislatura, usar_cache):
                if permitidos is not None and dep["id"] not in permitidos:
                    continue
                tarefas.extend((dep["id"], dep["nome"], a) for a in anos_leg)
        logger.info("Remuneração: %d páginas anuais (deputado × ano)", len(tarefas))

        registros: List[Dict[str, Any]] = []
        falhas: List[str] = []

        def trabalho(t: Tuple[int, str, int]):
            cid, _nome, ano = t
            try:
                return t, self._anual(cid, ano, usar_cache), None
            except HttpError as exc:
                return t, {}, str(exc)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for fut in as_completed([pool.submit(trabalho, t) for t in tarefas]):
                (cid, nome, ano), meses, erro = fut.result()
                if erro:
                    falhas.append(f"{cid}/{ano}: {erro}")
                for mes, valor in sorted(meses.items()):
                    registros.append({"camara_id": cid, "nome": nome, "ano": ano, "mes": mes, "salario_bruto": valor})

        # Líquido do mês mais recente de cada deputado (uma página detalhada por deputado)
        ultimo: Dict[int, Dict[str, Any]] = {}
        for r in registros:
            atual = ultimo.get(r["camara_id"])
            if atual is None or (r["ano"], r["mes"]) > (atual["ano"], atual["mes"]):
                ultimo[r["camara_id"]] = r
        # Só vale buscar o líquido de quem tem registro no ano corrente ou no anterior (em exercício recente)
        alvos = [r for r in ultimo.values() if r["ano"] >= self.hoje.year - 1]

        def detalhe_trabalho(r: Dict[str, Any]):
            try:
                return r, self._detalhe(r["camara_id"], r["ano"], r["mes"], usar_cache), None
            except HttpError as exc:
                return r, None, str(exc)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for fut in as_completed([pool.submit(detalhe_trabalho, r) for r in alvos]):
                r, detalhe, erro = fut.result()
                if erro:
                    falhas.append(f"detalhe {r['camara_id']}/{r['ano']}-{r['mes']}: {erro}")
                    continue
                if detalhe and detalhe.get("liquido") is not None:
                    r["salario_liquido"] = detalhe["liquido"]

        for r in registros:
            r.setdefault("salario_liquido", None)
        registros.sort(key=lambda r: (r["camara_id"], r["ano"], r["mes"]))
        if not registros:
            raise EmptyResultError("Nenhuma remuneração extraída; arquivo existente preservado.")

        saida = {
            "gerado_em": _agora().isoformat(timespec="seconds"),
            "is_synthetic": False,
            "fonte": FONTE,
            "metodologia": (
                "salario_bruto = 'Remuneração Fixa' do mês (subsídio proporcional ao exercício); salario_liquido = "
                "remuneração após descontos obrigatórios da FOLHA NORMAL, coletada apenas para o mês mais recente de "
                "cada deputado (demais meses: null). Senado: sem fonte estruturada (null)."
            ),
            "cobertura": {
                "anos": sorted({r["ano"] for r in registros}),
                "deputados": len({r["camara_id"] for r in registros}),
                "falhas": falhas,
            },
            "registros": registros,
        }
        atomic_write_json(self.processed_dir / ARQ_REMUNERACAO, saida)
        return saida


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Extrai a remuneração mensal dos deputados (portal da Câmara).")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--todos", action="store_true", help="Todos os deputados das legislaturas (não só os conhecidos)"
    )
    args = parser.parse_args()
    res = RemuneracaoExtractor(workers=args.workers).run(
        usar_cache=not args.no_cache, ids_permitidos=None if args.todos else ids_deputados_conhecidos()
    )
    print(len(res["registros"]), "registros;", len(res["cobertura"]["falhas"]), "falhas")


if __name__ == "__main__":
    main()
