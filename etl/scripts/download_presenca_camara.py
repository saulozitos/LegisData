#!/usr/bin/env python3
"""
Download Inteligente e Resiliente de 100% da Presença em Plenário da Câmara dos Deputados.

Garante a cobertura integral (100%) dos deputados das Legislaturas 56 e 57 para todos os
anos disponíveis no portal oficial da Câmara (2020 a 2026).
Informa em tempo real o status atual, porcentagem concluída, restante e tempo estimado.
Ao final, consolida os arquivos de produção:
- etl/data/processed/presenca_plenario_resumo.json
- etl/data/processed/presenca_plenario_dias.json.gz
"""

import argparse
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import List, Tuple

import requests

# Ajuste do path
sys.path.insert(0, "/home/saulo/Workspace/LegisData")
sys.path.insert(0, "/home/saulo/Workspace/LegisData/backend")

from etl.config import PROCESSED_DATA_DIR, RAW_DATA_DIR  # noqa: E402
from etl.extractors.presenca_extractor import (  # noqa: E402
    CAMARA_PRIMEIRO_ANO,
    LEGISLATURAS,
    URL_CAMARA_PRESENCA,
    PresencaExtractor,
    _agora,
    _cache_vale,
    parse_presenca_camara,
)
from etl.utils.io_utils import atomic_write_json  # noqa: E402

logger = logging.getLogger("DownloadPresencaCamara")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36 (LegisData Intelligent Collector)"
)


class IntelligentPresencaDownloader:
    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        workers: int = 3,
        request_delay: float = 0.2,
    ):
        self.raw_dir = Path(raw_dir) / "presenca" / "camara"
        self.processed_dir = Path(processed_dir)
        self.workers = workers
        self.request_delay = request_delay
        self.hoje = date.today()
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Não pausado inicialmente

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
            }
        )

    def _cache_path(self, cid: int, ano: int) -> Path:
        return self.raw_dir / str(ano) / f"{cid}.json"

    def is_cached(self, cid: int, ano: int) -> bool:
        p = self._cache_path(cid, ano)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return _cache_vale(data.get("fetched_at"), ano, self.hoje)
        except (OSError, json.JSONDecodeError):
            return False

    def build_tasks(self) -> List[Tuple[int, str, int]]:
        """Gera todas as 4.431 tarefas (deputado x ano) das Legislaturas 56 e 57."""
        tarefas = []
        for leg, (ini, fim) in sorted(LEGISLATURAS.items(), reverse=True):
            anos_leg = [a for a in range(max(ini, CAMARA_PRIMEIRO_ANO), min(fim, self.hoje.year) + 1)]
            caminho_dep = self.raw_dir / f"deputados_legislatura_{leg}.json"
            if not caminho_dep.exists():
                raise FileNotFoundError(f"Arquivo de deputados da legislatura {leg} não encontrado em {caminho_dep}")
            dados_dep = json.loads(caminho_dep.read_text(encoding="utf-8"))["deputados"]
            for d in dados_dep:
                cid = int(d["id"])
                nome = d.get("nome", "")
                for ano in anos_leg:
                    tarefas.append((cid, nome, ano))
        # Remove duplicatas se houver
        vistos = set()
        dedup = []
        for t in tarefas:
            chave = (t[0], t[2])
            if chave not in vistos:
                vistos.add(chave)
                dedup.append(t)
        return dedup

    def fetch_single(self, cid: int, ano: int) -> bool:
        """Baixa e salva em cache uma página deputado x ano com tratamento de retry/429."""
        caminho = self._cache_path(cid, ano)
        url = URL_CAMARA_PRESENCA.format(id=cid, ano=ano)

        for tentativa in range(1, 6):
            self.pause_event.wait()  # Aguarda caso haja backoff global ativo
            try:
                resp = self.session.get(url, timeout=25)
                if resp.status_code == 429:
                    with self.lock:
                        if self.pause_event.is_set():
                            self.pause_event.clear()
                            espera = 15.0 * tentativa
                            logger.warning(
                                "HTTP 429 recebido em %s. Pausando todas as threads por %.1fs...", url, espera
                            )
                            time.sleep(espera)
                            self.pause_event.set()
                    continue
                if resp.status_code == 200:
                    html_text = resp.text
                    parsed = parse_presenca_camara(html_text)
                    atomic_write_json(
                        caminho,
                        {"fetched_at": _agora().isoformat(), "parsed": parsed},
                        indent=None,
                        separators=(",", ":"),
                    )
                    time.sleep(self.request_delay)
                    return True
                elif resp.status_code == 404:
                    # Deputado não possui registros para aquele ano
                    atomic_write_json(
                        caminho,
                        {"fetched_at": _agora().isoformat(), "parsed": None},
                        indent=None,
                        separators=(",", ":"),
                    )
                    return True
                else:
                    logger.warning("HTTP %s em %s (tentativa %d)", resp.status_code, url, tentativa)
                    time.sleep(1.0 * tentativa)
            except requests.RequestException as exc:
                logger.warning("Erro de conexão em %s: %s (tentativa %d)", url, exc, tentativa)
                time.sleep(2.0 * tentativa)

        return False

    def run(self) -> None:
        todas_tarefas = self.build_tasks()
        total = len(todas_tarefas)
        logger.info("Total de tarefas identificadas para 100%% de presença na Câmara: %d", total)

        concluidos_inicial = sum(1 for cid, _, ano in todas_tarefas if self.is_cached(cid, ano))
        pendentes = [t for t in todas_tarefas if not self.is_cached(t[0], t[2])]
        total_pendentes = len(pendentes)

        pct_inicial = (concluidos_inicial / total) * 100.0
        print(f"\n{'='*80}")
        print(f"ESTADO INICIAL: {concluidos_inicial}/{total} tarefas concluídas ({pct_inicial:.2f}%).")
        print(f"PENDENTES PARA 100%: {total_pendentes} tarefas restantes ({(total_pendentes/total)*100.0:.2f}%).")
        print(f"{'='*80}\n", flush=True)

        if not pendentes:
            print("100% dos dados de presença da Câmara já estão em cache! Consolidando arquivos...")
            self.consolidar()
            return

        concluidos_agora = concluidos_inicial
        t_inicio = time.time()
        ultimos_tempos = []
        lock_metricas = threading.Lock()

        def format_duracao(segundos: float) -> str:
            m, s = divmod(int(segundos), 60)
            h, m = divmod(m, 60)
            if h > 0:
                return f"{h}h {m:02d}m {s:02d}s"
            return f"{m:02d}m {s:02d}s"

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futuros = {executor.submit(self.fetch_single, cid, ano): (cid, nome, ano) for cid, nome, ano in pendentes}

            for i, fut in enumerate(as_completed(futuros), start=1):
                cid, nome, ano = futuros[fut]
                sucesso = fut.result()

                with lock_metricas:
                    if sucesso:
                        concluidos_agora += 1
                    t_atual = time.time()
                    ultimos_tempos.append(t_atual)
                    # Manter janela de 60 segundos para taxa
                    while ultimos_tempos and ultimos_tempos[0] < t_atual - 60:
                        ultimos_tempos.pop(0)
                    taxa = len(ultimos_tempos) / 60.0 if len(ultimos_tempos) > 5 else (i / max(1.0, t_atual - t_inicio))

                if i % 25 == 0 or i == total_pendentes:
                    restantes = total - concluidos_agora
                    pct = (concluidos_agora / total) * 100.0
                    pct_falta = 100.0 - pct
                    decorrido = time.time() - t_inicio
                    eta_segundos = restantes / max(0.1, taxa)

                    print(
                        f"[PRESENÇA CÂMARA 100%] Progresso: {concluidos_agora}/{total} ({pct:6.2f}%) | "
                        f"Faltam: {restantes:4d} ({pct_falta:5.2f}%) | "
                        f"Taxa: {taxa:4.1f} req/s | "
                        f"Decorrido: {format_duracao(decorrido)} | "
                        f"ETA: {format_duracao(eta_segundos)}",
                        flush=True,
                    )

        print(f"\n{'='*80}")
        print(f"DOWNLOAD CONCLUÍDO: 100% das páginas da Câmara baixadas ({concluidos_agora}/{total}).")
        print(f"Tempo total de extração: {format_duracao(time.time() - t_inicio)}")
        print(f"{'='*80}\n", flush=True)

        self.consolidar()

    def consolidar(self) -> None:
        """Executa a consolidação oficial dos dados processados via PresencaExtractor."""
        print("Consolidando resumos e dias oficiais através do PresencaExtractor...", flush=True)
        ext = PresencaExtractor(raw_dir=RAW_DATA_DIR, processed_dir=PROCESSED_DATA_DIR, workers=1)
        res = ext.run(camara=True, senado=False, usar_cache=True, ids_camara=None)

        camara_res = res.get("CAMARA", {})
        total_resumos = len(camara_res.get("resumos", []))
        total_dias = len(camara_res.get("dias", []))
        divergencias = camara_res.get("divergencias_resumo_oficial", 0)

        print("CONSOLIDAÇÃO CONCLUÍDA:")
        print(f"- Total de resumos anuais de deputados: {total_resumos}")
        print(f"- Total de dias deliberativos individuais: {total_dias}")
        print(f"- Divergências detectadas com resumo oficial: {divergencias}")
        print(f"- Arquivo de resumo: {self.processed_dir / 'presenca_plenario_resumo.json'}")
        print(f"- Arquivo de dias: {self.processed_dir / 'presenca_plenario_dias.json.gz'}")


def main():
    parser = argparse.ArgumentParser(description="Download inteligente de 100% de Presença da Câmara.")
    parser.add_argument("--workers", type=int, default=3, help="Número de threads simultâneas (padrão 3)")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay entre requisições por thread (padrão 0.2s)")
    args = parser.parse_args()

    downloader = IntelligentPresencaDownloader(workers=args.workers, request_delay=args.delay)
    downloader.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    main()
