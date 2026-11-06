"""Comandos `flask ...` para administrar o projeto pelo terminal."""
import click
from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models import MOVIE, SERIES, User
from app.services.tmdb import TMDbError


def register_cli(app):
    @app.cli.command("create-admin")
    @click.option("--username", prompt="Usuário")
    @click.option("--email", prompt="E-mail")
    @click.password_option(prompt="Senha", confirmation_prompt="Repita a senha")
    def create_admin(username, email, password):
        """Cria um usuário administrador (ou promove um existente)."""
        if len(password) < 8:
            raise click.ClickException("A senha precisa ter pelo menos 8 caracteres.")
        user = db.session.scalar(db.select(User).where(func.lower(User.username) == username.lower()))
        if user is None:
            user = User(username=username, email=email.strip().lower())
            db.session.add(user)
        user.is_admin = True
        user.set_password(password)
        db.session.commit()
        click.echo(f"Administrador {user.username} pronto.")

    @app.cli.command("seed")
    @click.option("--demo", is_flag=True, help="Usa os dados offline mesmo com o TMDb configurado.")
    def seed(demo):
        """Popula o catálogo (TMDb se configurado; senão, dados de demonstração)."""
        from app.seed import seed_demo, seed_from_tmdb

        client = current_app.extensions["tmdb"]
        if client.configured and not demo:
            click.echo("Importando títulos do TMDb...")
            total = seed_from_tmdb(client, echo=click.echo)
        else:
            if not demo:
                click.echo("TMDb não configurado: usando o catálogo de demonstração.")
            total = seed_demo()
        click.echo(f"Pronto: {total} título(s) adicionados ou atualizados.")

    @app.cli.command("import-tmdb")
    @click.argument("kind", type=click.Choice([MOVIE, SERIES]))
    @click.argument("tmdb_id", type=int)
    def import_tmdb(kind, tmdb_id):
        """Importa um título pelo ID do TMDb. Ex.: flask import-tmdb movie 693134"""
        from app.services.importer import import_title

        try:
            item = import_title(current_app.extensions["tmdb"], kind, tmdb_id)
        except TMDbError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Importado: {item.title}")
