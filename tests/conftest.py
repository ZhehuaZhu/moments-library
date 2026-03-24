from __future__ import annotations

import shutil
import tempfile

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture()
def app():
    upload_root = tempfile.mkdtemp()
    app = create_app(
        {
            "TESTING": True,
            "WTF_CSRF_ENABLED": False,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "UPLOAD_FOLDER": upload_root,
        }
    )

    with app.app_context():
        db.create_all()
        admin = User(
            username="admin",
            password_hash=generate_password_hash("password123"),
            is_admin=True,
        )
        db.session.add(admin)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()

    shutil.rmtree(upload_root, ignore_errors=True)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    response = client.post(
        "/login",
        data={"username": "admin", "password": "password123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return client
