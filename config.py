"""Configurações por ambiente, lidas de variáveis de ambiente (.env)."""
import os

from dotenv import load_dotenv

load_dotenv()

# Valor só para desenvolvimento: o create_app recusa subir em produção com ele.
DEV_SECRET_KEY = "dev-only-troque-esta-chave"  # noqa: S105


def _database_url() -> str | None:
    url = os.environ.get("DATABASE_URL")
    # Render/Heroku entregam "postgres://", que o SQLAlchemy 2 não aceita.
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET_KEY)
    # Quando vazio, o create_app usa SQLite em instance/telao.db.
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    TMDB_API_TOKEN = os.environ.get("TMDB_API_TOKEN", "")
    TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
    TMDB_LANGUAGE = os.environ.get("TMDB_LANGUAGE", "pt-BR")
    TMDB_REGION = os.environ.get("TMDB_REGION", "BR")
    TMDB_TIMEOUT = float(os.environ.get("TMDB_TIMEOUT", "8"))
    TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

    ITEMS_PER_PAGE = 24

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    # Liga o Strict-Transport-Security; só faz sentido servido via HTTPS.
    ENABLE_HSTS = False


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing"  # noqa: S105
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    TMDB_API_TOKEN = ""
    TMDB_API_KEY = ""


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    ENABLE_HSTS = os.environ.get("ENABLE_HSTS", "1") == "1"


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
