"""Tests for MixPy networking demo patches."""
from demo_game.network.client import HTTPClient, SocketClient, Response


def test_http_head_blocks_path():
    client = HTTPClient()
    assert client.get("/blocked").status == 403
    assert client.get("/blocked").body == "Forbidden"


def test_http_head_allows_normal_path():
    client = HTTPClient()
    r = client.get("/api/data")
    assert r.status == 200


def test_http_post_empty_body_gets_default():
    client = HTTPClient()
    r = client.post("/api/items", body="")
    assert "{}" in r.body


def test_http_post_non_empty_body_unchanged():
    client = HTTPClient()
    r = client.post("/api/items", body='{"x":1}')
    assert '{"x":1}' in r.body


def test_http_fetch_exception_fallback():
    class _BrokenHTTPClient(HTTPClient):
        def get(self, path: str, headers=None) -> Response:  # type: ignore[override]
            raise ConnectionError("simulated")

    client = _BrokenHTTPClient()
    r = client.fetch("/api")
    assert r.status == 503


def test_socket_send_returns_length():
    sock = SocketClient()
    sock.connect()
    assert sock.send(b"hello") == 5


def test_socket_send_empty_raises():
    sock = SocketClient()
    sock.connect()
    try:
        sock.send(b"")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_socket_send_disconnected_returns_minus_one():
    sock = SocketClient()
    # not connected, send → ConnectionError → EXCEPTION injector cancels to -1
    result = sock.send(b"hi")
    assert result == -1
