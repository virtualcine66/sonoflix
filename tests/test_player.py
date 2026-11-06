import pytest

from app.models import Episode, Movie, Season


def test_watch_requires_a_configured_source(client, catalog):
    assert client.get(f"/watch/movie/{catalog['movie'].id}").status_code == 404
    assert client.get("/watch/series/1").status_code == 404
    assert client.get("/watch/episode/9999").status_code == 404


def test_movie_playback_and_scoped_csp(client, db, catalog):
    movie = catalog["movie"]
    movie.video_url = "https://media.example.com/master.m3u8?token=abc&x=1"
    movie.video_type = "hls"
    movie.subtitle_url = "/static/captions/movie.vtt"
    db.session.commit()
    response = client.get(f"/watch/movie/{movie.id}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-type="hls"' in html
    assert 'playsinline' in html
    assert 'kind="subtitles"' in html
    assert 'token=abc&amp;x=1' in html
    assert "hls.min.js" in html
    assert 'data-next' not in html
    assert "media-src 'self' https: blob:" in response.headers["Content-Security-Policy"]
    assert "connect-src 'self' https:" in response.headers["Content-Security-Policy"]
    assert "connect-src 'self' https:" not in client.get("/").headers["Content-Security-Policy"]
    assert f'/watch/movie/{movie.id}' in client.get(f"/movie/{movie.id}/{movie.slug}").get_data(as_text=True)


def test_episode_playback_next_season_and_missing_sources(client, db, catalog):
    series = catalog["series"]
    first_season = series.seasons.first()
    second_season = Season(series=series, season_number=2)
    first = Episode(season=first_season, episode_number=1, title="Primeiro", video_url="/static/one.mp4")
    unavailable = Episode(season=first_season, episode_number=2, title="Sem fonte")
    last = Episode(season=second_season, episode_number=1, title="Depois", video_url="/static/two.mp4")
    db.session.add_all([second_season, first, unavailable, last])
    db.session.commit()
    html = client.get(f"/watch/episode/{first.id}").get_data(as_text=True)
    assert f'/watch/episode/{last.id}' in html
    assert f'/watch/episode/{unavailable.id}' not in html
    assert 'data-next' not in client.get(f"/watch/episode/{last.id}").get_data(as_text=True)
    detail = client.get(f"/series/{series.id}/{series.slug}").get_data(as_text=True)
    assert f'/watch/episode/{first.id}' in detail
    assert f'/watch/episode/{unavailable.id}' not in detail


@pytest.mark.parametrize("source", ["javascript:alert(1)", "//evil.example/v.mp4", "http://evil.example/v.mp4",
                                     "/\\evil.example/v.mp4", "https://user:password@example.com/v.mp4"])
def test_admin_rejects_unsafe_media_sources(admin_client, db, source):
    response = admin_client.post("/admin/movie/add", data={"title": "Inválido", "video_url": source})
    assert response.status_code == 200
    assert "Use uma URL HTTPS" in response.get_data(as_text=True)
    assert db.session.scalar(db.select(Movie).filter_by(title="Inválido")) is None


def test_admin_saves_movie_and_episode_sources(admin_client, db, catalog):
    result = admin_client.post("/admin/movie/add", data={
        "title": "Vídeo próprio", "video_url": "https://media.example.com/stream?token=1",
        "video_type": "hls", "subtitle_url": "/static/pt.vtt",
    })
    assert result.status_code == 302
    movie = db.session.scalar(db.select(Movie).filter_by(title="Vídeo próprio"))
    assert movie.video_type == "hls"
    assert movie.subtitle_url == "/static/pt.vtt"
    season = catalog["series"].seasons.first()
    result = admin_client.post(f"/admin/season/{season.id}/episodes/add", data={
        "episode_number": "1", "title": "Piloto", "video_url": "/static/pilot.mp4", "video_type": "mp4",
    })
    assert result.status_code == 302
    episode = season.episodes.first()
    assert episode.video_url == "/static/pilot.mp4"
    assert episode.video_type == "mp4"


def test_watch_escapes_title_and_source(client, db, catalog):
    movie = catalog["movie"]
    movie.title = '<script>alert("x")</script>'
    movie.video_url = 'https://media.example.com/a.mp4?x=" onerror="alert(1)'
    db.session.commit()
    html = client.get(f"/watch/movie/{movie.id}").get_data(as_text=True)
    assert '<script>alert(' not in html
    assert 'src="https://media.example.com/a.mp4?x=" onerror=' not in html


@pytest.mark.parametrize("source,format_,expected", [
    ("https://media.example.com/movie.mp4", "mp4", False),
    ("/static/movie.webm", "auto", False),
    ("https://media.example.com/stream?token=1", "hls", True),
    ("https://media.example.com/MASTER.M3U8?token=1#t=0", "auto", True),
])
def test_hls_library_only_loads_when_needed(client, db, catalog, source, format_, expected):
    movie = catalog["movie"]
    movie.video_url, movie.video_type = source, format_
    db.session.commit()
    html = client.get(f"/watch/movie/{movie.id}").get_data(as_text=True)
    assert ("vendor/hls.min.js" in html) is expected
    assert 'data-options hidden' in html
    assert "js/player.js" not in client.get("/").get_data(as_text=True)
    assert "vendor/hls.min.js" not in client.get("/").get_data(as_text=True)
