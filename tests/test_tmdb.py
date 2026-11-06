from datetime import date

import pytest
import requests

from app.models import MOVIE, SERIES, Genre, Movie, Series
from app.services.importer import import_title
from app.services.tmdb import TMDbClient, TMDbError, TMDbNotConfigured, pick_trailer

MOVIE_PAYLOAD = {
    "id": 693134, "title": "Duna: Parte Dois", "original_title": "Dune: Part Two",
    "overview": "Paul Atreides se une a Chani.", "tagline": "O longo caminho.",
    "release_date": "2024-02-27", "runtime": 166, "vote_average": 8.13, "vote_count": 6000,
    "popularity": 300.5, "poster_path": "/poster.jpg", "backdrop_path": "/fundo.jpg",
    "genres": [{"id": 878, "name": "Ficção científica"}, {"id": 12, "name": "Aventura"}],
    "credits": {
        "cast": [{"name": "Timothée Chalamet"}, {"name": "Zendaya"}],
        "crew": [{"name": "Denis Villeneuve", "job": "Director"}, {"name": "Hans Zimmer", "job": "Original Music"}],
    },
    "videos": {"results": [
        {"site": "YouTube", "key": "teaser00000", "type": "Teaser", "iso_639_1": "pt", "official": True},
        {"site": "YouTube", "key": "trailerEN00", "type": "Trailer", "iso_639_1": "en", "official": True},
        {"site": "YouTube", "key": "trailerPT00", "type": "Trailer", "iso_639_1": "pt", "official": True},
        {"site": "Vimeo", "key": "ignorado", "type": "Trailer", "iso_639_1": "pt"},
    ]},
}

TV_PAYLOAD = {
    "id": 1396, "name": "Breaking Bad", "original_name": "Breaking Bad", "overview": "Walter White...",
    "first_air_date": "2008-01-20", "last_air_date": "2013-09-29", "status": "Ended",
    "vote_average": 8.9, "vote_count": 15000, "popularity": 400, "episode_run_time": [47],
    "poster_path": "/bb.jpg", "backdrop_path": "/bb-fundo.jpg",
    "created_by": [{"name": "Vince Gilligan"}],
    "genres": [{"id": 18, "name": "Drama"}],
    "credits": {"cast": [{"name": "Bryan Cranston"}]},
    "videos": {"results": []},
    "seasons": [
        {"season_number": 0, "name": "Especiais"},
        {"season_number": 1, "name": "Temporada 1", "air_date": "2008-01-20", "poster_path": "/t1.jpg"},
    ],
}

SEASON_PAYLOAD = {"episodes": [
    {"episode_number": 1, "name": "Piloto", "air_date": "2008-01-20", "runtime": 58, "still_path": "/e1.jpg"},
    {"episode_number": 2, "name": "O Gato Está no Saco...", "air_date": "2008-01-27", "runtime": 48},
]}


class FakeClient:
    """Substitui o TMDbClient nos testes: nada de rede."""
    language = "pt-BR"

    def __init__(self, movie=None, tv=None):
        self._movie = movie or MOVIE_PAYLOAD
        self._tv = tv or TV_PAYLOAD
        self.season_calls = []

    def movie(self, tmdb_id):
        return self._movie

    def tv(self, tmdb_id):
        return self._tv

    def season(self, tv_id, number):
        self.season_calls.append(number)
        return SEASON_PAYLOAD


def test_pick_trailer_prefers_trailer_in_portuguese():
    assert pick_trailer(MOVIE_PAYLOAD["videos"], "pt") == "trailerPT00"
    assert pick_trailer(MOVIE_PAYLOAD["videos"], "en") == "trailerEN00"
    assert pick_trailer({"results": []}) is None
    assert pick_trailer(None) is None


def test_import_movie(db):
    movie = import_title(FakeClient(), MOVIE, 693134)
    assert movie.title == "Duna: Parte Dois"
    assert movie.director == "Denis Villeneuve"
    assert movie.release_date == date(2024, 2, 27)
    assert movie.rating == 8.1
    assert movie.cast_list == ["Timothée Chalamet", "Zendaya"]
    assert movie.trailer_key == "trailerPT00"
    assert sorted(g.name for g in movie.genres) == ["Aventura", "Ficção científica"]


def test_reimport_updates_instead_of_duplicating(db):
    import_title(FakeClient(), MOVIE, 693134)
    changed = {**MOVIE_PAYLOAD, "vote_average": 9.0}
    import_title(FakeClient(movie=changed), MOVIE, 693134)
    assert db.session.scalar(db.select(db.func.count(Movie.id))) == 1
    assert db.session.scalar(db.select(Movie)).rating == 9.0
    assert db.session.scalar(db.select(db.func.count(Genre.id))) == 2


def test_import_series_with_seasons_and_episodes(db):
    client = FakeClient()
    series = import_title(client, SERIES, 1396)
    assert series.creator == "Vince Gilligan"
    assert series.end_date == date(2013, 9, 29)
    seasons = series.seasons.all()
    assert [s.season_number for s in seasons] == [1]  # temporada 0 (especiais) é ignorada
    assert client.season_calls == [1]
    episodes = seasons[0].episodes.all()
    assert [e.title for e in episodes] == ["Piloto", "O Gato Está no Saco..."]
    assert episodes[0].still() == "https://image.tmdb.org/t/p/w300/e1.jpg"


def test_reimport_series_replaces_seasons(db):
    import_title(FakeClient(), SERIES, 1396)
    import_title(FakeClient(), SERIES, 1396)
    series = db.session.scalar(db.select(Series))
    assert series.seasons.count() == 1
    assert series.seasons.first().episodes.count() == 2


def test_client_requires_credentials():
    with pytest.raises(TMDbNotConfigured):
        TMDbClient().search("duna")


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def test_client_uses_bearer_token_timeout_and_cache():
    session = FakeSession(FakeResponse(200, {"results": [
        {"id": 1, "title": "Duna", "release_date": "2021-09-15", "vote_average": 7.8}]}))
    client = TMDbClient(token="abc", session=session, timeout=5)
    results = client.search("duna")
    client.search("duna")
    assert results[0] == {"tmdb_id": 1, "kind": "movie", "title": "Duna", "original_title": None,
                          "year": "2021", "overview": "", "poster_path": None, "rating": 7.8}
    assert len(session.calls) == 1  # segunda chamada veio do cache
    call = session.calls[0]
    assert call["headers"]["Authorization"] == "Bearer abc"
    assert call["timeout"] == 5
    assert call["params"]["language"] == "pt-BR"
    assert "api_key" not in call["params"]


@pytest.mark.parametrize("status, message", [
    (401, "credencial"), (404, "não encontrado"), (429, "limitou"), (500, "erro 500"),
])
def test_client_translates_http_errors(status, message):
    client = TMDbClient(api_key="k", session=FakeSession(FakeResponse(status)))
    with pytest.raises(TMDbError, match=message):
        client.movie(1)


def test_client_handles_network_errors():
    client = TMDbClient(api_key="k", session=FakeSession(error=requests.ConnectionError("offline")))
    with pytest.raises(TMDbError, match="conectar"):
        client.tv(1)
