from app.models import User
from tests.conftest import login


def test_register_creates_user_and_logs_in(client, db):
    response = client.post("/auth/register", data={
        "username": "joao", "email": "JOAO@Example.com",
        "password": "senha-segura-123", "password2": "senha-segura-123",
    })
    assert response.status_code == 302
    user = db.session.scalar(db.select(User).filter_by(username="joao"))
    assert user.email == "joao@example.com"
    assert user.password_hash != "senha-segura-123"
    assert client.get("/profile").status_code == 200


def test_register_rejects_duplicate_username_ignoring_case(client, user):
    response = client.post("/auth/register", data={
        "username": "MARIA", "email": "outra@example.com",
        "password": "senha-segura-123", "password2": "senha-segura-123",
    })
    assert response.status_code == 200
    assert "já está em uso" in response.get_data(as_text=True)


def test_register_requires_minimum_password_length(client):
    response = client.post("/auth/register", data={
        "username": "ana", "email": "ana@example.com", "password": "curta", "password2": "curta",
    })
    assert "pelo menos 8 caracteres" in response.get_data(as_text=True)


def test_login_with_username_or_email(client, user):
    assert login(client, "maria").status_code == 302
    client.post("/auth/logout")
    assert login(client, "maria@example.com").status_code == 302


def test_login_with_wrong_password_fails(client, user):
    response = login(client, password="errada")
    assert response.status_code == 200
    assert "inválidos" in response.get_data(as_text=True)


def test_login_follows_safe_next(client, user):
    response = login(client, next_url="/profile")
    assert response.headers["Location"] == "/profile"


def test_login_blocks_open_redirect(client, user):
    for target in ("https://evil.example.com/", "//evil.example.com", "/\\evil.example.com"):
        response = login(client, next_url=target)
        assert response.headers["Location"] == "/", target
        client.post("/auth/logout")


def test_logout_only_accepts_post(logged_in):
    assert logged_in.get("/auth/logout").status_code == 405
    assert logged_in.post("/auth/logout").status_code == 302
    assert logged_in.get("/profile").status_code == 302
