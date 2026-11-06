from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app.admin.forms import EpisodeForm, GenreForm, MovieForm, SeasonForm, SeriesForm, UserEditForm, populate
from app.extensions import db, login_manager
from app.models import MOVIE, SERIES, Episode, Genre, Movie, Season, Series, User, favorite_movies, favorite_series
from app.services.importer import import_title
from app.services.tmdb import TMDbError
from app.utils import like_pattern, safe_next

# Cria um Blueprint para as rotas de administração
admin_bp = Blueprint("admin", __name__)

PER_PAGE = 20


@admin_bp.before_request
def admin_required():
    """
    Todas as rotas do painel exigem login de administrador.
    """
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    if not current_user.is_admin:
        abort(403)


def _tmdb():
    return current_app.extensions["tmdb"]


def _render_form(form, title, back_url, **context):
    return render_template("admin/form.html", form=form, title=title, back_url=back_url, **context)


@admin_bp.route("/dashboard")
@admin_bp.route("/")
def dashboard():
    """
    Painel com totais, títulos recentes e os mais favoritados.
    """
    stats = {
        "Filmes": db.session.scalar(db.select(func.count(Movie.id))),
        "Séries": db.session.scalar(db.select(func.count(Series.id))),
        "Gêneros": db.session.scalar(db.select(func.count(Genre.id))),
        "Usuários": db.session.scalar(db.select(func.count(User.id))),
    }
    recent = sorted(
        db.session.scalars(db.select(Movie).order_by(Movie.created_at.desc()).limit(6)).all()
        + db.session.scalars(db.select(Series).order_by(Series.created_at.desc()).limit(6)).all(),
        key=lambda item: item.created_at, reverse=True,
    )[:6]
    most_favorited = []
    for model, table, column in ((Movie, favorite_movies, favorite_movies.c.movie_id),
                                 (Series, favorite_series, favorite_series.c.series_id)):
        rows = db.session.execute(
            db.select(model, func.count().label("total")).join(table, column == model.id)
            .group_by(model.id).order_by(func.count().desc()).limit(5)
        ).all()
        most_favorited.extend(rows)
    most_favorited.sort(key=lambda row: row.total, reverse=True)
    return render_template("admin/dashboard.html", title="Painel", stats=stats, recent=recent,
                           most_favorited=most_favorited[:5])


# --- Listagem, cadastro e edição de filmes e séries ----------------------

CATALOG = {
    MOVIE: {"model": Movie, "form": MovieForm, "label": "Filme", "plural": "Filmes"},
    SERIES: {"model": Series, "form": SeriesForm, "label": "Série", "plural": "Séries"},
}


def _catalog_or_404(kind):
    return CATALOG.get(kind) or abort(404)


def _list(kind):
    meta = CATALOG[kind]
    model = meta["model"]
    query = request.args.get("q", "").strip()
    stmt = db.select(model)
    if query:
        stmt = stmt.where(model.title.ilike(like_pattern(query), escape="\\"))
    page = db.paginate(stmt.order_by(model.title), per_page=PER_PAGE, error_out=False)
    return render_template("admin/catalog_list.html", title=f"Gerenciar {meta['plural'].lower()}",
                           kind=kind, meta=meta, page=page, query=query)


@admin_bp.route("/movies")
def list_movies():
    """Lista todos os filmes no painel de administração."""
    return _list(MOVIE)


@admin_bp.route("/series")
def list_series():
    """Lista todas as séries no painel de administração."""
    return _list(SERIES)


def _list_endpoint(kind):
    return "admin.list_movies" if kind == MOVIE else "admin.list_series"


def _save_item(form, item):
    populate(form, item)
    item.genres = form.selected_genres()
    db.session.add(item)
    db.session.commit()


@admin_bp.route("/<kind>/add", methods=["GET", "POST"])
def add_item(kind):
    """Cadastro manual de filme ou série (para títulos que não estão no TMDb)."""
    meta = _catalog_or_404(kind)
    form = meta["form"]()
    if form.validate_on_submit():
        item = meta["model"]()
        _save_item(form, item)
        flash(f"{meta['label']} “{item.title}” cadastrado(a).", "success")
        return redirect(url_for(_list_endpoint(kind)))
    return _render_form(form, f"Adicionar {meta['label'].lower()}", url_for(_list_endpoint(kind)))


@admin_bp.route("/<kind>/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(kind, item_id):
    meta = _catalog_or_404(kind)
    item = db.get_or_404(meta["model"], item_id)
    form = meta["form"](obj=item)
    if request.method == "GET":
        form.genres.data = [g.id for g in item.genres]
    if form.validate_on_submit():
        _save_item(form, item)
        flash(f"“{item.title}” atualizado(a).", "success")
        return redirect(url_for(_list_endpoint(kind)))
    return _render_form(form, f"Editar “{item.title}”", url_for(_list_endpoint(kind)), item=item)


@admin_bp.route("/<kind>/<int:item_id>/delete", methods=["POST"])
def delete_item(kind, item_id):
    meta = _catalog_or_404(kind)
    item = db.get_or_404(meta["model"], item_id)
    db.session.delete(item)
    db.session.commit()
    flash(f"“{item.title}” excluído(a).", "success")
    return redirect(url_for(_list_endpoint(kind)))


@admin_bp.route("/<kind>/<int:item_id>/feature", methods=["POST"])
def toggle_featured(kind, item_id):
    item = db.get_or_404(_catalog_or_404(kind)["model"], item_id)
    item.featured = not item.featured
    db.session.commit()
    flash(f"“{item.title}” {'agora aparece' if item.featured else 'não aparece mais'} em destaque.", "success")
    return redirect(safe_next(request.form.get("next"), url_for(_list_endpoint(kind))))


@admin_bp.route("/<kind>/<int:item_id>/refresh", methods=["POST"])
def refresh_item(kind, item_id):
    """Reimporta os dados do TMDb (nota, pôster, temporadas novas...)."""
    item = db.get_or_404(_catalog_or_404(kind)["model"], item_id)
    if not item.tmdb_id:
        flash("Esse título foi cadastrado à mão e não tem vínculo com o TMDb.", "danger")
    else:
        try:
            import_title(_tmdb(), kind, item.tmdb_id)
            flash(f"“{item.title}” atualizado com os dados do TMDb.", "success")
        except TMDbError as exc:
            db.session.rollback()
            flash(str(exc), "danger")
    return redirect(safe_next(request.form.get("next"), url_for(_list_endpoint(kind))))


# --- Importação do TMDb ---------------------------------------------------

@admin_bp.route("/import")
def import_search():
    """
    Busca no TMDb e mostra os resultados com botão de importar.
    """
    query = request.args.get("q", "").strip()
    kind = request.args.get("kind", MOVIE)
    kind = kind if kind in CATALOG else MOVIE
    results, error = [], None
    if query:
        try:
            results = _tmdb().search(query, kind)
        except TMDbError as exc:
            error = str(exc)
    model = CATALOG[kind]["model"]
    ids = [r["tmdb_id"] for r in results]
    imported = {
        tmdb_id: item_id for tmdb_id, item_id in
        db.session.execute(db.select(model.tmdb_id, model.id).where(model.tmdb_id.in_(ids)))
    } if ids else {}
    return render_template("admin/import.html", title="Importar do TMDb", query=query, kind=kind,
                           results=results, imported=imported, error=error,
                           image_base=current_app.config["TMDB_IMAGE_BASE"])


@admin_bp.route("/import", methods=["POST"])
def import_item():
    kind = request.form.get("kind")
    tmdb_id = request.form.get("tmdb_id", type=int)
    if kind not in CATALOG or not tmdb_id:
        abort(400)
    try:
        item = import_title(_tmdb(), kind, tmdb_id)
        flash(f"“{item.title}” importado com sucesso.", "success")
    except TMDbError as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(safe_next(request.form.get("next"), url_for("admin.import_search")))


# --- Rotas para Temporadas (associadas a uma série) ------------------------

@admin_bp.route("/series/<int:series_id>/seasons")
def list_seasons(series_id):
    """Lista as temporadas de uma série específica."""
    series_item = db.get_or_404(Series, series_id)
    return render_template("admin/seasons_list.html", title=f"Temporadas de {series_item.title}",
                           series=series_item, seasons=series_item.seasons.all())


@admin_bp.route("/series/<int:series_id>/seasons/add", methods=["GET", "POST"])
def add_season(series_id):
    """Adiciona uma nova temporada a uma série."""
    series_item = db.get_or_404(Series, series_id)
    form = SeasonForm()
    if form.validate_on_submit():
        season = Season(series_id=series_item.id)
        populate(form, season)
        db.session.add(season)
        db.session.commit()
        flash("Temporada adicionada.", "success")
        return redirect(url_for("admin.list_seasons", series_id=series_item.id))
    return _render_form(form, f"Nova temporada de “{series_item.title}”",
                        url_for("admin.list_seasons", series_id=series_item.id))


@admin_bp.route("/season/<int:season_id>/edit", methods=["GET", "POST"])
def edit_season(season_id):
    """Edita uma temporada existente."""
    season = db.get_or_404(Season, season_id)
    form = SeasonForm(obj=season)
    if form.validate_on_submit():
        populate(form, season)
        db.session.commit()
        flash("Temporada atualizada.", "success")
        return redirect(url_for("admin.list_seasons", series_id=season.series_id))
    return _render_form(form, f"Editar {season.display_title}",
                        url_for("admin.list_seasons", series_id=season.series_id))


@admin_bp.route("/season/<int:season_id>/delete", methods=["POST"])
def delete_season(season_id):
    """Exclui uma temporada e seus episódios."""
    season = db.get_or_404(Season, season_id)
    series_id = season.series_id
    db.session.delete(season)
    db.session.commit()
    flash("Temporada excluída.", "success")
    return redirect(url_for("admin.list_seasons", series_id=series_id))


# --- Rotas para Episódios (associados a uma temporada) ---------------------

@admin_bp.route("/season/<int:season_id>/episodes")
def list_episodes(season_id):
    """Lista os episódios de uma temporada específica."""
    season = db.get_or_404(Season, season_id)
    return render_template("admin/episodes_list.html", title=f"Episódios · {season.display_title}",
                           season=season, episodes=season.episodes.all())


@admin_bp.route("/season/<int:season_id>/episodes/add", methods=["GET", "POST"])
def add_episode(season_id):
    """Adiciona um novo episódio a uma temporada."""
    season = db.get_or_404(Season, season_id)
    form = EpisodeForm()
    if form.validate_on_submit():
        episode = Episode(season_id=season.id)
        populate(form, episode)
        db.session.add(episode)
        db.session.commit()
        flash("Episódio adicionado.", "success")
        return redirect(url_for("admin.list_episodes", season_id=season.id))
    return _render_form(form, f"Novo episódio · {season.display_title}",
                        url_for("admin.list_episodes", season_id=season.id))


@admin_bp.route("/episode/<int:episode_id>/edit", methods=["GET", "POST"])
def edit_episode(episode_id):
    """Edita um episódio existente."""
    episode = db.get_or_404(Episode, episode_id)
    form = EpisodeForm(obj=episode)
    if form.validate_on_submit():
        populate(form, episode)
        db.session.commit()
        flash("Episódio atualizado.", "success")
        return redirect(url_for("admin.list_episodes", season_id=episode.season_id))
    return _render_form(form, f"Editar episódio {episode.episode_number}",
                        url_for("admin.list_episodes", season_id=episode.season_id))


@admin_bp.route("/episode/<int:episode_id>/delete", methods=["POST"])
def delete_episode(episode_id):
    """Exclui um episódio."""
    episode = db.get_or_404(Episode, episode_id)
    season_id = episode.season_id
    db.session.delete(episode)
    db.session.commit()
    flash("Episódio excluído.", "success")
    return redirect(url_for("admin.list_episodes", season_id=season_id))


# --- Rotas para Gêneros ------------------------------------------------------

@admin_bp.route("/genres", methods=["GET", "POST"])
def list_genres():
    """Lista os gêneros com a contagem de títulos e permite criar novos."""
    form = GenreForm()
    if form.validate_on_submit():
        db.session.add(Genre(name=form.name.data.strip(), description=form.description.data or None))
        db.session.commit()
        flash("Gênero adicionado.", "success")
        return redirect(url_for("admin.list_genres"))
    genres = db.session.scalars(db.select(Genre).order_by(Genre.name)).all()
    return render_template("admin/genres.html", title="Gêneros", genres=genres, form=form)


@admin_bp.route("/genres/<int:genre_id>/edit", methods=["GET", "POST"])
def edit_genre(genre_id):
    """Edita um gênero existente."""
    genre = db.get_or_404(Genre, genre_id)
    form = GenreForm(obj=genre, current=genre)
    if form.validate_on_submit():
        genre.name = form.name.data.strip()
        genre.description = form.description.data or None
        db.session.commit()
        flash("Gênero atualizado.", "success")
        return redirect(url_for("admin.list_genres"))
    return _render_form(form, f"Editar gênero “{genre.name}”", url_for("admin.list_genres"))


@admin_bp.route("/genres/<int:genre_id>/delete", methods=["POST"])
def delete_genre(genre_id):
    """Exclui um gênero (os títulos continuam, só perdem a categoria)."""
    genre = db.get_or_404(Genre, genre_id)
    db.session.delete(genre)
    db.session.commit()
    flash(f"Gênero “{genre.name}” excluído.", "success")
    return redirect(url_for("admin.list_genres"))


# --- Rotas para Usuários -----------------------------------------------------

def _admin_count():
    return db.session.scalar(db.select(func.count(User.id)).filter_by(is_admin=True))


@admin_bp.route("/users")
def list_users():
    """Lista todos os usuários no painel de administração."""
    page = db.paginate(db.select(User).order_by(User.created_at.desc()), per_page=PER_PAGE, error_out=False)
    return render_template("admin/users.html", title="Usuários", page=page)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
def edit_user(user_id):
    """Edita um usuário existente."""
    user = db.get_or_404(User, user_id)
    form = UserEditForm(original_username=user.username, original_email=user.email, obj=user)
    if form.validate_on_submit():
        if user.is_admin and not form.is_admin.data and (user == current_user or _admin_count() == 1):
            flash("Você não pode remover o próprio acesso de administrador nem o do último admin.", "danger")
        else:
            user.username = form.username.data.strip()
            user.email = form.email.data.strip().lower()
            user.is_admin = form.is_admin.data
            db.session.commit()
            flash("Usuário atualizado.", "success")
            return redirect(url_for("admin.list_users"))
    return _render_form(form, f"Editar usuário {user.username}", url_for("admin.list_users"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
def delete_user(user_id):
    """Exclui um usuário."""
    user = db.get_or_404(User, user_id)
    if user == current_user:
        flash("Você não pode excluir a própria conta pelo painel.", "danger")
    elif user.is_admin and _admin_count() == 1:
        flash("Não é possível excluir o último administrador.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"Usuário {user.username} excluído.", "success")
    return redirect(url_for("admin.list_users"))
