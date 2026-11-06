import pytest

from app import create_app
from app.extensions import db as _db
from app.models import Genre, Movie, Season, Series, User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


def make_user(username="maria", password="senha-segura-123", is_admin=False):
    user = User(username=username, email=f"{username}@example.com", is_admin=is_admin)
    user.set_password(password)
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def user(app):
    return make_user()


@pytest.fixture
def admin(app):
    return make_user("admin", is_admin=True)


def login(client, username="maria", password="senha-segura-123", next_url=None):
    url = "/auth/login" + (f"?next={next_url}" if next_url else "")
    return client.post(url, data={"identifier": username, "password": password})


@pytest.fixture
def logged_in(client, user):
    login(client)
    return client


@pytest.fixture
def admin_client(client, admin):
    login(client, "admin")
    return client


@pytest.fixture
def catalog(app):
    drama = Genre(name="Drama")
    scifi = Genre(name="Ficção científica")
    movie = Movie(title="Interestelar", director="Christopher Nolan", rating=8.4, popularity=80,
                  cast="Matthew McConaughey, Anne Hathaway", genres=[scifi, drama],
                  trailer_url="https://www.youtube.com/watch?v=zSWdZVtXT7E")
    other = Movie(title="Oppenheimer", director="Christopher Nolan", rating=8.1, popularity=70, genres=[drama])
    series = Series(title="Dark", creator="Baran bo Odar", rating=8.4, popularity=60, genres=[scifi])
    _db.session.add_all([movie, other, series])
    series.seasons.append(Season(season_number=1))
    _db.session.commit()
    return {"movie": movie, "other": other, "series": series, "drama": drama, "scifi": scifi}
