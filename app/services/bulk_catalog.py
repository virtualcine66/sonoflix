"""Fila retomável e cache de metadados em disco para grandes catálogos."""
import json
import sqlite3
import time
from pathlib import Path

from app.extensions import db
from app.services.source_matching import match
from app.services.tmdb import TMDbClient
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
        result = super()._get(path, **params)
        self.disk.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?, ?)',
                          (key, time.time() + 7 * 86400, json.dumps(result)))
        self.disk.commit()
        return result

    def close(self):
        self.disk.close()
        self.session.close()


def process_queue(client, status='pending', limit=None, progress=None):
    """Cada associação é confirmada; falha de API preserva a fonte pendente."""
    cursor = 0
    counts = {'processed': 0, 'matched': 0, 'review': 0}
    while limit is None or counts['processed'] < limit:
        size = min(100, limit - counts['processed']) if limit is not None else 100
        ids = list(db.session.scalars(db.select(MediaSource.id).where(
            MediaSource.match_status == status, MediaSource.id > cursor)
            .order_by(MediaSource.id).limit(size)))
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
