"""Public research connectors with DNS-pinned, bounded resource fetching.

References: https://help.openalex.org/api/searching/
https://www.crossref.org/documentation/retrieve-metadata/rest-api/
https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from typing import Any
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit

from studio.errors import DomainError, ErrorCode

MAX_DOWNLOAD_BYTES = 24 * 1024 * 1024
MAX_TEXT_CHARS = 500_000
_TIMEOUT = 20
_REDIRECTS = {301, 302, 303, 307, 308}


@dataclass(frozen=True)
class Download:
    url: str
    media_type: str
    body: bytes


def public_url(url: str) -> str:
    """Validate URL syntax before resolution; no credentials or arbitrary ports."""
    if len(url) > 6000 or any(ord(ch) < 32 for ch in url) or "\\" in url:
        raise DomainError(ErrorCode.VALIDATION, "invalid resource URL")
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
        if (
            parts.scheme not in {"http", "https"}
            or not hostname
            or parts.username is not None
            or parts.password is not None
            or port not in {None, 80, 443}
        ):
            raise ValueError
        host = hostname.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        raise DomainError(ErrorCode.VALIDATION, "use a public HTTP or HTTPS resource URL") from None
    host = f"[{host}]" if ":" in host else host
    netloc = host + (f":{port}" if port else "")
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def _resolve(host: str, port: int, *, trusted_endpoint: bool = False) -> str:
    try:
        addresses = list(
            dict.fromkeys(
                entry[4][0] for entry in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            )
        )
    except OSError:
        raise DomainError(
            ErrorCode.RESOURCE_UNAVAILABLE, "resource host could not be resolved"
        ) from None
    if not addresses or any(
        not ipaddress.ip_address(address).is_global or ipaddress.ip_address(address).is_multicast
        for address in addresses
    ):
        if not trusted_endpoint:
            raise DomainError(ErrorCode.FORBIDDEN, "resource host must resolve to public addresses")
    # Resolution is performed once and the actual socket uses this exact address.
    return str(addresses[0])


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, address: str) -> None:
        super().__init__(host, port, timeout=_TIMEOUT)
        self._address = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._address, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, address: str) -> None:
        self._tls_context = ssl.create_default_context()
        super().__init__(host, port, timeout=_TIMEOUT, context=self._tls_context)
        self._address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, self.port), self.timeout)
        try:
            self.sock = self._tls_context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch_public(
    url: str, *, max_bytes: int = MAX_DOWNLOAD_BYTES, trusted_endpoint: str | None = None
) -> Download:
    """Follow public redirects, verify TLS by original hostname and cap all bytes.

    trusted_endpoint is exclusively for the operator-configured SearXNG service.
    Redirects from it may not change origin; user-supplied fetch URLs never use it.
    """
    current = url
    trusted_origin = None
    if trusted_endpoint:
        configured = urlsplit(trusted_endpoint)
        trusted_origin = (configured.scheme, configured.hostname, configured.port)
    for _ in range(4):
        if trusted_origin is None:
            current = public_url(current)
        parts = urlsplit(current)
        origin = (parts.scheme, parts.hostname, parts.port)
        if trusted_origin is not None and origin != trusted_origin:
            raise DomainError(
                ErrorCode.FORBIDDEN, "search endpoint redirects must keep their origin"
            )
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username:
            raise DomainError(ErrorCode.VALIDATION, "invalid search endpoint")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        address = _resolve(parts.hostname, port, trusted_endpoint=trusted_origin is not None)
        cls = _PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP
        connection = cls(parts.hostname, port, address)
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parts.query:
            path += "?" + quote(parts.query, safe="%=&;:+,/@!?-._~")
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": "ChemistryStudio/0.1 (research resource archive)",
                    "Accept-Encoding": "identity",
                    "Accept": "application/json,text/html,application/pdf,text/plain,*/*;q=0.5",
                },
            )
            response = connection.getresponse()
            if response.status in _REDIRECTS:
                location = response.getheader("Location")
                if not location:
                    raise DomainError(
                        ErrorCode.RESOURCE_UNAVAILABLE, "resource redirect is incomplete"
                    )
                target = urljoin(current, location)
                if parts.scheme == "https" and urlsplit(target).scheme != "https":
                    raise DomainError(
                        ErrorCode.FORBIDDEN, "HTTPS resource redirected to an insecure URL"
                    )
                current = target
                continue
            if not 200 <= response.status < 300:
                raise DomainError(
                    ErrorCode.RESOURCE_UNAVAILABLE,
                    f"resource returned HTTP {response.status}",
                    retryable=response.status in {429, 502, 503, 504},
                )
            encoding = (response.getheader("Content-Encoding") or "identity").lower()
            if encoding not in {"", "identity"}:
                raise DomainError(
                    ErrorCode.VALIDATION, "resource ignored the uncompressed download request"
                )
            length = response.getheader("Content-Length")
            if length and (not length.isdecimal() or int(length) > max_bytes):
                raise DomainError(ErrorCode.VALIDATION, "resource exceeds the download size limit")
            chunks: list[bytes] = []
            total = 0
            while chunk := response.read(min(64 * 1024, max_bytes - total + 1)):
                total += len(chunk)
                if total > max_bytes:
                    raise DomainError(
                        ErrorCode.VALIDATION, "resource exceeds the download size limit"
                    )
                chunks.append(chunk)
            media_type = response.getheader("Content-Type") or "application/octet-stream"
            return Download(current, media_type.split(";", 1)[0].lower(), b"".join(chunks))
        except (OSError, http.client.HTTPException, ValueError):
            raise DomainError(
                ErrorCode.RESOURCE_UNAVAILABLE, "resource download failed", retryable=True
            ) from None
        finally:
            connection.close()
    raise DomainError(ErrorCode.VALIDATION, "resource exceeded the redirect limit")


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def readable_text(download: Download) -> str:
    if download.media_type == "application/pdf" or download.body.startswith(b"%PDF-"):
        from pypdf import PdfReader

        try:
            reader = PdfReader(BytesIO(download.body))
            result: list[str] = []
            count = 0
            for number, page in enumerate(reader.pages[:200], 1):
                text = page.extract_text() or ""
                result.append(f"\n[Page {number}]\n{text}")
                count += len(text)
                if count >= MAX_TEXT_CHARS:
                    break
            return "\n".join(result)[:MAX_TEXT_CHARS]
        except Exception:
            # Original bytes remain archived; a failed parser is not fabricated text.
            return ""
    if not (
        download.media_type.startswith("text/")
        or download.media_type in {"application/json", "application/xml", "application/xhtml+xml"}
    ):
        return ""
    decoded = download.body.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
    if "html" in download.media_type:
        parser = _ReadableHTML()
        parser.feed(decoded)
        return "\n".join(
            line.strip() for line in "".join(parser.parts).splitlines() if line.strip()
        )
    if download.media_type == "application/json":
        try:
            return json.dumps(json.loads(decoded), ensure_ascii=False, indent=2)[:MAX_TEXT_CHARS]
        except (ValueError, RecursionError):
            pass
    return decoded


def _json_get(url: str, *, trusted_endpoint: str | None = None) -> dict[str, Any]:
    downloaded = fetch_public(url, max_bytes=4 * 1024 * 1024, trusted_endpoint=trusted_endpoint)
    try:
        result = json.loads(downloaded.body)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, RecursionError):
        raise DomainError(
            ErrorCode.RESOURCE_UNAVAILABLE, "research service returned invalid JSON"
        ) from None


def _crossref_year(item: dict[str, Any]) -> int | None:
    dates = (item.get("published") or {}).get("date-parts") or []
    if dates and isinstance(dates[0], list) and dates[0] and isinstance(dates[0][0], int):
        return int(dates[0][0])
    return None


def search_resources(connector: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    query = query.strip()
    if not query or len(query) > 500:
        raise DomainError(ErrorCode.VALIDATION, "research query must contain 1-500 characters")
    limit = max(1, min(limit, 20))
    if connector == "openalex":
        params: dict[str, Any] = {"search": query, "per-page": limit}
        if key := os.environ.get("STUDIO_OPENALEX_API_KEY"):
            params["api_key"] = key
        body = _json_get("https://api.openalex.org/works?" + urlencode(params))
        results = []
        for item in body.get("results", [])[:limit]:
            location = item.get("best_oa_location") or item.get("primary_location") or {}
            results.append(
                {
                    "id": item.get("id"),
                    "connector": connector,
                    "title": item.get("display_name") or "Untitled work",
                    "doi": item.get("doi"),
                    "url": location.get("landing_page_url") or item.get("doi") or item.get("id"),
                    "downloadUrl": location.get("pdf_url"),
                    "year": item.get("publication_year"),
                    "openAccess": bool((item.get("open_access") or {}).get("is_oa")),
                    "license": location.get("license"),
                    "authors": [
                        {
                            "name": (author.get("author") or {}).get("display_name"),
                            "orcid": (author.get("author") or {}).get("orcid"),
                        }
                        for author in item.get("authorships", [])
                    ],
                    "venue": (location.get("source") or {}).get("display_name"),
                    "publisher": item.get("publisher"),
                    "locator": {"workId": item.get("id"), "doi": item.get("doi")},
                }
            )
        return results
    if connector == "crossref":
        body = _json_get(
            "https://api.crossref.org/works?" + urlencode({"query": query, "rows": limit})
        )
        return [
            {
                "id": item.get("DOI"),
                "connector": connector,
                "title": next(iter(item.get("title") or []), "Untitled work"),
                "doi": item.get("DOI"),
                "url": item.get("URL"),
                "downloadUrl": next(
                    (
                        link.get("URL")
                        for link in item.get("link", [])
                        if link.get("content-type") == "application/pdf"
                    ),
                    None,
                ),
                "citation": {"doi": item.get("DOI"), "publisher": item.get("publisher")},
                "authors": [
                    {
                        "given": author.get("given"),
                        "family": author.get("family"),
                        "name": " ".join(filter(None, [author.get("given"), author.get("family")])),
                    }
                    for author in item.get("author", [])
                ],
                "year": _crossref_year(item),
                "publisher": item.get("publisher"),
                "license": item.get("license"),
                "locator": {
                    "doi": item.get("DOI"),
                    "page": item.get("page"),
                    "volume": item.get("volume"),
                    "issue": item.get("issue"),
                },
            }
            for item in body.get("message", {}).get("items", [])[:limit]
        ]
    if connector == "pubchem":
        body = _json_get(
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
            + quote(query, safe="")
            + "/property/MolecularFormula,MolecularWeight,SMILES/JSON"
        )
        return [
            {
                "id": str(item.get("CID")),
                "connector": connector,
                "title": f"{query} · PubChem CID {item.get('CID')}",
                "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{item.get('CID')}",
                "downloadUrl": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/"
                f"{item.get('CID')}/property/MolecularFormula,MolecularWeight,SMILES/JSON",
                "formula": item.get("MolecularFormula"),
                "molecularWeight": item.get("MolecularWeight"),
                "smiles": item.get("SMILES") or item.get("ConnectivitySMILES"),
            }
            for item in body.get("PropertyTable", {}).get("Properties", [])[:limit]
        ]
    if connector == "web":
        endpoint = os.environ.get("STUDIO_SEARXNG_URL", "http://127.0.0.1:8088").strip().rstrip("/")
        if not endpoint:
            raise DomainError(
                ErrorCode.ENGINE_UNAVAILABLE, "configure STUDIO_SEARXNG_URL for web search"
            )
        configured = urlsplit(endpoint)
        if configured.query or configured.fragment or configured.username or configured.password:
            raise DomainError(ErrorCode.VALIDATION, "search endpoint must be a plain service URL")
        try:
            body = _json_get(
                endpoint + "/search?" + urlencode({"q": query, "format": "json"}),
                trusted_endpoint=endpoint,
            )
        except DomainError as exc:
            if exc.code == ErrorCode.RESOURCE_UNAVAILABLE:
                raise DomainError(
                    ErrorCode.ENGINE_UNAVAILABLE,
                    "Start the app search service with infra/local/research-search.sh, "
                    "or check the configured STUDIO_SEARXNG_URL",
                ) from None
            raise
        return [
            {
                "id": item.get("url"),
                "connector": connector,
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": item.get("content", "")[:1000],
            }
            for item in body.get("results", [])[:limit]
        ]
    raise DomainError(ErrorCode.VALIDATION, "unknown research connector")
