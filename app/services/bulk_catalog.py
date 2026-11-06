"""Fila retomável e cache de metadados em disco para grandes catálogos."""
import json
import sqlite3
import time
from pathlib import Path

from sqlalchemy import func

from app.extensions import db
from app.models import Episode, Season, Series
from app.services.source_matching import match
from app.services.tmdb import TMDbClient, TMDbError
from app.source_models import MediaSource


class BatchClient(TMDbClient):
    def __init__(self, path, **kwargs):
        super().__init__(**kwargs)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.disk = sqlite3.connect(path)
        self.disk.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, expires REAL, body TEXT)')

    def _get(self, path, **params):
        key = json.dumps([self.language, self.region, path, params], sort_keys=True)
        row = self.disk.execute('SELECT expires, body FROM metadata WHERE key=?', (key,)).fetchone()
        if row and row[0] > time.time():
            return json.loads(row[1])
        for attempt in range(3):
            try:
                result = super()._get(path, **params)
                break
            except TMDbError as exc:
                if not exc.retryable or attempt == 2:
                    raise
                time.sleep(2 ** (attempt + 1))
        self.disk.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?)',
                          (key, time.time() + 7 * 86400, json.dumps(result)))
        self.disk.commit()
        return result

    def close(self):
        self.disk.close()
        self.session.close()


def process_queue(client, status='pending', limit=None, progress=None, kind=None):
    """Cada associação é confirmada; falha de API preserva a fonte pendente."""
    cursor = 0
    counts = {'processed': 0, 'matched': 0, 'review': 0}
    while limit is None or counts['processed'] < limit:
        size = min(100, limit - counts['processed']) if limit is not None else 100
        stmt = db.select(MediaSource.id).where(MediaSource.match_status == status, MediaSource.id > cursor)
        if kind:
            stmt = stmt.where(MediaSource.kind == kind)
        ids = list(db.session.scalars(stmt.order_by(MediaSource.id).limit(size)))
        if not ids:
            break
        for source_id in ids:
            source = db.session.get(MediaSource, source_id)
            try:
                match(source, client, allow_unique_title=True)
            except ValueError:
                db.session.rollback()
                source.match_status = 'review'
                db.session.commit()
            counts['processed'] += 1
            counts[source.match_status] += 1
            cursor = source_id
            if progress and (counts['processed'] % 100 == 0):
                progress(dict(counts))
            db.session.expunge_all()
    if progress:
        progress(dict(counts))
    return counts


def process_series_titles(client, limit=None, progress=None):
    # Uma consulta por série primeiro; episódios completos ficam para a próxima etapa.
    first = (db.select(func.min(MediaSource.id).label('source_id')).join(
        Episode, MediaSource.episode_id == Episode.id).join(Season, Episode.season_id == Season.id)
        .join(Series, Season.series_id == Series.id).where(Series.tmdb_id.is_(None))
        .group_by(Series.id))
    representatives = list(db.session.scalars(first))
    # Materializar os IDs evita um nested scan quadrático no planejador do SQLite.
    stmt = db.select(MediaSource.id).where(MediaSource.id.in_(representatives),
        MediaSource.match_status == 'pending').order_by(MediaSource.id)
    if limit:
        stmt = stmt.limit(limit)
    ids = list(db.session.scalars(stmt))
    counts = {'processed': 0, 'matched': 0, 'review': 0}
    for source_id in ids:
        source = db.session.get(MediaSource, source_id)
        try:
            match(source, client, allow_unique_title=True)
        except ValueError:
            db.session.rollback()
            source.match_status = 'review'
            db.session.commit()
        counts['processed'] += 1
        counts[source.match_status] += 1
        if progress and counts['processed'] % 10 == 0:
            progress(dict(counts))
        db.session.expunge_all()
    if progress:
        progress(dict(counts))
    return counts
