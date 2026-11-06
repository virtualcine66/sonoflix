"""Sondagem limitada, DNS fixado por conexão e redirecionamentos explícitos.
Não baixa filmes, não contorna desafios e não executa páginas do fornecedor.
"""
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import certifi
import urllib3

MESSAGES = {
    "host_not_allowed": "O domínio da fonte ou do redirecionamento não foi autorizado no servidor.",
    "unsafe_address": "Destino de rede não permitido.",
    "invalid_url": "Endereço de fonte inválido.",
    "network_error": "Não foi possível conectar ao fornecedor.",
    "timeout": "O fornecedor demorou demais para responder.",
    "access_denied": "O fornecedor recusou o acesso do servidor (401/403).",
    "not_found": "A fonte não foi encontrada (404).",
    "rate_limited": "O fornecedor limitou as consultas (429). Tente mais tarde.",
    "upstream_error": "O fornecedor respondeu com erro.",
    "html_response": "A fonte entregou uma página HTML, não um vídeo.",
    "unsupported_media": "Não foi identificada mídia MP4/HLS compatível nesta resposta.",
    "http_only": "A fonte final usa HTTP. É necessária uma fonte HTTPS ou integração de mídia.",
    "redirect_limit": "A fonte excedeu o limite de redirecionamentos.",
    "key_error": "A configuração de acesso às fontes precisa ser revisada pelo administrador.",
}


class SourceError(Exception):
    def __init__(self, code, host=None):
        self.code = code
        self.host = host
        super().__init__(MESSAGES[code])


def target(url, allowed_hosts):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").encode("idna").decode().lower()
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if (parts.scheme not in ("http", "https") or not host or parts.username or parts.password
                or port not in (80, 443) or any(ord(c) < 33 for c in url) or "\\" in url):
            raise SourceError("invalid_url")
    except (ValueError, UnicodeError) as exc:
        raise SourceError("invalid_url") from exc
    allowed = host in allowed_hosts or any(rule.startswith('.') and host.endswith(rule)
                                          for rule in allowed_hosts)
    if not allowed:
        raise SourceError("host_not_allowed", host=host)
    try:
        addresses = [row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    except OSError as exc:
        raise SourceError("network_error") from exc
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise SourceError("unsafe_address")
    return parts, host, port, addresses[0]


def probe(url, allowed_hosts, deadline=None):
    deadline = deadline or time.monotonic() + 12
    visited = set()
    for _ in range(6):
        if url in visited:
            raise SourceError("redirect_limit")
        visited.add(url)
        parts, host, port, ip = target(url, allowed_hosts)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError("timeout")
        kwargs = dict(port=port, timeout=urllib3.Timeout(total=remaining, connect=min(3, remaining),
                                                       read=min(3, remaining)), retries=False)
        if parts.scheme == "https":
            pool = urllib3.HTTPSConnectionPool(ip, server_hostname=host, assert_hostname=host,
                                              cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(), **kwargs)
        else:
            pool = urllib3.HTTPConnectionPool(ip, **kwargs)
        response = None
        try:
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            response = pool.urlopen("GET", path, headers={"Host": parts.netloc, "Range": "bytes=0-4095",
                                    "Accept-Encoding": "identity", "User-Agent": "Sonoflix-SourceCheck/1.0"},
                                    redirect=False, preload_content=False, retries=False)
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise SourceError("invalid_url")
                url = urljoin(url, location)
                continue
            codes = {401: "access_denied", 403: "access_denied", 404: "not_found", 429: "rate_limited"}
            if response.status not in (200, 206):
                raise SourceError(codes.get(response.status, "upstream_error"))
            body = response.read(1024, decode_content=False)
            stripped = body.lstrip(b"\xef\xbb\xbf \r\n\t")
            mime = response.headers.get("Content-Type", "").split(";")[0].lower()
            if stripped.lower().startswith((b"<!doctype html", b"<html")) or mime == "text/html":
                raise SourceError("html_response")
            if stripped.startswith(b"#EXTM3U"):
                kind = "hls"
            elif len(body) >= 12 and body[4:8] == b"ftyp":
                kind = "mp4"
            else:
                raise SourceError("unsupported_media")
            if parts.scheme != "https":
                # Verifica HTTPS de verdade; nunca entrega HTTP para uma página HTTPS.
                secure_host = f"[{host}]" if ":" in host else host
                url = urlunsplit(("https", secure_host, parts.path, parts.query, ""))
                if url in visited:
                    raise SourceError("http_only")
                continue
            return {"url": url, "type": kind, "host": host,
                    "cors": response.headers.get("Access-Control-Allow-Origin", ""),
                    "range": response.status == 206, "redirects": len(visited) - 1}
        except urllib3.exceptions.TimeoutError as exc:
            raise SourceError("timeout") from exc
        except (urllib3.exceptions.HTTPError, OSError) as exc:
            raise SourceError("network_error") from exc
        finally:
            if response:
                response.close()
            pool.close()
    raise SourceError("redirect_limit")
