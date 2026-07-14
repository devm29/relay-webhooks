import pytest

from relay.delivery.client import BlockedAddressError, resolve_public
from relay.domain.models import EndpointCreateIn


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.1.2.3", "169.254.169.254", "::1"])
async def test_non_public_addresses_are_refused_at_connect_time(host: str) -> None:
    with pytest.raises(BlockedAddressError):
        await resolve_public(host)


async def test_public_literal_addresses_pass() -> None:
    assert await resolve_public("1.1.1.1") == "1.1.1.1"


@pytest.mark.parametrize("name", ["Host", "content-length", "Transfer-Encoding", "Connection"])
def test_framing_and_hop_by_hop_headers_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="header"):
        EndpointCreateIn(url="https://hooks.example.com", headers={name: "x"})
