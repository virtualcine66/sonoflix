"""Funções utilitárias sem dependência de contexto da aplicação."""
import re
import unicodedata
from datetime import date
from urllib.parse import urljoin, urlparse

from flask import request

_YOUTUBE_PATTERNS = (
    re.compile(r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/))([\w-]{11})"),
    re.compile(r"youtu\.be/([\w-]{11})"),
    re.compile(r"^([\w-]{11})$"),
)


def slugify(value: str) -> str:
    """'Duna: Parte Dois' -> 'duna-parte-dois'."""
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug or "titulo"


def youtube_key(value: str | None) -> str | None:
    """Extrai o ID de 11 caracteres de um link do YouTube (ou do próprio ID)."""
    value = (value or "").strip()
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)
    return None


def parse_date(value: str | None) -> date | None:
    """Converte 'AAAA-MM-DD' do TMDb; datas vazias ou inválidas viram None."""
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def like_pattern(term: str) -> str:
    """Monta um padrão LIKE escapando curingas digitados pelo usuário."""
    escaped = term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def is_safe_url(target: str | None) -> bool:
    """Só aceita redirecionar para o próprio site (evita open redirect)."""
    if not target or "\\" in target:
        return False
    host = urlparse(request.host_url)
    resolved = urlparse(urljoin(request.host_url, target))
    return resolved.scheme in ("http", "https") and resolved.netloc == host.netloc


def safe_next(target: str | None, fallback: str) -> str:
    return target if is_safe_url(target) else fallback
