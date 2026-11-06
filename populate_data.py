"""
Atalho mantido por compatibilidade: popula o catálogo.

Prefira o comando do Flask:  flask seed   (ou  flask seed --demo)
"""
from app import create_app
from app.seed import seed_demo, seed_from_tmdb

app = create_app()

with app.app_context():
    client = app.extensions["tmdb"]
    total = seed_from_tmdb(client) if client.configured else seed_demo()
    print(f"Pronto: {total} título(s) adicionados ou atualizados.")
