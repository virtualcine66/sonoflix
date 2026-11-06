"""Consultas do catálogo compartilhadas pelas páginas HTML e pela API."""
from collections import namedtuple

from sqlalchemy import func, or_

from app.extensions import db
from app.models import Genre, Movie, Series, movie_genre_association, series_genre_association
from app.utils import like_pattern

SORT_OPTIONS = {
    "popular": "Mais populares",
    "rating": "Mais bem avaliados",
    "recent": "Lançamentos",
    "title": "Ordem alfabética",
}

Rail = namedtuple("Rail", "title link items")


def _premiere_column(model):
    return model.release_date if model is Movie else model.start_date


def catalog_query(model, genre=None, sort="popular"):
    stmt = db.select(model)
    if genre is not None:
        stmt = stmt.where(model.genres.any(Genre.id == genre.id))
    order = {
        "popular": model.popularity.desc(),
        "rating": model.rating.desc(),
        "recent": _premiere_column(model).desc().nulls_last(),
        "title": model.title.asc(),
    }[sort]
    return stmt.order_by(order, model.id.desc())


def genres_in_use(model):
    """Gêneros que têm pelo menos um título do tipo informado."""
    return db.session.scalars(
        db.select(Genre).where(Genre.movies.any() if model is Movie else Genre.series.any()).order_by(Genre.name)
    ).all()


def search_items(query, limit=None):
    """Busca por título, título original, elenco e direção/criação, misturando filmes e séries."""
    pattern = like_pattern(query)
    results = []
    for model, people in ((Movie, Movie.director), (Series, Series.creator)):
        stmt = db.select(model).where(or_(
            model.title.ilike(pattern, escape="\\"),
            model.original_title.ilike(pattern, escape="\\"),
            model.cast.ilike(pattern, escape="\\"),
            people.ilike(pattern, escape="\\"),
        )).order_by(model.popularity.desc())
        if limit:
            stmt = stmt.limit(limit)
        results.extend(db.session.scalars(stmt))
    # Títulos que começam com o termo vêm primeiro; depois, os mais populares.
    term = query.lower()
    results.sort(key=lambda item: (not item.title.lower().startswith(term), -(item.popularity or 0)))
    return results[:limit] if limit else results


def featured_item():
    """Destaque da home: um título marcado como destaque, senão o mais popular com imagem de fundo."""
    for model in (Movie, Series):
        item = db.session.scalar(
            db.select(model).where(model.featured, model.backdrop_url.is_not(None))
            .order_by(model.updated_at.desc()).limit(1))
        if item:
            return item
    for with_backdrop in (True, False):
        candidates = []
        for model in (Movie, Series):
            stmt = db.select(model).order_by(model.popularity.desc())
            if with_backdrop:
                stmt = stmt.where(model.backdrop_url.is_not(None))
            candidates.append(db.session.scalar(stmt.limit(1)))
        candidates = [c for c in candidates if c]
        if candidates:
            return max(candidates, key=lambda c: c.popularity or 0)
    return None


def home_rails(url_for, limit=18):
    """Fileiras da página inicial; fileiras vazias são descartadas."""
    rails = [
        Rail("Filmes em alta", url_for("main.movies", sort="popular"),
             db.session.scalars(catalog_query(Movie).limit(limit)).all()),
        Rail("Séries em alta", url_for("main.series", sort="popular"),
             db.session.scalars(catalog_query(Series).limit(limit)).all()),
        Rail("Filmes mais bem avaliados", url_for("main.movies", sort="rating"),
             db.session.scalars(catalog_query(Movie, sort="rating").limit(limit)).all()),
    ]
    for genre in top_genres(3):
        items = (
            db.session.scalars(catalog_query(Movie, genre).limit(limit)).all()
            + db.session.scalars(catalog_query(Series, genre).limit(limit)).all()
        )
        items.sort(key=lambda item: -(item.popularity or 0))
        rails.append(Rail(genre.name, url_for("main.movies", genre=genre.slug), items[:limit]))
    return [rail for rail in rails if rail.items]


def top_genres(limit):
    """Gêneros com mais títulos (filmes + séries)."""
    movie_counts = (db.select(movie_genre_association.c.genre_id.label("genre_id"))
                    .union_all(db.select(series_genre_association.c.genre_id))).subquery()
    stmt = (db.select(Genre)
            .join(movie_counts, movie_counts.c.genre_id == Genre.id)
            .group_by(Genre.id)
            .order_by(func.count().desc(), Genre.name)
            .limit(limit))
    return db.session.scalars(stmt).all()


def related_items(item, limit=12):
    """Títulos que compartilham gêneros com o item (filmes e séries)."""
    genre_ids = [g.id for g in item.genres]
    if not genre_ids:
        return []
    related = []
    for model in (Movie, Series):
        stmt = db.select(model).where(model.genres.any(Genre.id.in_(genre_ids)))
        if isinstance(item, model):
            stmt = stmt.where(model.id != item.id)
        related.extend(db.session.scalars(stmt.order_by(model.popularity.desc()).limit(limit)))
    related.sort(key=lambda other: -(other.popularity or 0))
    return related[:limit]
