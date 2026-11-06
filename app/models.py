from datetime import UTC, datetime
from urllib.parse import urlsplit

from flask import current_app, url_for
from flask_login import UserMixin
from sqlalchemy.orm import declared_attr, validates
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.utils import slugify, youtube_key

MOVIE, SERIES = "movie", "series"
KIND_LABELS = {MOVIE: "Filme", SERIES: "Série"}


def utcnow():
    return datetime.now(UTC)


# Tabelas de associação (muitos para muitos)
movie_genre_association = db.Table(
    "movie_genre",
    db.Column("movie_id", db.Integer, db.ForeignKey("movie.id", ondelete="CASCADE"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genre.id", ondelete="CASCADE"), primary_key=True),
)

series_genre_association = db.Table(
    "series_genre",
    db.Column("series_id", db.Integer, db.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genre.id", ondelete="CASCADE"), primary_key=True),
)

# Favoritos ("Minha lista") de cada usuário
favorite_movies = db.Table(
    "favorite_movie",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.Column("movie_id", db.Integer, db.ForeignKey("movie.id", ondelete="CASCADE"), primary_key=True),
    db.Column("created_at", db.DateTime(timezone=True), default=utcnow, nullable=False),
)

favorite_series = db.Table(
    "favorite_series",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    db.Column("series_id", db.Integer, db.ForeignKey("series.id", ondelete="CASCADE"), primary_key=True),
    db.Column("created_at", db.DateTime(timezone=True), default=utcnow, nullable=False),
)


def image_url(path, size):
    """Resolve uma imagem: caminho do TMDb ('/abc.jpg') ou URL completa cadastrada à mão."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    return f"{current_app.config['TMDB_IMAGE_BASE']}/{size}{path}"


class User(UserMixin, db.Model):
    """
    Modelo de usuário para autenticação e gerenciamento de contas.
    Integra com Flask-Login via UserMixin.
    """
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    favorite_movies = db.relationship("Movie", secondary=favorite_movies, lazy="dynamic",
                                      backref=db.backref("favorited_by", lazy="dynamic"))
    favorite_series = db.relationship("Series", secondary=favorite_series, lazy="dynamic",
                                      backref=db.backref("favorited_by", lazy="dynamic"))

    def set_password(self, password):
        """Define a senha do usuário, aplicando hash."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verifica se a senha fornecida corresponde ao hash armazenado."""
        return check_password_hash(self.password_hash, password)

    def _favorites_of(self, item):
        return self.favorite_movies if item.kind == MOVIE else self.favorite_series

    def has_favorited(self, item):
        return self._favorites_of(item).filter_by(id=item.id).first() is not None

    def toggle_favorite(self, item):
        """Adiciona ou remove o item da lista. Retorna True se ele ficou favoritado."""
        favorites = self._favorites_of(item)
        if self.has_favorited(item):
            favorites.remove(item)
            return False
        favorites.append(item)
        return True

    @property
    def favorites_count(self):
        return self.favorite_movies.count() + self.favorite_series.count()

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Genre(db.Model):
    """
    Modelo para categorias/gêneros de filmes e séries.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    description = db.Column(db.String(200), nullable=True)

    @validates("name")
    def _sync_slug(self, key, value):
        self.slug = slugify(value)
        return value

    def __repr__(self):
        return f"<Genre {self.name}>"


class CatalogItem:
    """
    Campos e comportamentos comuns a filmes e séries.
    Cada subclasse define `kind`, a data de estreia e a relação com gêneros.
    """
    kind = None
    catalog_key = db.Column(db.String(64), unique=True, nullable=True)

    id = db.Column(db.Integer, primary_key=True)
    tmdb_id = db.Column(db.Integer, nullable=True, unique=True, index=True)
    title = db.Column(db.String(255), nullable=False)
    original_title = db.Column(db.String(255), nullable=True)
    slug = db.Column(db.String(255), nullable=False, default="titulo")
    tagline = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    cast = db.Column(db.Text, nullable=True)
    rating = db.Column(db.Float, default=0.0)            # Nota média (0 a 10)
    vote_count = db.Column(db.Integer, default=0)
    popularity = db.Column(db.Float, default=0.0)
    poster_url = db.Column(db.String(500), nullable=True)    # Caminho do TMDb ou URL completa
    backdrop_url = db.Column(db.String(500), nullable=True)  # Imagem de fundo (paisagem)
    trailer_url = db.Column(db.String(255), nullable=True)   # Link do YouTube
    featured = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @validates("title")
    def _sync_slug(self, key, value):
        self.slug = slugify(value)
        return value

    @property
    def kind_label(self):
        return KIND_LABELS[self.kind]

    @property
    def premiere(self):
        return self.release_date if self.kind == MOVIE else self.start_date

    @property
    def year(self):
        return self.premiere.year if self.premiere else None

    @property
    def cast_list(self):
        return [name.strip() for name in (self.cast or "").split(",") if name.strip()]

    @property
    def url(self):
        endpoint = "main.movie_detail" if self.kind == MOVIE else "main.series_detail"
        id_arg = "movie_id" if self.kind == MOVIE else "series_id"
        return url_for(endpoint, slug=self.slug, **{id_arg: self.id})

    def poster(self, size="w342"):
        return image_url(self.poster_url, size)

    def backdrop(self, size="w1280"):
        return image_url(self.backdrop_url, size)

    @property
    def trailer_key(self):
        return youtube_key(self.trailer_url)

    @property
    def trailer_embed_url(self):
        key = self.trailer_key
        return f"https://www.youtube-nocookie.com/embed/{key}?autoplay=1&rel=0" if key else None

    @property
    def trailer_thumb_url(self):
        key = self.trailer_key
        return f"https://i.ytimg.com/vi/{key}/hqdefault.jpg" if key else None

    @property
    def placeholder_hue(self):
        """Variação de cor do pôster genérico, estável por título."""
        return sum(map(ord, self.title or "")) % 8

    def to_dict(self, detail=False):
        data = {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "year": self.year,
            "rating": round(self.rating or 0, 1),
            "poster": self.poster(),
            "url": self.url,
        }
        if detail:
            data.update({
                "tmdb_id": self.tmdb_id,
                "original_title": self.original_title,
                "tagline": self.tagline,
                "description": self.description,
                "backdrop": self.backdrop(),
                "trailer_youtube_key": self.trailer_key,
                "cast": self.cast_list,
                "genres": [{"name": g.name, "slug": g.slug} for g in self.genres],
                "vote_count": self.vote_count,
            })
        return data


class Playable:
    """Fontes cadastradas pelo administrador; não são fornecidas pelo TMDb."""
    video_url = db.Column(db.String(2048), nullable=True)
    video_type = db.Column(db.String(12), nullable=False, default="auto", server_default="auto")
    subtitle_url = db.Column(db.String(2048), nullable=True)

    @declared_attr
    def sources(cls):
        return db.relationship("MediaSource", foreign_keys=f"MediaSource.{cls.__name__.lower()}_id",
                               lazy="selectin", passive_deletes=True)

    @property
    def managed_sources(self):
        return any(source.enabled for source in self.sources)

    @property
    def has_playback(self):
        return bool(self.video_url) or self.managed_sources

    @property
    def uses_hls(self):
        return self.video_type == "hls" or (
            self.video_type == "auto" and urlsplit(self.video_url or "").path.lower().endswith(".m3u8")
        )


class Movie(Playable, CatalogItem, db.Model):
    """
    Modelo para filmes.
    """
    kind = MOVIE

    release_date = db.Column(db.Date, nullable=True)
    director = db.Column(db.String(255), nullable=True)
    runtime = db.Column(db.Integer, nullable=True)  # Duração em minutos

    genres = db.relationship("Genre", secondary=movie_genre_association, order_by="Genre.name",
                             backref=db.backref("movies", lazy="dynamic"))

    def to_dict(self, detail=False):
        data = super().to_dict(detail)
        if detail:
            data.update({
                "release_date": self.release_date.isoformat() if self.release_date else None,
                "director": self.director,
                "runtime": self.runtime,
            })
        return data

    def __repr__(self):
        return f"<Movie {self.title}>"


class Series(CatalogItem, db.Model):
    """
    Modelo para séries.
    """
    kind = SERIES

    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)  # Nulo enquanto a série estiver no ar
    creator = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(40), nullable=True)
    episode_runtime = db.Column(db.Integer, nullable=True)

    genres = db.relationship("Genre", secondary=series_genre_association, order_by="Genre.name",
                             backref=db.backref("series", lazy="dynamic"))
    seasons = db.relationship("Season", backref="series", lazy="dynamic",
                              cascade="all, delete-orphan", order_by="Season.season_number")

    @property
    def years_label(self):
        if not self.start_date:
            return None
        end = self.end_date.year if self.end_date else ""
        return f"{self.start_date.year}–{end}" if end != self.start_date.year else str(end)

    def to_dict(self, detail=False):
        data = super().to_dict(detail)
        if detail:
            data.update({
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "end_date": self.end_date.isoformat() if self.end_date else None,
                "creator": self.creator,
                "status": self.status,
                "seasons": [s.to_dict() for s in self.seasons],
            })
        return data

    def __repr__(self):
        return f"<Series {self.title}>"


class Season(db.Model):
    """
    Modelo para temporadas de séries.
    """
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True)
    season_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    release_date = db.Column(db.Date, nullable=True)
    poster_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    episodes = db.relationship("Episode", backref="season", lazy="dynamic",
                               cascade="all, delete-orphan", order_by="Episode.episode_number")

    @property
    def display_title(self):
        return self.title or f"Temporada {self.season_number}"

    def poster(self, size="w185"):
        return image_url(self.poster_url, size)

    def to_dict(self):
        return {
            "season_number": self.season_number,
            "title": self.display_title,
            "release_date": self.release_date.isoformat() if self.release_date else None,
            "episode_count": self.episodes.count(),
        }

    def __repr__(self):
        return f"<Season {self.season_number} of series {self.series_id}>"


class Episode(Playable, db.Model):
    """
    Modelo para episódios de temporadas.
    """
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey("season.id", ondelete="CASCADE"), nullable=False, index=True)
    episode_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    release_date = db.Column(db.Date, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    still_url = db.Column(db.String(500), nullable=True)  # Imagem da cena do episódio
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def still(self, size="w300"):
        return image_url(self.still_url, size)

    def __repr__(self):
        return f"<Episode {self.episode_number} - {self.title}>"
