from unittest.mock import Mock

import pytest

from app.services.bulk_catalog import BatchClient, process_queue, process_series_titles
from app.services.source_catalog import build_catalog
from app.services.source_matching import match
from app.services.tmdb import TMDbClient, TMDbError
from app.source_models import MediaSource


def add_sources(db, count):
    for n in range(count):
        db.session.add(MediaSource(fingerprint=str(n), encrypted_url='unused', label='Title',
                                   search_title='Title', kind='movie'))
    db.session.commit()


def test_disk_cache_survives_restart_and_separates_language(tmp_path, monkeypatch):
    get = Mock(return_value={'results': []})
    monkeypatch.setattr(TMDbClient, '_get', get)
    path = tmp_path / 'cache.db'
    first = BatchClient(path)
    first._get('/search/movie', query='Title')
    first.close()
    second = BatchClient(path)
    assert second._get('/search/movie', query='Title') == {'results': []}
    assert get.call_count == 1
    second.close()
    third = BatchClient(path, language='en-US')
    third._get('/search/movie', query='Title')
    assert get.call_count == 2
    third.close()


def test_queue_crosses_batch_boundary_and_resumes(db, monkeypatch):
    add_sources(db, 205)
    visited = []

    def fake_match(source, client, **kwargs):
        visited.append(source.id)
        source.match_status = 'review'
        db.session.commit()

    monkeypatch.setattr('app.services.bulk_catalog.match', fake_match)
    assert process_queue(Mock(), limit=103)['processed'] == 103
    assert process_queue(Mock())['processed'] == 102
    assert len(set(visited)) == 205
    assert process_queue(Mock())['processed'] == 0


def test_api_failure_leaves_current_item_pending(db, monkeypatch):
    add_sources(db, 1)
    monkeypatch.setattr('app.services.bulk_catalog.match', Mock(side_effect=TMDbError('offline')))
    with pytest.raises(TMDbError):
        process_queue(Mock())
    db.session.rollback()
    assert db.session.get(MediaSource, 1).match_status == 'pending'


def test_no_year_only_matches_single_exact_candidate(db, monkeypatch):
    add_sources(db, 1)
    source = db.session.get(MediaSource, 1)
    client = Mock()
    client.search.return_value = [{'tmdb_id': 1, 'title': 'Title', 'year': '2024'}]
    attach = Mock()
    monkeypatch.setattr('app.services.source_matching.attach', attach)
    match(source, client, allow_unique_title=True)
    attach.assert_called_once_with(source, 1, client)
    attach.reset_mock()
    client.search.return_value.append({'tmdb_id': 2, 'title': 'Title', 'year': '1990'})
    match(source, client, allow_unique_title=True)
    attach.assert_not_called()
    assert source.match_status == 'review'


def test_series_titles_are_processed_once_per_show(db, monkeypatch):
    for ident, title, episode in ((1, 'First', 1), (2, 'First', 2), (3, 'Second', 1)):
        db.session.add(MediaSource(fingerprint=str(ident), encrypted_url='unused', label=title,
                                   search_title=title, kind='series', season_number=1, episode_number=episode))
    db.session.commit()
    build_catalog()
    visited = []

    def fake_match(source, client, **kwargs):
        visited.append(source.search_title)
        source.match_status = 'review'
        db.session.commit()

    monkeypatch.setattr('app.services.bulk_catalog.match', fake_match)
    assert process_series_titles(Mock())['processed'] == 2
    assert visited == ['First', 'Second']
    assert process_series_titles(Mock())['processed'] == 0


def test_transient_tmdb_failure_is_retried(tmp_path, monkeypatch):
    get = Mock(side_effect=[TMDbError('offline', retryable=True), {'results': []}])
    monkeypatch.setattr(TMDbClient, '_get', get)
    monkeypatch.setattr('app.services.bulk_catalog.time.sleep', Mock())
    client = BatchClient(tmp_path / 'cache.db')
    assert client._get('/search/tv', query='show') == {'results': []}
    assert get.call_count == 2
    client.close()
