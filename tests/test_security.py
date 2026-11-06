import pytest

from app.utils import slugify, youtube_key


def test_security_headers(client):
    response = client.get("/")
    csp = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_html_is_escaped(client, db):
    from app.models import Movie
    db.session.add(Movie(title="<script>alert(1)</script>"))
    db.session.commit()
    html = client.get("/movies").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_production_requires_secret_key(monkeypatch):
    import config
    from app import create_app

    monkeypatch.setattr(config.ProductionConfig, "SECRET_KEY", config.DEV_SECRET_KEY)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production")


@pytest.mark.parametrize("value, expected", [
    ("https://www.youtube.com/watch?v=Way9Dexny3w", "Way9Dexny3w"),
    ("https://www.youtube.com/watch?feature=share&v=Way9Dexny3w", "Way9Dexny3w"),
    ("https://youtu.be/Way9Dexny3w?t=10", "Way9Dexny3w"),
    ("https://www.youtube-nocookie.com/embed/Way9Dexny3w", "Way9Dexny3w"),
    ("Way9Dexny3w", "Way9Dexny3w"),
    ("https://vimeo.com/12345", None),
    ("", None),
])
def test_youtube_key(value, expected):
    assert youtube_key(value) == expected


@pytest.mark.parametrize("value, expected", [
    ("Duna: Parte Dois", "duna-parte-dois"),
    ("Ação & Aventura", "acao-aventura"),
    ("???", "titulo"),
])
def test_slugify(value, expected):
    assert slugify(value) == expected
