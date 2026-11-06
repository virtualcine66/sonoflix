"""Fontes administradas e resolução sob demanda. A URL final fica visível ao usuário autenticado que reproduz."""
import time

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db, limiter, login_manager
from app.models import Episode, Movie, utcnow
from app.services.source_matching import attach
from app.services.source_resolver import SourceError, probe
from app.services.tmdb import TMDbError
from app.source_models import MediaSource
from app.utils import like_pattern

sources_bp = Blueprint("sources", __name__)


@sources_bp.before_request
def authorize():
    if request.path.startswith("/admin/"):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
    elif current_app.config["SOURCE_PLAYBACK_LOGIN_REQUIRED"] and not current_user.is_authenticated:
        return login_manager.unauthorized()


@sources_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@sources_bp.post("/api/v1/playback/<kind>/<int:item_id>")
@limiter.limit("10 per minute")
def playback(kind, item_id):
    model = {"movie": Movie, "episode": Episode}.get(kind)
    if model is None:
        abort(404)
    db.get_or_404(model, item_id)
    column = MediaSource.movie_id if kind == "movie" else MediaSource.episode_id
    selection = request.form.get("source_id", type=int)
    stmt = db.select(MediaSource).where(column == item_id, MediaSource.enabled.is_(True))
    if selection is not None:
        stmt = stmt.where(MediaSource.id == selection)
    sources = db.session.scalars(stmt.order_by(MediaSource.id).limit(3)).all()
    if not sources:
        abort(404)
    hosts = {h.strip().lower() for h in current_app.config["SOURCE_ALLOWED_HOSTS"].split(",") if h.strip()}
    errors = []
    deadline = time.monotonic() + 12
    for source in sources:
        try:
            result = probe(source.get_url(), hosts, deadline=deadline)
            source.last_code, source.checked_at = "ready", utcnow()
            db.session.commit()
            # URL final é necessariamente visível ao navegador, mas nunca vai para logs/banco/cache público.
            return jsonify(url=result["url"], type=result["type"], source_id=source.id,
                           message="Fonte acessível pelo servidor; reprodução depende do navegador.")
        except ValueError:
            error = SourceError("key_error")
        except SourceError as exc:
            error = exc
        source.last_code, source.checked_at = error.code, utcnow()
        errors.append({"source_id": source.id, "code": error.code, "message": str(error)})
        if time.monotonic() >= deadline:
            break
    db.session.commit()
    return jsonify(message=errors[-1]["message"], attempts=errors), 502


@sources_bp.get("/admin/sources")
def listing():
    status = request.args.get("status", "")
    query = request.args.get("q", "").strip()[:200]
    stmt = db.select(MediaSource)
    if status in ("pending", "matched", "review", "error"):
        stmt = stmt.where(MediaSource.match_status == status)
    if query:
        stmt = stmt.where(MediaSource.label.ilike(like_pattern(query), escape="\\"))
    page = db.paginate(stmt.order_by(MediaSource.id), per_page=30, max_per_page=30, error_out=False)
    return render_template("admin/sources.html", page=page, status=status, query=query, title="Fontes de reprodução")


@sources_bp.post("/admin/sources/<int:source_id>/bind")
@limiter.limit("10 per minute")
def bind(source_id):
    source = db.get_or_404(MediaSource, source_id)
    tmdb_id = request.form.get("tmdb_id", type=int)
    if not tmdb_id or tmdb_id < 1:
        abort(400)
    try:
        attach(source, tmdb_id, current_app.extensions["tmdb"])
        flash("Fonte associada ao catálogo.", "success")
    except (ValueError, TMDbError) as exc:
        db.session.rollback()
        flash(str(exc), "danger")
    return redirect(url_for("sources.listing", q=source.label))
