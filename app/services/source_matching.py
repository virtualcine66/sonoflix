"""Correspondência conservadora e associação explícita de fontes."""
from app.extensions import db
from app.models import Episode, Movie, Season, Series
from app.services.importer import import_title
from app.services.tmdb import TMDbError
from app.utils import parse_date, slugify


def attach(source, tmdb_id, client):
    model = Movie if source.kind == "movie" else Series
    item = db.session.scalar(db.select(model).filter_by(tmdb_id=tmdb_id))
    if item is None:
        provisional = db.session.get(Movie, source.movie_id) if source.movie_id else None
        if source.episode_id:
            provisional = db.session.get(Episode, source.episode_id).season.series
        if provisional is not None and provisional.tmdb_id is not None:
            provisional = None
        item = import_title(client, source.kind, tmdb_id, with_episodes=False, target=provisional)
    if source.kind == "movie":
        source.movie_id, source.episode_id = item.id, None
    else:
        if source.season_number is None or source.episode_number is None:
            raise ValueError("Informe temporada e episódio antes de associar a série.")
        season = item.seasons.filter_by(season_number=source.season_number).first()
        episode = season.episodes.filter_by(episode_number=source.episode_number).first() if season else None
        if episode is None or not episode.description:
            try:
                detail = client.season(tmdb_id, source.season_number)
            except TMDbError as exc:
                if exc.status_code == 404:
                    raise ValueError('Temporada não encontrada no TMDB.') from exc
                raise
            info = next((e for e in detail.get("episodes", [])
                         if e.get("episode_number") == source.episode_number), None)
            if not info:
                raise ValueError("Episódio não encontrado nesta temporada no TMDB.")
            if season is None:
                season = Season(series=item, season_number=source.season_number, title=detail.get("name"))
                db.session.add(season)
            if episode is None:
                episode = Episode(season=season, episode_number=source.episode_number)
            episode.title = info.get("name") or f"Episódio {source.episode_number}"
            episode.description = info.get("overview")
            episode.release_date = parse_date(info.get("air_date"))
            episode.duration_minutes = info.get("runtime")
            episode.still_url = info.get("still_path")
            db.session.add(episode)
            db.session.flush()
        source.episode_id, source.movie_id = episode.id, None
    source.match_status = "matched"
    db.session.commit()


def match(source, client, allow_unique_title=False):
    from app.services.source_catalog import source_key

    known = None
    if source.movie_id:
        known = db.session.get(Movie, source.movie_id)
    elif source.episode_id:
        known = db.session.get(Episode, source.episode_id).season.series
    if (known is not None and known.tmdb_id and known.catalog_key
            == source_key(source.kind, source.search_title, source.year)):
        attach(source, known.tmdb_id, client)
        return
    if source.kind == "series" and source.episode_number is None:
        source.match_status = "review"
        source.candidates = []
        db.session.commit()
        return
    results = client.search(source.search_title, source.kind)
    source.candidates = results[:10]
    exact = [r for r in results if slugify(source.search_title) in
             (slugify(r["title"]), slugify(r.get("original_title") or ""))
             and (source.year is None or str(source.year) == str(r.get("year")))]
    # Sem ano, filmes homônimos não são associados automaticamente.
    if len(exact) == 1 and (source.kind == "series" or source.year is not None
                            or (allow_unique_title and len(results) == 1)):
        attach(source, exact[0]["tmdb_id"], client)
    else:
        source.match_status = "review"
        db.session.commit()
