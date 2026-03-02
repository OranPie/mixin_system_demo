"""Simulated networking clients for MixPy networking demo."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Response:
    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HTTPClient:
    """Simulated HTTP client (no real I/O)."""

    def __init__(self, base_url: str = "http://example.com", timeout: float = 5.0):
        self.base_url = base_url
        self.timeout = timeout
        self.request_log: list[dict[str, Any]] = []

    def get(self, path: str, headers: dict[str, str] | None = None) -> Response:
        url = f"{self.base_url}{path}"
        self.request_log.append({"method": "GET", "url": url, "headers": headers or {}})
        return Response(status=200, body=f"GET {url}", headers={})

    def post(self, path: str, body: str = "", headers: dict[str, str] | None = None) -> Response:
        url = f"{self.base_url}{path}"
        self.request_log.append({"method": "POST", "url": url, "body": body, "headers": headers or {}})
        return Response(status=201, body=f"POST {url} -> {body}", headers={})

    def fetch(self, path: str, retries: int = 0) -> Response:
        """Fetch with optional retries (demonstrates HEAD + EXCEPTION injection)."""
        return self.get(path)


class SocketClient:
    """Simulated socket client (no real I/O)."""

    def __init__(self, host: str = "localhost", port: int = 9000):
        self.host = host
        self.port = port
        self._connected = False
        self.sent: list[bytes] = []
        self.recv_buffer: bytes = b""

    def connect(self) -> None:
        self._connected = True

    def send(self, data: bytes) -> int:
        if not self._connected:
            raise ConnectionError("Socket not connected")
        self.sent.append(data)
        return len(data)

    def recv(self, size: int = 1024) -> bytes:
        chunk = self.recv_buffer[:size]
        self.recv_buffer = self.recv_buffer[size:]
        return chunk

    def close(self) -> None:
        self._connected = False
