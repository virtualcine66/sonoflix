import os
from datetime import date

from flask import Flask, jsonify, render_template, request, url_for

from app.extensions import csrf, db, limiter, login_manager, migrate


def create_app(config_name=None):
    """
    Cria e configura a instância da aplicação Flask.
    """
    from config import DEV_SECRET_KEY, config_by_name

    config_name = config_name or os.environ.get("APP_ENV", "development")
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "filmes_series.db")
    if config_name == "production" and app.config["SECRET_KEY"] == DEV_SECRET_KEY:
        raise RuntimeError("Defina SECRET_KEY no ambiente antes de subir em produção.")

    # Inicializa as extensões com a aplicação
    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    # Cliente do TMDb compartilhado (configurado só se houver credencial no .env)
    from app.services.tmdb import TMDbClient
    app.extensions["tmdb"] = TMDbClient.from_config(app.config)

    from app.security import register_security
    register_security(app)

    # Importa e registra os Blueprints
    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from app.routes import main_bp
    app.register_blueprint(main_bp)

    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix="/api/v1")

    from app.cli import register_cli
    register_cli(app)

    _register_error_handlers(app)
    _register_template_helpers(app)
    return app


def _wants_json():
    return request.path.startswith("/api/")


def _register_error_handlers(app):
    messages = {
        403: ("Acesso negado", "Você não tem permissão para acessar esta página."),
        404: ("Página não encontrada", "O endereço que você tentou abrir não existe ou foi removido."),
        405: ("Método não permitido", "Essa ação não pode ser feita desse jeito."),
        429: ("Muitas tentativas", "Você fez muitas requisições seguidas. Espere um minuto e tente de novo."),
        500: ("Algo deu errado", "Tivemos um problema interno. Tente novamente em instantes."),
    }

    def handle(error):
        code = getattr(error, "code", 500) or 500
        title, message = messages.get(code, messages[500])
        if code == 500:
            db.session.rollback()
        if _wants_json():
            return jsonify(error=title, message=message), code
        return render_template("errors/error.html", code=code, title=title, message=message), code

    for code in messages:
        app.register_error_handler(code, handle)

    @login_manager.unauthorized_handler
    def unauthorized():
        if _wants_json():
            return jsonify(error="Não autenticado", message="Entre na sua conta para usar este recurso."), 401
        from flask import flash, redirect
        flash(login_manager.login_message, login_manager.login_message_category)
        return redirect(url_for("auth.login", next=request.full_path))


def _register_template_helpers(app):
    from app.models import KIND_LABELS

    @app.template_filter("date_br")
    def date_br(value):
        return value.strftime("%d/%m/%Y") if value else ""

    @app.template_filter("duration")
    def duration(minutes):
        if not minutes:
            return ""
        hours, mins = divmod(int(minutes), 60)
        return f"{hours}h {mins:02d}min" if hours else f"{mins} min"

    @app.template_filter("score")
    def score(value):
        return f"{(value or 0):.1f}".replace(".", ",")

    @app.context_processor
    def inject_globals():
        def url_with(**changes):
            """URL da página atual trocando só alguns parâmetros (paginação, filtros)."""
            args = request.args.to_dict()
            args.update({k: v for k, v in changes.items() if v is not None})
            for key in [k for k, v in changes.items() if v is None]:
                args.pop(key, None)
            return url_for(request.endpoint, **(request.view_args or {}), **args)

        return {
            "url_with": url_with,
            "current_year": date.today().year,
            "kind_labels": KIND_LABELS,
            "tmdb_configured": app.extensions["tmdb"].configured,
        }
