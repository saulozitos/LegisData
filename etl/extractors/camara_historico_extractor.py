"""
Extrator do histórico de mandatos dos deputados federais (API de Dados Abertos da Câmara, v2).

Para cada legislatura da janela de dados (50ª em diante, a partir de 1995) lista os deputados e baixa
`/deputados/{id}/historico`: posse, saída, licença, suplência, convocação e troca de partido, com data. É dele que
saem as cadeiras-dia de cada partido em qualquer período (quem ocupou a cadeira, por qual partido, em que dias).
Cada resposta é guardada em `etl/data/raw/camara_historico/{id}.json` (cache; reexecutar só baixa o que falta).
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set

from etl.config import RAW_DATA_DIR
from etl.utils.http_client import HttpClient, HttpError
from etl.utils.io_utils import atomic_write_json

logger = logging.getLogger("CamaraHistoricoExtractor")

BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
LEGISLATURA_INICIAL = 50  # 1995-02-01 a 1999-01-31
ITENS_POR_PAGINA = 100


class CamaraHistoricoExtractor:
    def __init__(self, raw_dir: Optional[Path] = None, client: Optional[HttpClient] = None, workers: int = 6):
        self.raw_dir = Path(raw_dir) if raw_dir else RAW_DATA_DIR / "camara_historico"
        self.client = client or HttpClient(timeout=30.0, max_retries=4, min_interval=0.05)
        self.workers = workers

    def legislatura_atual(self) -> int:
        dados = self.client.get_json(f"{BASE_URL}/legislaturas?itens=1&ordem=DESC&ordenarPor=id")["dados"]
        return int(dados[0]["id"])

    def legislaturas(self) -> List[Dict[str, str]]:
        """Datas de início e fim de cada legislatura da janela."""
        ultima = self.legislatura_atual()
        resultado = []
        for numero in range(LEGISLATURA_INICIAL, ultima + 1):
            item = self.client.get_json(f"{BASE_URL}/legislaturas?id={numero}&itens=1")["dados"][0]
            resultado.append({"id": numero, "dataInicio": item["dataInicio"], "dataFim": item["dataFim"]})
        return resultado

    def ids_por_legislatura(self, legislatura: int) -> Set[int]:
        ids: Set[int] = set()
        pagina = 1
        while True:
            url = f"{BASE_URL}/deputados?idLegislatura={legislatura}&itens={ITENS_POR_PAGINA}&pagina={pagina}"
            dados = self.client.get_json(url)["dados"]
            ids.update(int(d["id"]) for d in dados)
            if len(dados) < ITENS_POR_PAGINA:
                return ids
            pagina += 1

    def _baixar(self, id_deputado: int, force: bool) -> bool:
        destino = self.raw_dir / f"{id_deputado}.json"
        if destino.exists() and not force:
            return False
        eventos = self.client.get_json(f"{BASE_URL}/deputados/{id_deputado}/historico")["dados"]
        atomic_write_json(destino, eventos)
        return True

    def run(self, force: bool = False) -> Dict[str, object]:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        legislaturas = self.legislaturas()
        atomic_write_json(self.raw_dir / "_legislaturas.json", legislaturas)
        ids: Set[int] = set()
        for leg in legislaturas:
            ids |= self.ids_por_legislatura(leg["id"])
        logger.info("%d deputados nas legislaturas %d a %d", len(ids), legislaturas[0]["id"], legislaturas[-1]["id"])

        baixados, falhas = 0, []
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futuros = {pool.submit(self._baixar, i, force): i for i in sorted(ids)}
            for futuro in as_completed(futuros):
                try:
                    baixados += int(futuro.result())
                except HttpError as exc:
                    falhas.append({"id": futuros[futuro], "erro": str(exc)})
        if falhas:
            logger.error("%d históricos não baixados (ex.: %s)", len(falhas), falhas[0])
        return {"deputados": len(ids), "baixados": baixados, "falhas": falhas, "legislaturas": legislaturas}

    def eventos(self) -> List[Dict[str, object]]:
        """Todos os eventos em cache, com o id do deputado anexado."""
        eventos: List[Dict[str, object]] = []
        for caminho in sorted(self.raw_dir.glob("[0-9]*.json")):
            with open(caminho, encoding="utf-8") as arquivo:
                eventos.extend(json.load(arquivo))
        return eventos
