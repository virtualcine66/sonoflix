"""Monta o catálogo inteiro a partir da lista, sem depender de consultas TMDB."""
import hashlib
import json

from sqlalchemy import bindparam, insert, update

from app.extensions import db
from app.models import Episode, Movie, Season, Series
from app.source_models import MediaSource


def source_key(kind, title, year):
    # Preserva pontuação/acentos para não fundir obras diferentes por aproximação.
    value = json.dumps([kind, ' '.join(title.casefold().split()), year], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def build_catalog(progress=None, batch_size=1000):
    from app.utils import slugify

    items = {}
    for model in (Movie, Series):
        for item_id, key in db.session.execute(db.select(model.id, model.catalog_key)):
            if key:
                items[key] = item_id
    # Reaproveita os títulos já identificados antes de criar registros da lista.
    stmt = db.select(MediaSource.kind, MediaSource.search_title, MediaSource.year,
                     MediaSource.movie_id, Season.series_id).outerjoin(
        Episode, Episode.id == MediaSource.episode_id).outerjoin(Season, Season.id == Episode.season_id)
    for kind, title, year, movie_id, series_id in db.session.execute(stmt.where(
            (MediaSource.movie_id.is_not(None)) | (MediaSource.episode_id.is_not(None)))):
        items[source_key(kind, title, year)] = movie_id if kind == 'movie' else series_id
    seasons = {(series_id, number): ident for ident, series_id, number in
               db.session.execute(db.select(Season.id, Season.series_id, Season.season_number))}
    episodes = {(season_id, number): ident for ident, season_id, number in
                db.session.execute(db.select(Episode.id, Episode.season_id, Episode.episode_number))}
    cursor, linked, invalid = 0, 0, 0
    columns = (MediaSource.id, MediaSource.kind, MediaSource.search_title, MediaSource.year,
               MediaSource.season_number, MediaSource.episode_number,
               MediaSource.movie_id, MediaSource.episode_id)
    while True:
        rows = db.session.execute(db.select(*columns).where(MediaSource.id > cursor)
                                  .order_by(MediaSource.id).limit(batch_size)).all()
        if not rows:
            break
        prepared = []
        new = {'movie': {}, 'series': {}}
        for row in rows:
            sid, kind, title, year, sn, en, mid, eid = row
            if kind == 'series' and (sn is None or en is None):
                invalid += 1
                continue
            key = source_key(kind, title, year)
            prepared.append((row, key))
            if key not in items:
                new[kind][key] = {'catalog_key': key, 'title': title[:255], 'slug': slugify(title)[:255]}
        for kind, model in (('movie', Movie), ('series', Series)):
            if new[kind]:
                for ident, key in db.session.execute(insert(model.__table__).returning(
                        model.id, model.catalog_key), list(new[kind].values())):
                    items[key] = ident
        new_seasons = {(items[key], row.season_number) for row, key in prepared if row.kind == 'series'}
        missing = [{'series_id': ident, 'season_number': number, 'title': f'Temporada {number}'}
                   for ident, number in new_seasons if (ident, number) not in seasons]
        if missing:
            for ident, parent, number in db.session.execute(insert(Season.__table__).returning(
                    Season.id, Season.series_id, Season.season_number), missing):
                seasons[(parent, number)] = ident
        new_episodes = {(seasons[(items[key], row.season_number)], row.episode_number)
                        for row, key in prepared if row.kind == 'series'}
        missing = [{'season_id': ident, 'episode_number': number, 'title': f'Episódio {number}'}
                   for ident, number in new_episodes if (ident, number) not in episodes]
        if missing:
            for ident, parent, number in db.session.execute(insert(Episode.__table__).returning(
                    Episode.id, Episode.season_id, Episode.episode_number), missing):
                episodes[(parent, number)] = ident
        bindings = []
        for row, key in prepared:
            mid = row.movie_id
            eid = row.episode_id
            if mid is None and eid is None:
                if row.kind == 'movie':
                    mid = items[key]
                else:
                    eid = episodes[(seasons[(items[key], row.season_number)], row.episode_number)]
                bindings.append({'source_pk': row.id, 'movie_target': mid, 'episode_target': eid})
            linked += 1
        if bindings:
            db.session.execute(update(MediaSource.__table__).where(MediaSource.id == bindparam('source_pk'))
                               .values(movie_id=bindparam('movie_target'), episode_id=bindparam('episode_target')),
                               bindings)
        db.session.commit()
        cursor = rows[-1].id
        if progress and (cursor % 10000 == 0 or len(rows) < batch_size):
            progress({'linked': linked, 'unclassified': invalid})
    return {'linked': linked, 'unclassified': invalid}
