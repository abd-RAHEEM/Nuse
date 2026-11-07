import asyncio
import socket
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urljoin, urlsplit

import httpcore

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "text/plain",
}
USER_AGENT = "NuseCapture/1.0 (+https://nuse.local)"


class FetchError(Exception):
    code = "extraction_failed"
    hint = "retry"


class UnsafeUrlError(FetchError):
    code = "unsafe_url"
    hint = "check_url"


class FetchTimeoutError(FetchError):
    code = "extraction_timeout"


class UnsupportedContentTypeError(FetchError):
    code = "extraction_failed"
    hint = "enter_manually"


class ResponseTooLargeError(FetchError):
    code = "extraction_failed"
    hint = "enter_manually"


def _header(headers: list[tuple[bytes, bytes]], name: bytes) -> bytes | None:
    return next((value for key, value in headers if key.lower() == name), None)


@dataclass(frozen=True)
class FetchedPage:
    url: str
    content_type: str
    body: str
    redirects: int


def _is_unsafe(address: IPv4Address | IPv6Address) -> bool:
    return not address.is_global or address.is_multicast or address.is_unspecified


async def resolve_public_address(hostname: str, port: int) -> IPv4Address | IPv6Address:
    try:
        address = ip_address(hostname)
    except ValueError:
        try:
            records = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port,
                socket.AF_UNSPEC,
                socket.SOCK_STREAM,
            )
        except (OSError, socket.gaierror) as error:
            raise FetchError("The source host could not be resolved") from error
        addresses = {ip_address(record[4][0]) for record in records}
    else:
        addresses = {address}

    if not addresses or any(_is_unsafe(item) for item in addresses):
        raise UnsafeUrlError("private and local network URLs cannot be fetched")
    return sorted(addresses, key=lambda item: (item.version, str(item)))[0]


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object | None = None,
    ) -> httpcore.AsyncNetworkStream:
        address = await resolve_public_address(host, port)
        return await self._backend.connect_tcp(
            str(address), port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: object | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise UnsafeUrlError("Unix socket URLs are not supported")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


async def fetch_page(
    url: str,
    *,
    total_timeout: float = 15.0,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
) -> FetchedPage:
    current_url = url
    redirects = 0
    pool = httpcore.AsyncConnectionPool(
        network_backend=network_backend or PinnedNetworkBackend(),
        max_connections=10,
        max_keepalive_connections=0,
    )
    try:
        async with asyncio.timeout(total_timeout):
            while True:
                parsed = urlsplit(current_url)
                if (
                    parsed.scheme not in {"http", "https"}
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                ):
                    raise UnsafeUrlError("Only public http(s) URLs are supported")
                await resolve_public_address(
                    parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
                )
                request = httpcore.Request(
                    "GET",
                    current_url,
                    headers=[
                        (
                            b"accept",
                            b"text/html, application/xhtml+xml, application/json, text/plain",
                        ),
                        (b"host", parsed.netloc.encode("ascii")),
                        (b"user-agent", USER_AGENT.encode("ascii")),
                    ],
                )
                response = await pool.handle_async_request(request)
                if response.status in {301, 302, 303, 307, 308}:
                    location = _header(response.headers, b"location")
                    await response.aread()
                    if not location or redirects >= MAX_REDIRECTS:
                        raise FetchError("The source redirected too many times")
                    current_url = urljoin(current_url, location.decode("latin1"))
                    redirects += 1
                    continue
                if response.status >= 400:
                    await response.aread()
                    raise FetchError(f"The source returned HTTP {response.status}")

                content_type = (_header(response.headers, b"content-type") or b"").decode(
                    "latin1"
                ).split(";", 1)[0].strip().lower()
                if content_type not in ALLOWED_CONTENT_TYPES:
                    await response.aread()
                    raise UnsupportedContentTypeError(
                        "The source format cannot be read automatically"
                    )

                chunks: list[bytes] = []
                size = 0
                async for chunk in response.stream:
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise ResponseTooLargeError("The source is too large to capture")
                    chunks.append(chunk)
                return FetchedPage(
                    url=current_url,
                    content_type=content_type,
                    body=b"".join(chunks).decode("utf-8", errors="replace"),
                    redirects=redirects,
                )
    except TimeoutError as error:
        raise FetchTimeoutError("The source took too long to respond") from error
    except httpcore.NetworkError as error:
        raise FetchError("The source could not be fetched") from error
    finally:
        await pool.aclose()
