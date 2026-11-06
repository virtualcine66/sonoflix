"""
API REST pública em JSON (/api/v1).

Leitura é aberta; favoritos exigem sessão e o cabeçalho X-CSRFToken.
"""
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from app.catalog import SORT_OPTIONS, catalog_query, search_items
from app.extensions import db
from app.models import MOVIE, SERIES, Genre, Movie, Series

api_bp = Blueprint("api", __name__)

MODELS = {MOVIE: Movie, SERIES: Series}
MAX_PER_PAGE = 50


def _model_or_404(kind):
    model = MODELS.get(kind)
    if model is None:
        abort(404)
    return model


def _page_payload(page):
    return {
        "items": [item.to_dict() for item in page.items],
        "page": page.page,
        "per_page": page.per_page,
        "total": page.total,
        "pages": page.pages,
    }


@api_bp.get("/<kind>")
def list_items(kind):
    """GET /api/v1/movie?genre=drama&sort=rating&page=2"""
    model = _model_or_404(kind)
    sort = request.args.get("sort", "popular")
    if sort not in SORT_OPTIONS:
        return jsonify(error="Parâmetro inválido", message=f"sort deve ser um de: {', '.join(SORT_OPTIONS)}"), 400
    genre = None
    if request.args.get("genre"):
        genre = db.first_or_404(db.select(Genre).filter_by(slug=request.args["genre"]))
    per_page = max(1, min(request.args.get("per_page", 20, type=int), MAX_PER_PAGE))
    page = db.paginate(catalog_query(model, genre, sort), page=request.args.get("page", 1, type=int),
                       per_page=per_page, error_out=False)
    return jsonify(_page_payload(page))


@api_bp.get("/<kind>/<int:item_id>")
def get_item(kind, item_id):
    item = db.get_or_404(_model_or_404(kind), item_id)
    return jsonify(item.to_dict(detail=True))


@api_bp.get("/genres")
def list_genres():
    genres = db.session.scalars(db.select(Genre).order_by(Genre.name)).all()
    return jsonify([
        {"name": g.name, "slug": g.slug, "movies": g.movies.count(), "series": g.series.count()}
        for g in genres
    ])


@api_bp.get("/search")
def search():
    """Usado pelo autocompletar do cabeçalho. Exige ao menos 2 caracteres."""
    query = request.args.get("q", "").strip()[:100]
    limit = max(1, min(request.args.get("limit", 8, type=int), 20))
    if len(query) < 2:
        return jsonify(results=[])
    return jsonify(results=[item.to_dict() for item in search_items(query, limit)])


@api_bp.get("/me/favorites")
@login_required
def my_favorites():
    return jsonify(
        movies=[m.to_dict() for m in current_user.favorite_movies],
        series=[s.to_dict() for s in current_user.favorite_series],
    )


@api_bp.route("/favorites/<kind>/<int:item_id>", methods=["POST", "DELETE"])
@login_required
def favorite(kind, item_id):
    """POST adiciona e DELETE remove o título da lista do usuário (operações idempotentes)."""
    item = db.get_or_404(_model_or_404(kind), item_id)
    wanted = request.method == "POST"
    if current_user.has_favorited(item) != wanted:
        current_user.toggle_favorite(item)
        db.session.commit()
    return jsonify(kind=kind, id=item.id, favorited=wanted)
