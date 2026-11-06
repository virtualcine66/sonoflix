"""Importação streaming: não consulta URLs nem o TMDB durante a leitura."""
import hashlib
import re
from urllib.parse import urlsplit

from app.extensions import db
from app.source_models import MediaSource, cipher

ATTR = re.compile(r'([\w-]+)="([^"\r\n]*)"')
EPISODE = re.compile(r"\b(?:S(\d{1,3})\s*E(\d{1,4})|(\d{1,3})x(\d{1,4}))\b", re.I)
YEAR = re.compile(r"\((19\d{2}|20\d{2})\)")
QUALITY = re.compile(r"\s*(?:\[(?:HD|FHD|4K|SD|DUB|LEG)\]|\b(?:2160p|1080p|720p|480p|H\.?264|H\.?265|HEVC)\b)", re.I)


def entries(stream):
    pending = None
    for number, raw in enumerate(stream, 1):
        line = raw.strip().lstrip("\ufeff")
        if len(line) > 16384:
            pending = None
            continue
        if line.startswith("#EXTINF:"):
            attrs = dict(ATTR.findall(line))
            # A vírgula do título pode aparecer também dentro de atributos entre aspas.
            tail = re.split(r',(?=(?:[^"\n]*"[^"\n]*")*[^"\n]*$)', line, maxsplit=1)
            pending = (attrs, tail[1].strip() if len(tail) > 1 else "", number)
        elif line and not line.startswith("#"):
            if pending and urlsplit(line).scheme in ("http", "https") and urlsplit(line).hostname:
                attrs, title, start = pending
                yield {"url": line, "title": (attrs.get("tvg-name") or title or "Sem título")[:500],
                       "group": attrs.get("group-title", "")[:255], "line": start}
            pending = None


def identity(title, url):
    episode = EPISODE.search(title)
    year = YEAR.search(title)
    kind = "series" if episode or urlsplit(url).path.startswith("/series/") else "movie"
    clean = title[:episode.start()] if episode else title
    clean = QUALITY.sub("", YEAR.sub("", clean)).strip(" -|.")
    return dict(search_title=clean or title, kind=kind, year=int(year[1]) if year else None,
                season_number=int(episode[1] or episode[3]) if episode else None,
                episode_number=int(episode[2] or episode[4]) if episode else None)


def import_m3u(stream, batch_size=500, limit=None, group=None, progress=None):
    cipher()  # Falha antes de gravar se a chave estiver ausente.
    total = {"read": 0, "created": 0, "existing": 0}
    batch = []
    def flush():
        fingerprints = [hashlib.sha256(x["url"].encode()).hexdigest() for x in batch]
        known = set(db.session.scalars(db.select(MediaSource.fingerprint).where(
            MediaSource.fingerprint.in_(fingerprints))))
        for item, fingerprint in zip(batch, fingerprints, strict=True):
            if fingerprint in known:
                total["existing"] += 1
                continue
            source = MediaSource(fingerprint=fingerprint, label=item["title"], group_name=item["group"],
                                 **identity(item["title"], item["url"]))
            source.set_url(item["url"])
            db.session.add(source)
            known.add(fingerprint)
            total["created"] += 1
        db.session.commit()
        batch.clear()
        if progress:
            progress(dict(total))
    for item in entries(stream):
        if group and group.casefold() not in item["group"].casefold():
            continue
        total["read"] += 1
        batch.append(item)
        if len(batch) >= batch_size:
            flush()
        if limit and total["read"] >= limit:
            break
    if batch:
        flush()
    return total
