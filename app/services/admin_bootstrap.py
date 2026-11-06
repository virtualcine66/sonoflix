"""Restaura o administrador de teste usando apenas segredos do ambiente."""
import os

from sqlalchemy import func, inspect, or_
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User


def restore_admin(app):
    username = os.environ.get('ADMIN_USER', '').strip()
    email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
    password = os.environ.get('ADMIN_PASSWORD', '')
    if not all((username, email, password)):
        return
    if len(password) < 8:
        app.logger.error('ADMIN_PASSWORD precisa ter pelo menos 8 caracteres; restauração ignorada.')
        return
    with app.app_context():
        # A chamada inicial de flask db upgrade pode acontecer antes da criação das tabelas.
        if not inspect(db.engine).has_table('user'):
            return
        users = db.session.scalars(db.select(User).where(or_(
            func.lower(User.username) == username.lower(), func.lower(User.email) == email))).all()
        if users and (len(users) != 1 or users[0].username.lower() != username.lower()
                      or users[0].email.lower() != email):
            app.logger.error('ADMIN_USER/ADMIN_EMAIL conflitam com outra conta; restauração ignorada.')
            return
        user = users[0] if users else User(username=username, email=email)
        if not users or not user.check_password(password):
            user.set_password(password)
        user.is_admin = True
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            # Outro worker pode ter criado a mesma conta simultaneamente.
            db.session.rollback()
