import socket

import httpcore
import pytest

from hub.modules.capture.fetcher import (
    MAX_RESPONSE_BYTES,
    ResponseTooLargeError,
    UnsafeUrlError,
    UnsupportedContentTypeError,
    fetch_page,
    resolve_public_address,
)


class StaticBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.connected_hosts: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected_hosts.append(host)
        return httpcore.AsyncMockStream([self.response])

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise AssertionError("unix sockets are not supported")

    async def sleep(self, seconds: float) -> None:
        return None


@pytest.mark.asyncio
async def test_resolve_public_address_rejects_private_dns_result(monkeypatch) -> None:
    def fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError):
        await resolve_public_address("public.example", 80)


@pytest.mark.asyncio
async def test_fetch_pins_connection_to_validated_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))
        ],
    )
    backend = StaticBackend(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 5\r\n\r\nhello"
    )
    page = await fetch_page("http://public.example/path", network_backend=backend)
    assert page.body == "hello"
    assert backend.connected_hosts == ["public.example"]


@pytest.mark.asyncio
async def test_fetch_rejects_unsupported_content_type() -> None:
    backend = StaticBackend(
        b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\nContent-Length: 4\r\n\r\nblob"
    )
    with pytest.raises(UnsupportedContentTypeError, match="format"):
        await fetch_page("http://93.184.216.34/image", network_backend=backend)


@pytest.mark.asyncio
async def test_fetch_rejects_oversized_response() -> None:
    body = b"x" * (MAX_RESPONSE_BYTES + 1)
    backend = StaticBackend(
        b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n" + body
    )
    with pytest.raises(ResponseTooLargeError, match="large"):
        await fetch_page("http://93.184.216.34/large", network_backend=backend)


@pytest.mark.asyncio
async def test_fetch_revalidates_redirect_target() -> None:
    backend = StaticBackend(
        b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/admin\r\nContent-Length: 0\r\n\r\n"
    )
    with pytest.raises(UnsafeUrlError):
        await fetch_page("http://93.184.216.34/start", network_backend=backend)
