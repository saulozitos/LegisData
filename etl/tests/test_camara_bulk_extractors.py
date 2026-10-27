"""Extratores em lote da Câmara: URLs, cache, arquivo inexistente e histórico por deputado (sem rede)."""

import hashlib

from etl.extractors import camara_bulk_extractor as bulk
from etl.extractors.camara_historico_extractor import CamaraHistoricoExtractor
from etl.utils.download import NotFoundError


def test_url_do_arquivo_segue_o_padrao_oficial():
    assert bulk.url_do_arquivo("proposicoes", 2024) == (
        "https://dadosabertos.camara.leg.br/arquivos/proposicoes/csv/proposicoes-2024.csv"
    )
    assert bulk.url_do_arquivo("proposicoesAutores", 1995).endswith(
        "/proposicoesAutores/csv/proposicoesAutores-1995.csv"
    )


def test_extrator_registra_hash_e_pula_ano_inexistente(tmp_path, monkeypatch):
    def falso(url, destino, force=False, **_):
        if "1995" in url:
            raise NotFoundError(f"{url}: 404")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"conteudo " + url.encode())
        return destino

    monkeypatch.setattr(bulk, "download_file", falso)
    arquivos = bulk.CamaraBulkExtractor(raw_dir=tmp_path, anos=[1995, 1996]).run()
    assert {(a.recurso, a.ano) for a in arquivos} == {("proposicoes", 1996), ("proposicoesAutores", 1996)}
    primeiro = arquivos[0]
    assert primeiro.sha256 == hashlib.sha256(primeiro.caminho.read_bytes()).hexdigest()
    assert primeiro.bytes == primeiro.caminho.stat().st_size


def test_janela_de_dados_comeca_em_1995():
    assert bulk.ANO_INICIAL == 1995
    assert bulk.CamaraBulkExtractor().anos[0] == 1995


class ClienteFalso:
    def __init__(self):
        self.chamadas = []

    def get_json(self, url, **_):
        self.chamadas.append(url)
        if "legislaturas?itens=1" in url:
            return {"dados": [{"id": 51}]}
        if "legislaturas?id=" in url:
            numero = int(url.split("id=")[1].split("&")[0])
            return {"dados": [{"id": numero, "dataInicio": f"{1995 + (numero - 50) * 4}-02-01", "dataFim": "x"}]}
        if "/deputados?idLegislatura=" in url:
            return {"dados": [{"id": 10}, {"id": 11}]}
        if url.endswith("/historico"):
            return {
                "dados": [{"id": int(url.split("/")[-2]), "idLegislatura": 50, "descricaoStatus": "Entrada - Posse"}]
            }
        raise AssertionError(url)


def test_historico_baixa_uma_vez_e_reaproveita_o_cache(tmp_path):
    cliente = ClienteFalso()
    extrator = CamaraHistoricoExtractor(raw_dir=tmp_path, client=cliente, workers=1)
    primeiro = extrator.run()
    assert primeiro["deputados"] == 2 and primeiro["baixados"] == 2 and primeiro["falhas"] == []
    assert {p.name for p in tmp_path.glob("*.json")} == {"10.json", "11.json", "_legislaturas.json"}
    antes = len(cliente.chamadas)
    segundo = extrator.run()
    assert segundo["baixados"] == 0
    assert not [c for c in cliente.chamadas[antes:] if c.endswith("/historico")]
    assert len(extrator.eventos()) == 2


def test_historico_comeca_na_50a_legislatura():
    from etl.extractors.camara_historico_extractor import LEGISLATURA_INICIAL

    assert LEGISLATURA_INICIAL == 50  # 1995-02-01
