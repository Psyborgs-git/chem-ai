"""Research SSRF boundaries, bounded fetching and connector mapping."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from studio.domain.library import research
from studio.errors import DomainError, ErrorCode


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:secret@example.org/a",
        "http://example.org:22/",
        "https://example.org/\r\nX-Test:1",
        "http://example.org\\@127.0.0.1/",
    ],
)
def test_invalid_resource_urls_rejected(url: str) -> None:
    with pytest.raises(DomainError):
        research.public_url(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.1.1.1", "::1", "fc00::1"])
def test_private_and_mixed_dns_answers_blocked(monkeypatch: Any, address: str) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
        ],
    )
    with pytest.raises(DomainError) as denied:
        research.fetch_public("https://example.org/paper")
    assert denied.value.code == ErrorCode.FORBIDDEN


def test_fetch_pins_socket_address_and_revalidates_redirects(monkeypatch: Any) -> None:
    resolutions = []
    connections = []

    def resolve(host: str, port: int, **kwargs: Any) -> str:
        resolutions.append(host)
        if host == "internal.example":
            raise DomainError(ErrorCode.FORBIDDEN, "blocked private host")
        return "93.184.216.34"

    class Response:
        status = 302

        def getheader(self, key: str) -> str | None:
            return "http://internal.example/metadata" if key == "Location" else None

    class Connection:
        def __init__(self, host: str, port: int, address: str):
            connections.append((host, address))

        def request(self, *args: Any, **kwargs: Any) -> None:
            pass

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(research, "_resolve", resolve)
    monkeypatch.setattr(research, "_PinnedHTTP", Connection)
    with pytest.raises(DomainError):
        research.fetch_public("http://public.example/paper")
    assert connections == [("public.example", "93.184.216.34")]
    assert resolutions == ["public.example", "internal.example"]


def test_fetch_size_limit_applies_without_content_length(monkeypatch: Any) -> None:
    class Response:
        status = 200

        def getheader(self, key: str) -> None:
            return None

        def read(self, count: int) -> bytes:
            return b"x" * count

    class Connection:
        def __init__(self, *args: Any):
            pass

        def request(self, *args: Any, **kwargs: Any) -> None:
            pass

        def getresponse(self) -> Response:
            return Response()

        def close(self) -> None:
            pass

    monkeypatch.setattr(research, "_resolve", lambda *a, **kw: "93.184.216.34")
    monkeypatch.setattr(research, "_PinnedHTTPS", Connection)
    with pytest.raises(DomainError, match="size limit"):
        research.fetch_public("https://example.org/data", max_bytes=100)


def test_connector_mapping_and_no_simulated_web_results(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        research,
        "_json_get",
        lambda url, **kw: {
            "PropertyTable": {
                "Properties": [
                    {
                        "CID": 702,
                        "MolecularFormula": "C2H6O",
                        "MolecularWeight": "46.07",
                        "SMILES": "CCO",
                    }
                ]
            }
        },
    )
    compound = research.search_resources("pubchem", "ethanol")[0]
    assert compound["smiles"] == "CCO" and compound["formula"] == "C2H6O"
    assert compound["downloadUrl"].startswith("https://pubchem.ncbi.nlm.nih.gov/")
    monkeypatch.setenv("STUDIO_SEARXNG_URL", "")
    with pytest.raises(DomainError) as unavailable:
        research.search_resources("web", "ethanol papers")
    assert unavailable.value.code == ErrorCode.ENGINE_UNAVAILABLE
