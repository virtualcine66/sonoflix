"""Consultas paralelas; apenas a thread principal escreve no catálogo SQLite."""
import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from app.extensions import db
from app.models import Episode, Movie, Season, Series
from app.services.source_catalog import source_key
from app.services.source_matching import choose_candidate, match
from app.services.tmdb import TMDbClient, TMDbError
from app.source_models import MediaSource


class Cooldown:
    def __init__(self):
        self.lock = threading.Lock()
        self.until = 0.0

    def defer(self, seconds):
        with self.lock:
            self.until = max(self.until, time.monotonic() + seconds)

    def wait(self):
        while True:
            with self.lock:
                delay = self.until - time.monotonic()
            if delay <= 0:
                return
            time.sleep(delay)


class PreparedClient(TMDbClient):
    def __init__(self, fallback):
        self.fallback = fallback
        self.language = fallback.language
        self.responses = {}

    def _get(self, path, **params):
        key = json.dumps([path, params], sort_keys=True)
        if key not in self.responses:
            self.responses[key] = self.fallback._get(path, **params)
        return self.responses[key]


def descriptors(ids):
    for start in range(0, len(ids), 100):
        stmt = db.select(MediaSource.id, MediaSource.kind, MediaSource.search_title, MediaSource.year,
                         MediaSource.season_number, Movie.tmdb_id, Movie.catalog_key,
                         Series.tmdb_id, Series.catalog_key).outerjoin(
            Movie, MediaSource.movie_id == Movie.id).outerjoin(
            Episode, MediaSource.episode_id == Episode.id).outerjoin(
            Season, Episode.season_id == Season.id).outerjoin(
            Series, Season.series_id == Series.id).where(MediaSource.id.in_(ids[start:start + 100]))
        for sid, kind, title, year, season, mid, mkey, tid, tkey in db.session.execute(stmt).all():
            key = source_key(kind, title, year)
            known = mid if mkey == key else tid if tkey == key else None
            yield {'id': sid, 'kind': kind, 'title': title, 'year': year, 'season': season, 'known': known}


def prepare(descriptor, client):
    prepared = PreparedClient(client)
    chosen = descriptor['known']
    if not chosen:
        results = prepared.search(descriptor['title'], descriptor['kind'])
        chosen = choose_candidate(descriptor['title'], descriptor['kind'], descriptor['year'], results, True)
    if chosen:
        if descriptor['kind'] == 'movie':
            prepared.movie(chosen)
        else:
            prepared.tv(chosen)
            if descriptor['season'] is not None:
                try:
                    prepared.season(chosen, descriptor['season'])
                except TMDbError as exc:
                    if exc.status_code != 404:
                        raise
    return prepared


def process_parallel(ids, writer, workers, counts, progress=None):
    cooldown = Cooldown()
    local = threading.local()
    clients, clients_lock = [], threading.Lock()

    def fetch(descriptor):
        if not hasattr(local, 'client'):
            local.client = writer.clone()
            local.client.cooldown = cooldown
            local.client.before_request = cooldown.wait
            with clients_lock:
                clients.append(local.client)
        return prepare(descriptor, local.client)

    pending = {}
    source_rows = iter(descriptors(ids))
    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='tmdb')
    try:
        while True:
            while len(pending) < workers * 2:
                descriptor = next(source_rows, None)
                if descriptor is None:
                    break
                pending[pool.submit(fetch, descriptor)] = descriptor['id']
            if not pending:
                break
            completed, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                source_id = pending.pop(future)
                prepared = future.result()
                # Workers nunca compartilham sua conexão/sessão com o escritor.
                prepared.fallback = writer
                source = db.session.get(MediaSource, source_id)
                try:
                    match(source, prepared, allow_unique_title=True)
                except ValueError:
                    db.session.rollback()
                    source.match_status = 'review'
                    db.session.commit()
                counts['processed'] += 1
                counts[source.match_status] += 1
                if progress and counts['processed'] % 10 == 0:
                    progress(dict(counts))
                db.session.expunge_all()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        for client in clients:
            client.close()
