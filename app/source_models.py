"""Fontes privadas e fila persistente de correspondência do catálogo."""
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.extensions import db
from app.models import utcnow


def cipher():
    key = current_app.config.get("SOURCE_ENCRYPTION_KEY")
    if not key:
        raise ValueError("Configure SOURCE_ENCRYPTION_KEY antes de importar fontes.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("SOURCE_ENCRYPTION_KEY inválida.") from exc


class MediaSource(db.Model):
    __tablename__ = "media_source"
    id = db.Column(db.Integer, primary_key=True)
    fingerprint = db.Column(db.String(64), unique=True, nullable=False)
    encrypted_url = db.Column(db.Text, nullable=False)
    label = db.Column(db.String(500), nullable=False)
    group_name = db.Column(db.String(255), nullable=False, default="")
    search_title = db.Column(db.String(500), nullable=False)
    kind = db.Column(db.String(12), nullable=False)
    year = db.Column(db.Integer)
    season_number = db.Column(db.Integer)
    episode_number = db.Column(db.Integer)
    match_status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    candidates = db.Column(db.JSON)
    movie_id = db.Column(db.Integer, db.ForeignKey("movie.id", ondelete="SET NULL"), index=True)
    episode_id = db.Column(db.Integer, db.ForeignKey("episode.id", ondelete="SET NULL"), index=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_code = db.Column(db.String(40))
    checked_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (db.CheckConstraint("movie_id IS NULL OR episode_id IS NULL", name="one_source_target"),)

    def set_url(self, url):
        self.encrypted_url = cipher().encrypt(url.encode()).decode()

    def get_url(self):
        try:
            return cipher().decrypt(self.encrypted_url.encode()).decode()
        except InvalidToken as exc:
            raise ValueError("A chave de fontes não corresponde a este banco.") from exc
