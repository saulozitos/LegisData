"""Cliente HTTP: retry, status, resposta truncada e JSON inválido."""

import http.client
import io
import urllib.error

import pytest

from etl.utils.http_client import HttpClient, HttpError, RateLimiter


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def instalar(monkeypatch, comportamentos):
    """Cada chamada a urlopen consome o próximo comportamento (exceção ou resposta)."""
    chamadas = []

    def fake_urlopen(req, timeout=None):
        chamadas.append((req.full_url, timeout))
        item = comportamentos[min(len(chamadas) - 1, len(comportamentos) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return chamadas


def cliente(**kw):
    return HttpClient(sleep=lambda _s: None, **kw)


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "erro", {}, None)


def test_sucesso_envia_timeout(monkeypatch):
    chamadas = instalar(monkeypatch, [FakeResponse(b'{"ok": true}')])
    assert cliente(timeout=7).get_json("http://x/a") == {"ok": True}
    assert chamadas == [("http://x/a", 7)]


def test_incomplete_read_e_retentado_e_nunca_aceita_parcial(monkeypatch):
    chamadas = instalar(
        monkeypatch,
        [http.client.IncompleteRead(b'{"parcial":'), FakeResponse(b"[1, 2, 3]")],
    )
    assert cliente().get_json("http://x") == [1, 2, 3]
    assert len(chamadas) == 2


def test_429_e_5xx_sao_retentados(monkeypatch):
    chamadas = instalar(monkeypatch, [http_error(429), http_error(503), FakeResponse(b"{}")])
    assert cliente(max_retries=4).get_json("http://x") == {}
    assert len(chamadas) == 3


def test_404_nao_e_retentado(monkeypatch):
    chamadas = instalar(monkeypatch, [http_error(404), FakeResponse(b"{}")])
    with pytest.raises(HttpError) as exc:
        cliente().get_json("http://x")
    assert exc.value.status == 404
    assert len(chamadas) == 1


def test_tentativas_esgotadas_levantam_http_error(monkeypatch):
    instalar(monkeypatch, [urllib.error.URLError("sem rede")])
    with pytest.raises(HttpError):
        cliente(max_retries=3).get_bytes("http://x")


def test_status_diferente_de_200_e_erro(monkeypatch):
    instalar(monkeypatch, [FakeResponse(b"x", status=204)])
    with pytest.raises(HttpError):
        cliente(max_retries=1).get_bytes("http://x")


def test_json_invalido_levanta_http_error(monkeypatch):
    instalar(monkeypatch, [FakeResponse(b"<html>")])
    with pytest.raises(HttpError):
        cliente().get_json("http://x")


def test_try_get_json_devolve_none_em_falha(monkeypatch):
    instalar(monkeypatch, [http_error(404)])
    assert cliente().try_get_json("http://x") is None


def test_rate_limiter_espaca_chamadas(monkeypatch):
    dorme = []
    monkeypatch.setattr("time.sleep", lambda s: dorme.append(s))
    limitador = RateLimiter(0.5)
    limitador.wait()
    limitador.wait()
    limitador.wait()
    # sem relógio real: a 1ª chamada passa direto; a 2ª e a 3ª são agendadas em 0,5s e 1,0s à frente
    assert len(dorme) == 2
    assert dorme[0] == pytest.approx(0.5, abs=0.05)
    assert dorme[1] - dorme[0] == pytest.approx(0.5, abs=0.05)
