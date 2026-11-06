from urllib.parse import urlsplit

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateField,
    EmailField,
    FloatField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
    widgets,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, ValidationError

from app.extensions import db
from app.models import Genre, User
from app.utils import slugify, youtube_key

NON_MODEL_FIELDS = {"csrf_token", "submit", "genres"}


def populate(form, obj):
    """Como form.populate_obj, mas sem tocar em campos que não são colunas do modelo."""
    for name, field in form._fields.items():
        if name not in NON_MODEL_FIELDS:
            field.populate_obj(obj, name)


def image_path(form, field):
    """Aceita caminho do TMDb ('/abc.jpg') ou URL https completa."""
    if field.data and not field.data.startswith(("/", "https://")):
        raise ValidationError("Use um caminho do TMDb (/abc.jpg) ou uma URL começando com https://")


def youtube_link(form, field):
    if field.data and not youtube_key(field.data):
        raise ValidationError("Cole um link válido do YouTube.")


class MultiCheckboxField(SelectMultipleField):
    """Lista de checkboxes em vez do <select multiple>, mais fácil de usar."""
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class CatalogForm(FlaskForm):
    """
    Campos comuns aos formulários de filme e série.
    """
    title = StringField("Título", validators=[DataRequired(), Length(max=255)])
    original_title = StringField("Título original", validators=[Optional(), Length(max=255)])
    tagline = StringField("Frase de efeito", validators=[Optional(), Length(max=255)])
    description = TextAreaField("Sinopse", validators=[Optional()])
    cast = TextAreaField("Elenco (separado por vírgulas)", validators=[Optional()])
    rating = FloatField("Nota (0 a 10)", validators=[Optional(), NumberRange(min=0, max=10)])
    poster_url = StringField("Pôster", validators=[Optional(), Length(max=500), image_path],
                             description="Caminho do TMDb (/abc.jpg) ou URL https.")
    backdrop_url = StringField("Imagem de fundo", validators=[Optional(), Length(max=500), image_path],
                               description="Imagem horizontal usada no destaque e na página do título.")
    trailer_url = StringField("Trailer (YouTube)", validators=[Optional(), Length(max=255), youtube_link])
    genres = MultiCheckboxField("Gêneros", coerce=int, validators=[Optional()])
    featured = BooleanField("Destacar na página inicial")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.genres.choices = [(g.id, g.name) for g in db.session.scalars(db.select(Genre).order_by(Genre.name))]

    def selected_genres(self):
        if not self.genres.data:
            return []
        return db.session.scalars(db.select(Genre).where(Genre.id.in_(self.genres.data))).all()


def media_link(form, field):
    value = (field.data or "").strip()
    field.data = value
    if not value:
        return
    try:
        parsed = urlsplit(value)
        local = value.startswith("/") and not value.startswith("//") and not parsed.netloc
        remote = parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
        valid_port = parsed.port is None or 0 < parsed.port < 65536
    except ValueError:
        raise ValidationError("Use uma URL HTTPS ou um caminho local começando com /.") from None
    if not (local or remote) or not valid_port or "\\" in value or any(c.isspace() for c in value):
        raise ValidationError("Use uma URL HTTPS ou um caminho local começando com /.")


class PlaybackFields:
    video_url = StringField("Vídeo (URL direta)", validators=[Optional(), Length(max=2048), media_link],
                            description="URL direta HTTPS de MP4, WebM ou HLS. Não use links de páginas ou iframes.")
    video_type = SelectField("Formato do vídeo", default="auto",
                             choices=[("auto", "Detectar pela URL"), ("mp4", "MP4"),
                                      ("webm", "WebM"), ("hls", "HLS (.m3u8)")])
    subtitle_url = StringField("Legenda em português (WebVTT)",
                               validators=[Optional(), Length(max=2048), media_link],
                               description="Arquivo .vtt. Se externo, o servidor deve permitir CORS.")


class MovieForm(PlaybackFields, CatalogForm):
    """
    Formulário para adicionar ou editar um filme.
    """
    release_date = DateField("Data de lançamento", validators=[Optional()])
    director = StringField("Direção", validators=[Optional(), Length(max=255)])
    runtime = IntegerField("Duração (minutos)", validators=[Optional(), NumberRange(min=1, max=1000)])
    submit = SubmitField("Salvar filme")

    field_order = ["title", "original_title", "tagline", "release_date", "runtime", "director", "rating",
                   "description", "cast", "genres", "poster_url", "backdrop_url", "trailer_url",
                   "video_url", "video_type", "subtitle_url", "featured"]


class SeriesForm(CatalogForm):
    """
    Formulário para adicionar ou editar uma série.
    """
    start_date = DateField("Estreia", validators=[Optional()])
    end_date = DateField("Encerramento", validators=[Optional()], description="Deixe vazio se ainda está no ar.")
    creator = StringField("Criação", validators=[Optional(), Length(max=255)])
    episode_runtime = IntegerField("Duração média do episódio (min)", validators=[Optional(), NumberRange(min=1)])
    submit = SubmitField("Salvar série")

    field_order = ["title", "original_title", "tagline", "start_date", "end_date", "creator", "episode_runtime",
                   "rating", "description", "cast", "genres", "poster_url", "backdrop_url", "trailer_url",
                   "featured"]

    def validate_end_date(self, field):
        if field.data and self.start_date.data and field.data < self.start_date.data:
            raise ValidationError("O encerramento não pode ser antes da estreia.")


class SeasonForm(FlaskForm):
    """
    Formulário para adicionar ou editar uma temporada.
    """
    season_number = IntegerField("Número da temporada", validators=[DataRequired(), NumberRange(min=1, max=200)])
    title = StringField("Título da temporada", validators=[Optional(), Length(max=200)])
    description = TextAreaField("Descrição", validators=[Optional()])
    release_date = DateField("Data de lançamento", validators=[Optional()])
    poster_url = StringField("Pôster da temporada", validators=[Optional(), Length(max=500), image_path])
    submit = SubmitField("Salvar temporada")


class EpisodeForm(PlaybackFields, FlaskForm):
    """
    Formulário para adicionar ou editar um episódio.
    """
    episode_number = IntegerField("Número do episódio", validators=[DataRequired(), NumberRange(min=1, max=2000)])
    title = StringField("Título do episódio", validators=[DataRequired(), Length(max=200)])
    description = TextAreaField("Descrição", validators=[Optional()])
    release_date = DateField("Data de exibição", validators=[Optional()])
    duration_minutes = IntegerField("Duração (minutos)", validators=[Optional(), NumberRange(min=1, max=600)])
    still_url = StringField("Imagem do episódio", validators=[Optional(), Length(max=500), image_path])
    submit = SubmitField("Salvar episódio")


class GenreForm(FlaskForm):
    """
    Formulário para adicionar ou editar um gênero.
    """
    name = StringField("Nome do gênero", validators=[DataRequired(), Length(max=60)])
    description = TextAreaField("Descrição", validators=[Optional(), Length(max=200)])
    submit = SubmitField("Salvar gênero")

    def __init__(self, *args, current=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.current = current

    def validate_name(self, field):
        existing = db.session.scalar(db.select(Genre).filter_by(slug=slugify(field.data)))
        if existing and existing is not self.current:
            raise ValidationError("Já existe um gênero com esse nome.")


class UserEditForm(FlaskForm):
    """
    Formulário para editar informações de um usuário (apenas para administradores).
    """
    username = StringField("Nome de usuário", validators=[DataRequired(), Length(min=3, max=30)])
    email = EmailField("E-mail", validators=[DataRequired(), Email(), Length(max=255)])
    is_admin = BooleanField("Administrador")
    submit = SubmitField("Salvar usuário")

    def __init__(self, original_username, original_email, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            if db.session.scalar(db.select(User).filter_by(username=username.data)):
                raise ValidationError("Este nome de usuário já está em uso.")

    def validate_email(self, email):
        if email.data.lower() != self.original_email:
            if db.session.scalar(db.select(User).filter_by(email=email.data.lower())):
                raise ValidationError("Este e-mail já está em uso.")
