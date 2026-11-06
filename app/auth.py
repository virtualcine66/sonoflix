from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from sqlalchemy import func, or_
from wtforms import BooleanField, EmailField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, ValidationError

from app.extensions import db, limiter
from app.models import User
from app.utils import safe_next

# Cria um Blueprint para as rotas de autenticação
auth_bp = Blueprint("auth", __name__)


# Formulário de Registro
class RegistrationForm(FlaskForm):
    username = StringField("Nome de usuário", validators=[
        DataRequired(),
        Length(min=3, max=30),
        Regexp(r"^[A-Za-z0-9_.]+$", message="Use apenas letras, números, ponto e sublinhado."),
    ])
    email = EmailField("E-mail", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Senha", validators=[
        DataRequired(), Length(min=8, message="A senha precisa ter pelo menos 8 caracteres.")])
    password2 = PasswordField("Repita a senha", validators=[
        DataRequired(), EqualTo("password", message="As senhas não conferem.")])
    submit = SubmitField("Criar conta")

    def validate_username(self, username):
        exists = db.session.scalar(db.select(User).where(func.lower(User.username) == username.data.lower()))
        if exists:
            raise ValidationError("Esse nome de usuário já está em uso.")

    def validate_email(self, email):
        if db.session.scalar(db.select(User).filter_by(email=email.data.strip().lower())):
            raise ValidationError("Esse e-mail já está cadastrado.")


# Formulário de Login
class LoginForm(FlaskForm):
    identifier = StringField("Usuário ou e-mail", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Senha", validators=[DataRequired()])
    remember_me = BooleanField("Manter conectado")
    submit = SubmitField("Entrar")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    """
    Rota para registro de novos usuários. Já entra na conta após o cadastro.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data.strip(), email=form.email.data.strip().lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Conta criada. Boas-vindas, {user.username}!", "success")
        return redirect(safe_next(request.args.get("next"), url_for("main.index")))
    return render_template("register.html", title="Criar conta", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    """
    Rota para login com usuário ou e-mail.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data.strip().lower()
        user = db.session.scalar(db.select(User).where(
            or_(func.lower(User.username) == identifier, User.email == identifier)))
        if user is None or not user.check_password(form.password.data):
            flash("Usuário ou senha inválidos.", "danger")
        else:
            login_user(user, remember=form.remember_me.data)
            # Só volta para páginas do próprio site (evita open redirect)
            return redirect(safe_next(request.args.get("next"), url_for("main.index")))
    return render_template("login.html", title="Entrar", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """
    Logout só via POST (com CSRF), para que um link externo não desconecte o usuário.
    """
    logout_user()
    flash("Você saiu da sua conta.", "info")
    return redirect(url_for("main.index"))
