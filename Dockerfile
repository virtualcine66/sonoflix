FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    FLASK_APP=run.py

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usuário sem privilégios de root
RUN useradd --create-home appuser && mkdir -p instance && chown -R appuser /app
USER appuser

EXPOSE 8000

# Aplica as migrations e sobe o servidor de produção
CMD ["sh", "-c", "flask db upgrade && gunicorn --bind 0.0.0.0:8000 --workers 2 --access-logfile - run:app"]
