"""
Importa filmes e séries do TMDb para o banco local.

Reimportar o mesmo título atualiza o registro existente em vez de duplicar.
"""
import logging

from app.extensions import db
from app.models import MOVIE, SERIES, Episode, Genre, Movie, Season, Series
from app.services.tmdb import TMDbError, pick_trailer
from app.utils import parse_date, slugify

log = logging.getLogger(__name__)

MAX_CAST = 10
ENDED_STATUSES = {"Ended", "Canceled"}


def import_title(client, kind, tmdb_id, with_episodes=True, target=None):
    """Busca o título no TMDb e cria/atualiza o Movie ou Series correspondente."""
    if kind == MOVIE:
        data = client.movie(tmdb_id)
        item = db.session.scalar(db.select(Movie).filter_by(tmdb_id=tmdb_id)) or target or Movie()
        item.tmdb_id = tmdb_id
        _fill_movie(item, data)
    elif kind == SERIES:
        data = client.tv(tmdb_id)
        item = db.session.scalar(db.select(Series).filter_by(tmdb_id=tmdb_id)) or target or Series()
        item.tmdb_id = tmdb_id
        _fill_series(item, data)
    else:
        raise ValueError(f"Tipo inválido: {kind}")

    language = client.language.split("-")[0]
    item.tagline = data.get("tagline") or None
    item.description = data.get("overview") or item.description
    item.rating = round(data.get("vote_average") or 0, 1)
    item.vote_count = data.get("vote_count") or 0
    item.popularity = data.get("popularity") or 0
    item.poster_url = data.get("poster_path") or item.poster_url
    item.backdrop_url = data.get("backdrop_path") or item.backdrop_url
    trailer = pick_trailer(data.get("videos"), language)
    if trailer:
        item.trailer_url = f"https://www.youtube.com/watch?v={trailer}"
    cast = (data.get("credits") or {}).get("cast", [])[:MAX_CAST]
    item.cast = ", ".join(person["name"] for person in cast) or item.cast
    item.genres = [_genre(g["name"]) for g in data.get("genres", [])]

    db.session.add(item)
    if kind == SERIES:
        _sync_seasons(client, item, data, with_episodes)
    db.session.commit()
    return item


def _fill_movie(movie, data):
    movie.title = data.get("title") or data.get("original_title") or "Sem título"
    movie.original_title = data.get("original_title")
    movie.release_date = parse_date(data.get("release_date"))
    movie.runtime = data.get("runtime") or None
    crew = (data.get("credits") or {}).get("crew", [])
    directors = [person["name"] for person in crew if person.get("job") == "Director"]
    movie.director = ", ".join(directors) or movie.director


def _fill_series(series, data):
    series.title = data.get("name") or data.get("original_name") or "Sem título"
    series.original_title = data.get("original_name")
    series.start_date = parse_date(data.get("first_air_date"))
    series.status = data.get("status")
    series.end_date = parse_date(data.get("last_air_date")) if data.get("status") in ENDED_STATUSES else None
    runtimes = data.get("episode_run_time") or []
    series.episode_runtime = runtimes[0] if runtimes else None
    creators = [person["name"] for person in data.get("created_by", [])]
    series.creator = ", ".join(creators) or series.creator


def _genre(name):
    genre = db.session.scalar(db.select(Genre).filter_by(slug=slugify(name)))
    if genre is None:
        genre = Genre(name=name)
        db.session.add(genre)
        db.session.flush()
    return genre


def _sync_seasons(client, series, data, with_episodes):
    """Atualiza metadados sem apagar episódios, fontes ou IDs existentes."""
    existing = {season.season_number: season for season in series.seasons}
    for info in data.get("seasons", []):
        number = info.get("season_number")
        if not number:
            continue
        season = existing.get(number)
        if season is None:
            season = Season(season_number=number)
            series.seasons.append(season)
        season.title = info.get("name")
        season.description = info.get("overview") or season.description
        season.release_date = parse_date(info.get("air_date"))
        season.poster_url = info.get("poster_path") or season.poster_url
        if not with_episodes:
            continue
        try:
            detail = client.season(series.tmdb_id, number)
        except TMDbError as exc:
            log.warning("Episódios da temporada %s de %s não importados: %s", number, series.title, exc)
            continue
        episodes = {ep.episode_number: ep for ep in season.episodes}
        for info_ep in detail.get("episodes", []):
            ep_number = info_ep.get("episode_number")
            if not ep_number:
                continue
            episode = episodes.get(ep_number)
            if episode is None:
                episode = Episode(episode_number=ep_number)
                season.episodes.append(episode)
            episode.title = info_ep.get("name") or f"Episódio {ep_number}"
            episode.description = info_ep.get("overview") or episode.description
            episode.release_date = parse_date(info_ep.get("air_date"))
            episode.duration_minutes = info_ep.get("runtime")
            episode.still_url = info_ep.get("still_path") or episode.still_url
