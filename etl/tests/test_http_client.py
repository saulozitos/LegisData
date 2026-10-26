"""Cliente HTTP: retry, status, resposta truncada e JSON inválido."""

import http.client
import io
import urllib.error

import pytest

from etl.utils.http_client import HttpClient, HttpError, RateLimiter


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

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


def http_error(code, headers=None):
    return urllib.error.HTTPError("http://x", code, "erro", headers or {}, None)


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


def test_retry_after_em_segundos_vira_a_espera_quando_maior_que_o_backoff(monkeypatch):
    instalar(monkeypatch, [http_error(429, {"Retry-After": "30"}), FakeResponse(b"{}")])
    dorme = []
    HttpClient(sleep=dorme.append, max_retries=3).get_json("http://x")
    assert dorme == [30.0]  # e não o backoff de 1,5 s


def test_sem_retry_after_ou_com_valor_invalido_vale_o_backoff(monkeypatch):
    for cabecalhos in (
        {},
        {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
        {"Retry-After": "-5"},
        {"Retry-After": "x"},
    ):
        instalar(monkeypatch, [http_error(503, cabecalhos), FakeResponse(b"{}")])
        dorme = []
        HttpClient(sleep=dorme.append, max_retries=3, backoff_base=2).get_json("http://x")
        assert dorme == [2.0], cabecalhos


def test_retry_after_pequeno_nao_encurta_o_backoff(monkeypatch):
    instalar(monkeypatch, [http_error(429, {"Retry-After": "0"}), FakeResponse(b"{}")])
    dorme = []
    HttpClient(sleep=dorme.append, max_retries=3, backoff_base=2).get_json("http://x")
    assert dorme == [2.0]


def test_retry_after_acima_do_limite_desiste_na_hora_sem_dormir(monkeypatch):
    chamadas = instalar(monkeypatch, [http_error(429, {"Retry-After": "3600"}), FakeResponse(b"{}")])
    dorme = []
    with pytest.raises(HttpError, match="Retry-After de 3600s") as exc:
        HttpClient(sleep=dorme.append, max_retries=4).get_bytes("http://x")
    assert exc.value.status == 429 and dorme == [] and len(chamadas) == 1


def test_resposta_dentro_do_teto_e_devolvida_inteira(monkeypatch):
    instalar(monkeypatch, [FakeResponse(b"x" * 1000, headers={"Content-Length": "1000"})])
    assert cliente().get_bytes("http://x", max_bytes=1000) == b"x" * 1000


def test_content_length_acima_do_teto_recusa_sem_ler_o_corpo_e_sem_nova_tentativa(monkeypatch):
    chamadas = instalar(monkeypatch, [FakeResponse(b"x", headers={"Content-Length": "5000"}), FakeResponse(b"ok")])
    with pytest.raises(HttpError, match="teto de 1000"):
        cliente(max_retries=3).get_bytes("http://x", max_bytes=1000)
    assert len(chamadas) == 1  # definitivo: repetir traria o mesmo arquivo gigante


def test_corpo_acima_do_teto_sem_content_length_e_cortado_no_meio_da_leitura(monkeypatch):
    chamadas = instalar(monkeypatch, [FakeResponse(b"x" * 3_000_000), FakeResponse(b"ok")])
    with pytest.raises(HttpError, match="passou do teto"):
        cliente(max_retries=3).get_bytes("http://x", max_bytes=2_000_000)
    assert len(chamadas) == 1


def test_sem_max_bytes_o_comportamento_antigo_continua(monkeypatch):
    instalar(monkeypatch, [FakeResponse(b"x" * 3_000_000, headers={"Content-Length": "3000000"})])
    assert len(cliente().get_bytes("http://x")) == 3_000_000


def test_retry_after_menor_que_o_backoff_fica_com_o_backoff(monkeypatch):
    instalar(monkeypatch, [http_error(429, {"Retry-After": "1"}), FakeResponse(b"{}")])
    dorme = []
    HttpClient(sleep=dorme.append, max_retries=3, backoff_base=2).get_json("http://x")
    assert dorme == [2.0]


def test_a_espera_pedida_numa_tentativa_nao_vaza_para_a_seguinte(monkeypatch):
    instalar(monkeypatch, [http_error(429, {"Retry-After": "30"}), http_error(429), FakeResponse(b"{}")])
    dorme = []
    HttpClient(sleep=dorme.append, max_retries=4, backoff_base=2).get_json("http://x")
    assert dorme == [30.0, 4.0]  # a segunda falha não trazia Retry-After: vale o backoff da 2ª tentativa


@pytest.mark.parametrize("pedido, desiste", [("120", False), ("120.5", True), ("121", True)])
def test_retry_after_no_limite_exato_espera_e_acima_dele_desiste(monkeypatch, pedido, desiste):
    instalar(monkeypatch, [http_error(429, {"Retry-After": pedido}), FakeResponse(b"{}")])
    dorme = []
    cli = HttpClient(sleep=dorme.append, max_retries=3, backoff_base=2)
    if desiste:
        with pytest.raises(HttpError, match="Retry-After"):
            cli.get_json("http://x")
        assert dorme == []
    else:
        cli.get_json("http://x")
        assert dorme == [120.0]


@pytest.mark.parametrize("valor", ["abc", "", "1.5", None, "-"])
def test_content_length_invalido_e_ignorado_e_o_teto_vale_pelo_corpo_lido(monkeypatch, valor):
    from etl.utils.http_client import _tamanho_declarado

    assert _tamanho_declarado({"Content-Length": valor}) is None
    instalar(monkeypatch, [FakeResponse(b"x" * 50, headers={"Content-Length": valor})])
    with pytest.raises(HttpError):
        cliente().get_bytes("http://x", max_bytes=10)
