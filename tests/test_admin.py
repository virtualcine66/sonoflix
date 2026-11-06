import pytest

from app.models import Genre, Movie, User
from tests.conftest import make_user

ADMIN_PAGES = [
    "/admin/", "/admin/movies", "/admin/series", "/admin/import", "/admin/genres", "/admin/users",
    "/admin/movie/add", "/admin/series/add",
]


@pytest.mark.parametrize("url", ADMIN_PAGES)
def test_admin_pages_require_admin(client, logged_in, url):
    assert logged_in.get(url).status_code == 403


def test_admin_redirects_anonymous_to_login(client):
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


@pytest.mark.parametrize("url", ADMIN_PAGES)
def test_admin_pages_render(admin_client, catalog, url):
    assert admin_client.get(url).status_code == 200


def test_season_and_episode_pages_render(admin_client, catalog):
    series = catalog["series"]
    season = series.seasons.first()
    for url in (f"/admin/series/{series.id}/seasons", f"/admin/series/{series.id}/seasons/add",
                f"/admin/season/{season.id}/edit", f"/admin/season/{season.id}/episodes",
                f"/admin/season/{season.id}/episodes/add"):
        assert admin_client.get(url).status_code == 200, url


def test_create_movie_manually(admin_client, db, catalog):
    response = admin_client.post("/admin/movie/add", data={
        "title": "Ainda Estou Aqui", "director": "Walter Salles", "rating": "8.2",
        "release_date": "2024-11-07", "genres": [catalog["drama"].id],
        "trailer_url": "https://youtu.be/abcdefghijk",
    })
    assert response.status_code == 302
    movie = db.session.scalar(db.select(Movie).filter_by(title="Ainda Estou Aqui"))
    assert movie.slug == "ainda-estou-aqui"
    assert [g.name for g in movie.genres] == ["Drama"]
    assert movie.trailer_key == "abcdefghijk"


def test_rejects_invalid_trailer_and_image(admin_client):
    html = admin_client.post("/admin/movie/add", data={
        "title": "X", "trailer_url": "https://vimeo.com/123", "poster_url": "ftp://imagem.jpg",
    }).get_data(as_text=True)
    assert "link válido do YouTube" in html
    assert "caminho do TMDb" in html


def test_edit_and_delete_movie(admin_client, db, catalog):
    movie = catalog["movie"]
    admin_client.post(f"/admin/movie/{movie.id}/edit", data={"title": "Interstellar", "genres": []})
    assert db.session.get(Movie, movie.id).title == "Interstellar"
    admin_client.post(f"/admin/movie/{movie.id}/delete")
    assert db.session.get(Movie, movie.id) is None


def test_toggle_featured(admin_client, db, catalog):
    movie = catalog["movie"]
    admin_client.post(f"/admin/movie/{movie.id}/feature")
    assert db.session.get(Movie, movie.id).featured is True


def test_genre_names_must_be_unique(admin_client, db, catalog):
    html = admin_client.post("/admin/genres", data={"name": "drama"}).get_data(as_text=True)
    assert "Já existe um gênero" in html
    admin_client.post("/admin/genres", data={"name": "Comédia"})
    assert db.session.scalar(db.select(Genre).filter_by(slug="comedia")) is not None


def test_admin_cannot_delete_self(admin_client, db, admin):
    admin_client.post(f"/admin/users/{admin.id}/delete")
    assert db.session.get(User, admin.id) is not None


def test_admin_can_delete_other_user(admin_client, db):
    other = make_user("pedro")
    admin_client.post(f"/admin/users/{other.id}/delete")
    assert db.session.get(User, other.id) is None


def test_admin_cannot_remove_own_admin_role(admin_client, db, admin):
    admin_client.post(f"/admin/users/{admin.id}/edit", data={"username": "admin", "email": "admin@example.com"})
    assert db.session.get(User, admin.id).is_admin is True


def test_import_page_without_tmdb_shows_notice(admin_client):
    html = admin_client.get("/admin/import?q=duna").get_data(as_text=True)
    assert "TMDb não configurado" in html
