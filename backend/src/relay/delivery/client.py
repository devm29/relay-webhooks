import asyncio
import ipaddress
import socket
import time
import typing
from dataclasses import dataclass

import httpcore
import httpx

USER_AGENT = "Relay-Webhooks/0.1"


@dataclass(frozen=True, slots=True)
class SendResult:
    status_code: int | None
    latency_ms: int
    error: str | None = None
    response_snippet: str | None = None
    retry_after: str | None = None

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300


class BlockedAddressError(httpx.ConnectError):
    pass


class WebhookSender:
    def __init__(self, client: httpx.AsyncClient, *, snippet_bytes: int) -> None:
        self._client = client
        self._snippet_bytes = snippet_bytes

    async def send(
        self, url: str, body: bytes, headers: dict[str, str], *, timeout: float
    ) -> SendResult:
        started = time.perf_counter()

        def elapsed() -> int:
            return round((time.perf_counter() - started) * 1000)

        # httpx timeouts apply per phase, so a receiver that drips its response one byte at
        # a time would never trip them. The overall deadline keeps an attempt inside its lease.
        try:
            async with (
                asyncio.timeout(timeout),
                self._client.stream(
                    "POST", url, content=body, headers=headers, timeout=timeout
                ) as response,
            ):
                snippet = await self._read_snippet(response)
                return SendResult(
                    status_code=response.status_code,
                    latency_ms=elapsed(),
                    response_snippet=snippet,
                    retry_after=response.headers.get("retry-after"),
                )
        except (TimeoutError, httpx.TimeoutException):
            return SendResult(None, elapsed(), error=f"timed out after {timeout:g}s")
        except BlockedAddressError as exc:
            return SendResult(None, elapsed(), error=str(exc))
        except httpx.ConnectError as exc:
            return SendResult(None, elapsed(), error=f"connection failed: {exc}")
        except httpx.HTTPError as exc:
            return SendResult(None, elapsed(), error=f"{type(exc).__name__}: {exc}")

    async def _read_snippet(self, response: httpx.Response) -> str | None:
        buffer = bytearray()
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) >= self._snippet_bytes:
                break
        if not buffer:
            return None
        return bytes(buffer[: self._snippet_bytes]).decode("utf-8", errors="replace")


class PublicOnlyBackend(httpcore.AsyncNetworkBackend):
    """Resolves the host itself and connects to the vetted address.

    Checking at connect time, rather than when the endpoint is saved, is what defeats DNS
    rebinding: the address that is checked is the address that is dialled. TLS still
    verifies against the original hostname because httpcore passes it separately.
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        address = await resolve_public(host)
        return await self._inner.connect_tcp(
            address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise BlockedAddressError("unix sockets are not allowed as webhook targets")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


async def resolve_public(host: str) -> str:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise httpx.ConnectError(f"cannot resolve {host!r}") from exc
    addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    blocked = [a for a in addresses if not a.is_global]
    if blocked or not addresses:
        raise BlockedAddressError(
            f"refused to connect: {host!r} resolves to non-public address {blocked[0]}"
            if blocked
            else f"refused to connect: {host!r} has no addresses"
        )
    return str(addresses[0])


class PublicOnlyTransport(httpx.AsyncHTTPTransport):
    def __init__(self, *, limits: httpx.Limits) -> None:
        super().__init__(limits=limits, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            network_backend=PublicOnlyBackend(),
        )


def build_http_client(*, allow_private: bool) -> httpx.AsyncClient:
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    transport = None if allow_private else PublicOnlyTransport(limits=limits)
    return httpx.AsyncClient(
        follow_redirects=False,
        headers={"user-agent": USER_AGENT},
        limits=limits,
        transport=transport,
        trust_env=allow_private,
    )
