import io
import json
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet

from app.services.importer import import_title
from app.services.m3u import entries, identity, import_m3u
from app.services.source_matching import attach, match
from app.services.source_resolver import SourceError, probe, target
from app.source_models import MediaSource
from tests.test_tmdb import FakeClient


@pytest.fixture
def sources_config(app):
    app.config["SOURCE_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    app.config["SOURCE_ALLOWED_HOSTS"] = "origin.test,cdn.test"
    return app


def playlist():
    return io.StringIO('#EXTM3U\n#EXTINF:-1 tvg-name="Filme (2024)" group-title="Filmes",Filme\n'
                       'http://origin.test/movie/private/password/1.mp4\n'
                       '#EXTINF:-1 tvg-name="Série S01E02" group-title="Séries",Episódio\n'
                       'http://origin.test/series/private/password/2.mp4\n')


def test_import_is_encrypted_batched_and_repeatable(sources_config, db):
    first = import_m3u(playlist(), batch_size=1)
    assert first == {"read": 2, "created": 2, "existing": 0}
    assert import_m3u(playlist())["existing"] == 2
    source = db.session.get(MediaSource, 1)
    assert "password" not in source.encrypted_url
    assert source.get_url().endswith("/1.mp4")
    second = db.session.get(MediaSource, 2)
    assert (second.search_title, second.season_number, second.episode_number) == ("Série", 1, 2)


def test_parser_handles_commas_and_discards_orphan_urls():
    data = '#EXTM3U\nhttps://orphan.test/a\n#EXTINF:-1 group-title="A,B",One, Two\nhttps://x.test/a\n'
    rows = list(entries(io.StringIO(data)))
    assert len(rows) == 1
    assert rows[0]["title"] == "One, Two"
    assert rows[0]["group"] == "A,B"
    assert identity("Show 02x03 1080p", "https://x.test/a")["season_number"] == 2


def test_key_required_before_import(app, db):
    app.config["SOURCE_ENCRYPTION_KEY"] = ""
    with pytest.raises(ValueError):
        import_m3u(playlist())
    assert db.session.query(MediaSource).count() == 0


def test_movie_matching_requires_year_and_exact_unique_name(sources_config, db):
    import_m3u(playlist())
    source = db.session.get(MediaSource, 1)
    client = Mock()
    client.search.return_value = [{"tmdb_id": 1, "title": "Filme", "year": "2023"}]
    match(source, client)
    assert source.match_status == "review"
    client.movie.assert_not_called()


def test_bind_movie_and_preserve_episode_sources(sources_config, db):
    import_m3u(playlist())
    source = db.session.get(MediaSource, 1)
    attach(source, 693134, FakeClient())
    assert source.movie_id and source.match_status == "matched"
    series = import_title(FakeClient(), "series", 1396)
    episode = series.seasons.first().episodes.first()
    episode.video_url = "https://media.test/original.mp4"
    source2 = db.session.get(MediaSource, 2)
    source2.episode_id = episode.id
    old_id = episode.id
    db.session.commit()
    import_title(FakeClient(), "series", 1396)
    assert series.seasons.first().episodes.first().id == old_id
    assert series.seasons.first().episodes.first().video_url.endswith("original.mp4")
    assert db.session.get(MediaSource, 2).episode_id == old_id


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"])
def test_blocks_internal_dns(monkeypatch, ip):
    monkeypatch.setattr("app.services.source_resolver.socket.getaddrinfo",
                        lambda *a, **k: [(0, 0, 0, "", (ip, 80))])
    with pytest.raises(SourceError, match="rede"):
        target("http://origin.test/a", {"origin.test"})


def test_blocks_unknown_host_before_dns(monkeypatch):
    dns = Mock()
    monkeypatch.setattr("app.services.source_resolver.socket.getaddrinfo", dns)
    with pytest.raises(SourceError):
        target("https://other.test/a", {"origin.test"})
    dns.assert_not_called()


def test_scoped_cdn_subdomains_keep_dns_and_suffix_checks(monkeypatch):
    monkeypatch.setattr('app.services.source_resolver.socket.getaddrinfo',
                        lambda *a, **k: [(0, 0, 0, '', ('93.184.216.34', 443))])
    assert target('https://node.account.workers.dev/file', {'.account.workers.dev'})[1] == 'node.account.workers.dev'
    for host in ('node.other.workers.dev', 'node.account.workers.dev.evil.test', '127.0.0.1'):
        with pytest.raises(SourceError):
            target('https://' + host + '/file', {'.account.workers.dev'})


def mock_transport(monkeypatch, responses):
    monkeypatch.setattr("app.services.source_resolver.socket.getaddrinfo",
                        lambda *a, **k: [(0, 0, 0, "", ("93.184.216.34", 443))])
    pool = Mock()
    pool.urlopen.side_effect = responses
    factory = Mock(return_value=pool)
    monkeypatch.setattr("app.services.source_resolver.urllib3.HTTPConnectionPool", factory)
    monkeypatch.setattr("app.services.source_resolver.urllib3.HTTPSConnectionPool", factory)
    return pool, factory


def response(status=206, headers=None, body=b"\x00\x00\x00\x18ftypisom"):
    r = Mock(status=status, headers=headers or {})
    r.read.return_value = body
    return r


def test_resolves_http_redirect_to_https_without_leaking_headers(monkeypatch):
    first = response(302, {"Location": "https://cdn.test/final.mp4"})
    last = response()
    pool, factory = mock_transport(monkeypatch, [first, last])
    result = probe("http://origin.test/private/path", {"origin.test", "cdn.test"})
    assert result["url"] == "https://cdn.test/final.mp4"
    assert result["type"] == "mp4" and result["redirects"] == 1
    last.read.assert_called_once_with(1024, decode_content=False)
    assert factory.call_args.kwargs["assert_hostname"] == "cdn.test"
    assert factory.call_args.args[0] == "93.184.216.34"
    assert "Cookie" not in pool.urlopen.call_args.kwargs["headers"]
    first.close.assert_called()
    last.close.assert_called()


@pytest.mark.parametrize("r,code", [
    (response(403), "access_denied"),
    (response(429), "rate_limited"),
    (response(200, {"Content-Type": "text/html"}, b"<html>login</html>"), "html_response"),
    (response(200, {"Content-Type": "video/mp4"}, b"not really a video"), "unsupported_media"),
    (response(302, {"Location": "http://169.254.169.254/latest/meta-data"}), "host_not_allowed"),
])
def test_failures_are_specific_and_bounded(monkeypatch, r, code):
    mock_transport(monkeypatch, [r])
    with pytest.raises(SourceError) as error:
        probe("https://origin.test/private", {"origin.test"})
    assert error.value.code == code
    r.close.assert_called()


def test_hls_is_detected_by_content_not_extension(monkeypatch):
    mock_transport(monkeypatch, [response(body=b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1")])
    assert probe("https://origin.test/master.txt", {"origin.test"})["type"] == "hls"


def test_http_media_is_only_returned_after_successful_https_probe(monkeypatch):
    pool, factory = mock_transport(monkeypatch, [response(), response()])
    result = probe("http://origin.test:80/movie.mp4", {"origin.test"})
    assert result["url"] == "https://origin.test/movie.mp4"
    assert pool.urlopen.call_count == 2
    assert factory.call_args.kwargs["port"] == 443


def test_http_media_does_not_hide_tls_failure(monkeypatch):
    import urllib3
    mock_transport(monkeypatch, [response(), urllib3.exceptions.SSLError("invalid certificate")])
    with pytest.raises(SourceError) as error:
        probe("http://origin.test/a.mp4", {"origin.test"})
    assert error.value.code == "network_error"


def test_playback_requires_login_and_hides_original(sources_config, client, logged_in, db, catalog, monkeypatch):
    import_m3u(playlist())
    source = db.session.get(MediaSource, 1)
    source.movie_id = catalog["movie"].id
    db.session.commit()
    html = client.get(f"/watch/movie/{source.movie_id}").get_data(as_text=True)
    assert "private/password" not in html and "data-resolve-url" in html
    monkeypatch.setattr("app.source_routes.probe", lambda *a, **k: {"url": "https://cdn.test/final", "type": "mp4"})
    result = logged_in.post(f"/api/v1/playback/movie/{source.movie_id}")
    assert result.json["url"] == "https://cdn.test/final"
    assert "no-store" in result.headers["Cache-Control"]
    assert "password" not in json.dumps(result.json)
    client.post("/auth/logout")
    anonymous = sources_config.test_client()
    assert anonymous.post(f"/api/v1/playback/movie/{source.movie_id}").status_code == 401
    assert anonymous.get("/admin/sources").status_code == 302


def test_admin_can_review_without_credentials_in_html(sources_config, admin_client):
    import_m3u(playlist())
    result = admin_client.get("/admin/sources")
    assert result.status_code == 200
    assert "Filme (2024)" in result.get_data(as_text=True)
    assert "private/password" not in result.get_data(as_text=True)


def test_source_selection_cannot_access_another_title(sources_config, logged_in, db, catalog, monkeypatch):
    import_m3u(playlist())
    source = db.session.get(MediaSource, 1)
    source.movie_id = catalog['movie'].id
    db.session.commit()
    probe_mock = Mock(return_value={'url': 'https://cdn.test/file', 'type': 'mp4'})
    monkeypatch.setattr('app.source_routes.probe', probe_mock)
    endpoint = f'/api/v1/playback/movie/{source.movie_id}'
    assert logged_in.post(endpoint, data={'source_id': '2'}).status_code == 404
    probe_mock.assert_not_called()
    assert logged_in.post(endpoint, data={'source_id': '1'}).status_code == 200
