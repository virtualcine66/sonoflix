from app import create_app

# O ambiente vem da variável APP_ENV (development, production ou testing).
# Exemplo: APP_ENV=production gunicorn run:app
app = create_app()

if __name__ == "__main__":
    # Servidor de desenvolvimento do Flask. Em produção use o gunicorn (veja o README).
    app.run(debug=app.config["DEBUG"], port=5000)
