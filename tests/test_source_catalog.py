import io

from cryptography.fernet import Fernet

from app.models import Episode, Movie, Series
from app.services.m3u import import_m3u
from app.services.source_catalog import build_catalog
from app.services.source_matching import attach
from app.source_models import MediaSource
from tests.test_tmdb import FakeClient


def test_entire_list_is_playable_without_tmdb_and_rebuild_is_idempotent(app, db):
    app.config['SOURCE_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    import_m3u(io.StringIO('''#EXTM3U
#EXTINF:-1,Filme
https://a.test/movie/1
#EXTINF:-1,Filme
https://a.test/movie/2
#EXTINF:-1,Show S01E01
https://a.test/series/3
#EXTINF:-1,Show S01E02
https://a.test/series/4
'''))
    assert build_catalog(batch_size=1) == {'linked': 4, 'unclassified': 0}
    assert db.session.query(Movie).count() == 1
    assert db.session.query(Series).count() == 1
    assert db.session.query(Episode).count() == 2
    movie = db.session.scalar(db.select(Movie))
    assert movie.has_playback and movie.tmdb_id is None
    assert len(movie.sources) == 2
    assert build_catalog(batch_size=2)['linked'] == 4
    assert db.session.query(Movie).count() == 1
    assert db.session.query(Episode).count() == 2
    source = db.session.get(MediaSource, 1)
    original_id = source.movie_id
    attach(source, 693134, FakeClient())
    assert source.movie_id == original_id
    assert db.session.query(Movie).count() == 1
    assert db.session.get(Movie, original_id).tmdb_id == 693134
    assert db.session.get(MediaSource, 2).movie_id == original_id
    episode_source = db.session.get(MediaSource, 3)
    original_episode = episode_source.episode_id
    attach(episode_source, 1396, FakeClient())
    assert episode_source.episode_id == original_episode
    assert db.session.get(Episode, original_episode).season.series.tmdb_id == 1396
    assert db.session.get(Episode, original_episode).title != 'Episódio 1'
    assert db.session.query(Series).count() == 1


def test_build_reuses_existing_tmdb_title(app, db):
    app.config['SOURCE_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    import_m3u(io.StringIO('#EXTINF:-1,Title\nhttps://a.test/1\n#EXTINF:-1,Title\nhttps://a.test/2'))
    source = db.session.get(MediaSource, 1)
    attach(source, 693134, FakeClient())
    build_catalog(batch_size=1)
    assert db.session.get(MediaSource, 2).movie_id == source.movie_id
    assert db.session.query(Movie).count() == 1
