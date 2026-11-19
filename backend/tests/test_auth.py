import hashlib

from fastapi.testclient import TestClient

from app.main import app, _issue_token, _password_matches, _verify_token


def _hash_password(password: str) -> str:
    salt = b"test-salt-16byte"
    rounds = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds).hex()
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest}"


def test_password_hash_verification():
    encoded = _hash_password("correct horse battery staple")
    assert _password_matches("correct horse battery staple", encoded)
    assert not _password_matches("wrong password", encoded)
    assert not _password_matches("anything", "unsupported$scheme")


def test_signed_session_token_round_trip(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "Admin")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-that-is-at-least-32-bytes")
    token = _issue_token("Admin")
    assert _verify_token(token)["sub"] == "Admin"


def test_tampered_token_is_rejected(monkeypatch):
    from fastapi import HTTPException
    import pytest

    monkeypatch.setenv("ADMIN_USERNAME", "Admin")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-that-is-at-least-32-bytes")
    token = _issue_token("Admin")
    with pytest.raises(HTTPException) as error:
        _verify_token(token + "tampered")
    assert error.value.status_code == 401


def test_health_endpoint_is_public():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_job_status_requires_auth(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-that-is-at-least-32-bytes")
    response = TestClient(app).get("/api/jobs/nonexistent")
    assert response.status_code == 401


def test_login_issues_token(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "Admin")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _hash_password("correct horse battery staple"))
    monkeypatch.setenv("SESSION_SECRET", "test-secret-that-is-at-least-32-bytes")
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"username": "Admin", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    session = client.get(
        "/api/auth/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert session.status_code == 200
    assert session.json()["authenticated"] is True
