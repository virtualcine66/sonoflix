"""
Dados iniciais do catálogo.

- Com TMDb configurado: importa uma lista curada de títulos reais (pôsteres, elenco, temporadas...).
- Sem TMDb: cria um catálogo de demonstração com dados fixos (as imagens vêm do CDN do TMDb).
"""
from datetime import date

from app.extensions import db
from app.models import MOVIE, SERIES, Genre, Movie, Season, Series
from app.services.importer import import_title
from app.services.tmdb import TMDbError
from app.utils import slugify

# IDs do TMDb importados pelo `flask seed`
CURATED = {
    MOVIE: [693134, 872585, 157336, 598, 40096, 496243, 569094, 545611, 438631, 27205],
    SERIES: [106379, 94997, 1396, 70523, 100088, 94605, 66732, 1399],
}

DEMO_MOVIES = [
    dict(title="Duna: Parte Dois", tmdb_id=693134,
         poster_url="/VMy4UGsI2u3f4fALGeCqCdsQBb.jpg", backdrop_url="/eZ239CUp1d6OryZEBPnO2n87gMG.jpg",
         release_date=date(2024, 2, 29), director="Denis Villeneuve", runtime=166,
         rating=8.1, popularity=90, genres=["Ficção científica", "Aventura"],
         cast="Timothée Chalamet, Zendaya, Rebecca Ferguson, Javier Bardem",
         trailer_url="https://www.youtube.com/watch?v=Way9Dexny3w",
         description="Paul Atreides se une aos Fremen e precisa escolher entre o amor e o destino "
                     "de todo um planeta enquanto busca vingança."),
    dict(title="Oppenheimer", tmdb_id=872585,
         poster_url="/dUPQszWoRSE9FucJTbVp2bwEi9G.jpg", backdrop_url="/neeNHeXjMF5fXoCJRsOmkNGC7q.jpg",
         release_date=date(2023, 7, 20), director="Christopher Nolan", runtime=180,
         rating=8.1, popularity=70, genres=["Drama", "História"],
         cast="Cillian Murphy, Emily Blunt, Matt Damon, Robert Downey Jr.",
         trailer_url="https://www.youtube.com/watch?v=uYPbbksJxIg",
         description="A trajetória do físico que liderou o Projeto Manhattan e o peso de criar "
                     "a arma mais destrutiva da história."),
    dict(title="Interestelar", tmdb_id=157336,
         poster_url="/tR1XVa5bxgdh2bRw2u0DzrgkO2l.jpg", backdrop_url="/8sNiAPPYU14PUepFNeSNGUTiHW.jpg",
         release_date=date(2014, 11, 6), director="Christopher Nolan", runtime=169,
         rating=8.4, popularity=80, genres=["Ficção científica", "Drama", "Aventura"],
         cast="Matthew McConaughey, Anne Hathaway, Jessica Chastain",
         trailer_url="https://www.youtube.com/watch?v=zSWdZVtXT7E",
         description="Com a Terra à beira do colapso, um grupo de exploradores atravessa um buraco "
                     "de minhoca em busca de um novo lar para a humanidade."),
    dict(title="Cidade de Deus", tmdb_id=598,
         poster_url="/gfnXixcGC060QcG6JPxN6AMdVsq.jpg", backdrop_url="/uvitbjFU4JqvMwIkMWHp69bmUzG.jpg",
         release_date=date(2002, 8, 30), director="Fernando Meirelles, Kátia Lund",
         runtime=130, rating=8.4, popularity=40, genres=["Crime", "Drama"],
         cast="Alexandre Rodrigues, Leandro Firmino, Phellipe Haagensen",
         description="Buscapé cresce em uma comunidade do Rio de Janeiro e registra com sua câmera "
                     "décadas de violência e disputa pelo tráfico."),
    dict(title="O Auto da Compadecida", tmdb_id=40096,
         poster_url="/y3IhuITELtprMhUd7bccu629rba.jpg", backdrop_url="/alQqTpmEkxSLgajfEYTsTH6nAKB.jpg",
         release_date=date(2000, 9, 15), director="Guel Arraes", runtime=104,
         rating=8.3, popularity=35, genres=["Comédia"],
         cast="Matheus Nachtergaele, Selton Mello, Fernanda Montenegro",
         description="João Grilo e Chicó aplicam golpes no sertão nordestino até que precisam "
                     "enfrentar um julgamento nada comum."),
    dict(title="Parasita", tmdb_id=496243,
         poster_url="/bNGW8zYA91VqTZfV3jnKHPEKKvB.jpg", backdrop_url="/TU9NIjwzjoKPwQHoHshkFcQUCG.jpg",
         release_date=date(2019, 11, 7), director="Bong Joon-ho", runtime=133,
         rating=8.5, popularity=45, genres=["Thriller", "Drama", "Comédia"],
         cast="Song Kang-ho, Lee Sun-kyun, Cho Yeo-jeong, Choi Woo-shik",
         description="Uma família pobre se infiltra, um a um, na rotina de uma família rica, "
                     "até que um segredo muda tudo."),
]

DEMO_SERIES = [
    dict(title="Breaking Bad", tmdb_id=1396,
         poster_url="/hGwm9Cj3CdbJIqQWNExQqiYmCd4.jpg", backdrop_url="/tsRy63Mu5cu8etL1X7ZLyf7UP1M.jpg",
         start_date=date(2008, 1, 20), end_date=date(2013, 9, 29), status="Ended",
         creator="Vince Gilligan", rating=8.9, popularity=95, seasons=5, genres=["Drama", "Crime"],
         cast="Bryan Cranston, Aaron Paul, Anna Gunn",
         description="Um professor de química com um diagnóstico terminal entra no mundo do crime "
                     "para garantir o futuro da família."),
    dict(title="Dark", tmdb_id=70523,
         poster_url="/wiiyc3m6HKaQhFBYeuM7ySCNQsG.jpg", backdrop_url="/3jDXL4Xvj3AzDOF6UH1xeyHW8MH.jpg",
         start_date=date(2017, 12, 1), end_date=date(2020, 6, 27), status="Ended",
         creator="Baran bo Odar, Jantje Friese", rating=8.4, popularity=60, seasons=3,
         genres=["Ficção científica", "Mistério", "Drama"], cast="Louis Hofmann, Lisa Vicari, Oliver Masucci",
         description="O desaparecimento de duas crianças expõe os segredos de quatro famílias "
                     "de uma pequena cidade alemã ao longo de várias gerações."),
    dict(title="Arcane", tmdb_id=94605,
         poster_url="/m3Tzf6k537PnhOEwaSRNCSxedLS.jpg", backdrop_url="/5cvnxEHT3e39DvT6ARw4GNCFrB0.jpg",
         start_date=date(2021, 11, 6), end_date=date(2024, 11, 23), status="Ended",
         creator="Christian Linke, Alex Yee", rating=8.7, popularity=75, seasons=2,
         genres=["Animação", "Ficção científica", "Aventura"], cast="Hailee Steinfeld, Ella Purnell, Kevin Alejandro",
         description="Duas irmãs ficam em lados opostos do conflito entre a cidade rica de Piltover "
                     "e o submundo de Zaun."),
    dict(title="The Last of Us", tmdb_id=100088,
         poster_url="/qWo5TP7mBijoZrfxBJkUMctkBt0.jpg", backdrop_url="/lY2DhbA7Hy44fAKddr06UrXWWaQ.jpg",
         start_date=date(2023, 1, 15), status="Returning Series",
         creator="Craig Mazin, Neil Druckmann", rating=8.6, popularity=85, seasons=2,
         genres=["Drama", "Aventura"], cast="Pedro Pascal, Bella Ramsey",
         description="Vinte anos após uma pandemia devastadora, um sobrevivente precisa atravessar "
                     "os Estados Unidos escoltando uma adolescente."),
]


def _genres(names):
    genres = []
    for name in names:
        genre = db.session.scalar(db.select(Genre).filter_by(slug=slugify(name)))
        if genre is None:
            genre = Genre(name=name)
            db.session.add(genre)
            db.session.flush()
        genres.append(genre)
    return genres


def seed_demo():
    """Cria o catálogo de demonstração (sem precisar de chave do TMDb). Retorna quantos títulos foram criados."""
    created = 0
    for data in DEMO_MOVIES:
        data = dict(data)
        if db.session.scalar(db.select(Movie).filter_by(title=data["title"])):
            continue
        genres = _genres(data.pop("genres"))
        db.session.add(Movie(**data, genres=genres))
        created += 1
    for data in DEMO_SERIES:
        data = dict(data)
        if db.session.scalar(db.select(Series).filter_by(title=data["title"])):
            continue
        genres = _genres(data.pop("genres"))
        season_count = data.pop("seasons")
        series = Series(**data, genres=genres)
        db.session.add(series)
        for number in range(1, season_count + 1):
            series.seasons.append(Season(season_number=number))
        created += 1
    db.session.commit()
    return created


def seed_from_tmdb(client, echo=print):
    """Importa a lista curada do TMDb. Retorna quantos títulos foram importados."""
    imported = 0
    for kind, ids in CURATED.items():
        for tmdb_id in ids:
            try:
                item = import_title(client, kind, tmdb_id)
                echo(f"  ✓ {item.title}")
                imported += 1
            except TMDbError as exc:
                db.session.rollback()
                echo(f"  ✗ {kind} {tmdb_id}: {exc}")
    return imported
