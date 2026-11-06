from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.catalog import (
    SORT_OPTIONS,
    Rail,
    catalog_query,
    featured_item,
    genres_in_use,
    home_rails,
    related_items,
    search_items,
)
from app.extensions import db
from app.models import MOVIE, SERIES, Episode, Genre, Movie, Season, Series
from app.utils import safe_next

# Cria um Blueprint para as rotas principais do site
main_bp = Blueprint("main", __name__)


@main_bp.route("/index")
@main_bp.route("/")
def index():
    """
    Página inicial: destaque com imagem de fundo e fileiras por categoria.
    """
    return render_template("index.html", title="Início", featured=featured_item(), rails=home_rails(url_for))


def _catalog(model, heading):
    sort = request.args.get("sort", "popular")
    if sort not in SORT_OPTIONS:
        sort = "popular"
    genre = None
    if request.args.get("genre"):
        genre = db.first_or_404(db.select(Genre).filter_by(slug=request.args["genre"]))
    page = db.paginate(catalog_query(model, genre, sort), per_page=current_app.config["ITEMS_PER_PAGE"],
                       error_out=False)
    return render_template("catalog.html", title=heading, heading=heading, page=page, genre=genre,
                           genres=genres_in_use(model), sort=sort, sort_options=SORT_OPTIONS)


@main_bp.route("/movies")
def movies():
    """Lista de filmes com filtro por gênero, ordenação e paginação."""
    return _catalog(Movie, "Filmes")


@main_bp.route("/series")
def series():
    """Lista de séries com filtro por gênero, ordenação e paginação."""
    return _catalog(Series, "Séries")


def _detail(model, item_id, slug, endpoint, id_arg):
    item = db.get_or_404(model, item_id)
    if slug != item.slug:
        # URL canônica com o nome do título (melhor para SEO e para compartilhar)
        return redirect(url_for(endpoint, slug=item.slug, **{id_arg: item.id}), code=301)
    is_favorite = current_user.is_authenticated and current_user.has_favorited(item)
    return render_template("detail.html", title=item.title, item=item, is_favorite=is_favorite,
                           related=Rail("Você também pode gostar", None, related_items(item)))


@main_bp.route("/movie/<int:movie_id>")
@main_bp.route("/movie/<int:movie_id>/<slug>")
def movie_detail(movie_id, slug=None):
    return _detail(Movie, movie_id, slug, "main.movie_detail", "movie_id")


@main_bp.route("/series/<int:series_id>")
@main_bp.route("/series/<int:series_id>/<slug>")
def series_detail(series_id, slug=None):
    return _detail(Series, series_id, slug, "main.series_detail", "series_id")


@main_bp.route("/search")
def search():
    """
    Busca em filmes e séries por título, elenco e direção/criação.
    """
    query = request.args.get("query", "").strip()[:100]
    results = search_items(query, limit=100) if query else []
    return render_template("search_results.html", title="Busca", query=query, results=results)


@main_bp.route("/profile")
@login_required
def profile():
    """
    Perfil do usuário com a sua lista de favoritos.
    """
    favorites = sorted(
        list(current_user.favorite_movies) + list(current_user.favorite_series),
        key=lambda item: item.title.lower(),
    )
    return render_template("profile.html", title="Minha lista", favorites=favorites)


@main_bp.route("/favorites/<kind>/<int:item_id>", methods=["POST"])
@login_required
def toggle_favorite(kind, item_id):
    """
    Adiciona/remove dos favoritos. Funciona sem JavaScript; com JS o front usa a API.
    """
    model = {MOVIE: Movie, SERIES: Series}.get(kind) or abort(404)
    item = db.get_or_404(model, item_id)
    added = current_user.toggle_favorite(item)
    db.session.commit()
    flash(f"“{item.title}” {'entrou na' if added else 'saiu da'} sua lista.", "success")
    return redirect(safe_next(request.form.get("next"), item.url))


@main_bp.route("/watch/<kind>/<int:item_id>")
def watch(kind, item_id):
    model = {"movie": Movie, "episode": Episode}.get(kind)
    if model is None:
        abort(404)
    media = db.get_or_404(model, item_id)
    if not media.has_playback:
        abort(404)
    parent = media if kind == "movie" else media.season.series
    next_episode = None
    if kind == "episode":
        next_episode = db.session.scalar(
            db.select(Episode).join(Season).where(
                Season.series_id == parent.id,
                or_(Season.season_number > media.season.season_number,
                    (Season.season_number == media.season.season_number)
                    & (Episode.episode_number > media.episode_number)),
                or_((Episode.video_url.is_not(None)) & (Episode.video_url != ''),
                    Episode.sources.any(enabled=True)))
            .order_by(Season.season_number, Episode.episode_number, Episode.id).limit(1))
    return render_template("watch.html", title=media.title, media=media, parent=parent,
                           kind=kind, next_episode=next_episode)
