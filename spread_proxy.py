"""The kit's client, sent through HTTPS_PROXY when one is set. In a Claude Code cloud session the proxy adds the team
key, so SPREAD_KEY can be a placeholder there. Without HTTPS_PROXY, or for a host in NO_PROXY, the client connects
straight to the server, as the kit's own does. The vendored kit stays unchanged."""

from __future__ import annotations

import http.client
import os
import ssl
from typing import Any
from urllib.parse import urlsplit

from spread.client import Client, Unreachable


def bypasses_proxy(host: str, no_proxy: str) -> bool:
    """True when NO_PROXY names the host, or a domain it belongs to."""
    for entry in (e.strip().lstrip("*").lower() for e in no_proxy.split(",")):
        if entry and (host == entry.lstrip(".") or host.endswith(entry if entry.startswith(".") else "." + entry)):
            return True
    return False


class ProxyClient(Client):
    """The kit's client, sent through HTTPS_PROXY when one is set, and counting its requests. The tunnel trusts the
    certificates in SSL_CERT_FILE, as Python's default TLS context does."""

    def __init__(self, url: str | None = None, key: str | None = None):
        super().__init__(url, key)
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        no_proxy = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
        host = self._parts.hostname or ""
        use = proxy and self._parts.scheme == "https" and not bypasses_proxy(host, no_proxy)
        self.proxy = urlsplit(proxy) if use else None
        self.requests = 0

    def call(self, method: str, path: str, body: Any = None, actions: int = 0) -> Any:
        self.requests += 1
        return super().call(method, path, body, actions)

    def _send(self, method: str, path: str, payload: bytes | None, headers: dict):
        # The kit's _send, with the connection opened through the proxy. Retries a kept-alive connection that the
        # server closed while it was idle: that request never arrived.
        while True:
            reused = self._connection is not None
            if self._connection is None:
                self._connection = self._connect()
            try:
                self._connection.request(method, self._parts.path + path, payload, headers)
                response = self._connection.getresponse()
                return response.status, response.headers, response.read()
            except BaseException as error:
                self._connection.close()
                self._connection = None
                if reused and isinstance(error, (ConnectionResetError, BrokenPipeError)):
                    continue
                if isinstance(error, (OSError, http.client.HTTPException)):
                    raise Unreachable(0, f"Cannot reach {self.url}: {error}") from error
                raise

    def _connect(self) -> http.client.HTTPConnection:
        if self.proxy is None:
            kind = http.client.HTTPSConnection if self._parts.scheme == "https" else http.client.HTTPConnection
            return kind(self._parts.netloc, timeout=20)
        connection = http.client.HTTPSConnection(
            self.proxy.hostname, self.proxy.port or 80, timeout=20, context=ssl.create_default_context()
        )
        connection.set_tunnel(self._parts.hostname, self._parts.port or 443)
        return connection
