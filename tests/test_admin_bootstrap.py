from app.models import User
from app.services.admin_bootstrap import restore_admin


def configure(monkeypatch):
    monkeypatch.setenv('ADMIN_USER', 'owner')
    monkeypatch.setenv('ADMIN_EMAIL', 'owner@example.test')
    monkeypatch.setenv('ADMIN_PASSWORD', 'test-password-123')


def test_admin_restored_idempotently_from_environment(app, db, monkeypatch):
    configure(monkeypatch)
    restore_admin(app)
    restore_admin(app)
    users = db.session.query(User).all()
    assert len(users) == 1
    assert users[0].is_admin and users[0].check_password('test-password-123')


def test_conflicting_registration_is_not_promoted(app, db, monkeypatch):
    configure(monkeypatch)
    stranger = User(username='owner', email='different@example.test', is_admin=False)
    stranger.set_password('another-password-123')
    db.session.add(stranger)
    db.session.commit()
    restore_admin(app)
    db.session.refresh(stranger)
    assert not stranger.is_admin
    assert stranger.check_password('another-password-123')


def test_incomplete_admin_environment_does_not_create_user(app, db, monkeypatch):
    configure(monkeypatch)
    monkeypatch.delenv('ADMIN_PASSWORD')
    restore_admin(app)
    assert db.session.query(User).count() == 0
