import threading
import time
from unittest.mock import Mock

import pytest

from app.models import Movie
from app.services.bulk_catalog import process_queue
from app.services.parallel_catalog import Cooldown
from app.services.source_catalog import build_catalog
from app.services.tmdb import TMDbClient, TMDbError
from app.source_models import MediaSource


class NetworkClient(TMDbClient):
    def __init__(self, shared=None):
        super().__init__()
        self.shared = shared or {'active': 0, 'peak': 0, 'lock': threading.Lock()}

    def clone(self):
        return NetworkClient(self.shared)

    def close(self):
        self.session.close()

    def _get(self, path, **params):
        with self.shared['lock']:
            self.shared['active'] += 1
            self.shared['peak'] = max(self.shared['peak'], self.shared['active'])
        try:
            time.sleep(0.025)
            if path == '/search/movie':
                ident = int(params['query'].split()[-1])
                return {'results': [{'id': ident, 'title': params['query']}]}
            ident = int(path.rsplit('/', 1)[-1])
            return {'id': ident, 'title': f'Title {ident}', 'overview': 'Metadata', 'genres': []}
        finally:
            with self.shared['lock']:
                self.shared['active'] -= 1


def test_parallel_network_preserves_single_catalog_and_resume(db):
    for n in range(1, 9):
        db.session.add(MediaSource(fingerprint=str(n), encrypted_url='unused', label=f'Title {n}',
                                   search_title=f'Title {n}', kind='movie'))
    db.session.commit()
    build_catalog(batch_size=3)
    writer = NetworkClient()
    counts = process_queue(writer, workers=4)
    assert counts == {'processed': 8, 'matched': 8, 'review': 0}
    assert writer.shared['peak'] > 1
    assert db.session.query(Movie).count() == 8
    assert db.session.query(Movie).filter(Movie.tmdb_id.is_not(None)).count() == 8
    assert process_queue(writer, workers=4)['processed'] == 0
    writer.close()


def test_parallel_api_failure_does_not_mark_source_complete(db):
    db.session.add(MediaSource(fingerprint='1', encrypted_url='unused', label='Title',
                               search_title='Title', kind='movie'))
    db.session.commit()
    writer = NetworkClient()
    failing = NetworkClient()
    failing._get = Mock(side_effect=TMDbError('offline'))
    writer.clone = Mock(return_value=failing)
    with pytest.raises(TMDbError):
        process_queue(writer, workers=2)
    assert db.session.get(MediaSource, 1).match_status == 'pending'
    writer.close()


def test_cooldown_waits_for_provider_pause(monkeypatch):
    current = [100.0]
    sleeps = []
    monkeypatch.setattr('app.services.parallel_catalog.time.monotonic', lambda: current[0])

    def sleep(seconds):
        sleeps.append(seconds)
        current[0] += seconds

    monkeypatch.setattr('app.services.parallel_catalog.time.sleep', sleep)
    gate = Cooldown()
    gate.defer(7)
    gate.wait()
    assert sleeps == [7]
