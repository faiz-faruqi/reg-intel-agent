"""Tests for the time-limited access code feature (src.db storage + auth routes)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.config import settings
from src.main import app

client = TestClient(app)


def _mock_conn(fetchone_return):
    """Build a MagicMock connection whose cursor's fetchone() returns the given value."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_return
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


# ---------------------------------------------------------------------------
# src.db — generate_access_code / verify_access_code
# ---------------------------------------------------------------------------

class TestAccessCodeStore:
    @patch("src.db.get_conn")
    def test_generate_returns_code_and_expiry(self, mock_get_conn):
        expires = datetime(2026, 1, 8, tzinfo=timezone.utc)
        conn, _cur = _mock_conn((expires,))
        mock_get_conn.return_value.__enter__.return_value = conn

        from src.db import generate_access_code

        code, expires_at = generate_access_code(168)

        assert isinstance(code, str) and len(code) > 0
        assert expires_at == expires.isoformat()

    @patch("src.db.get_conn")
    def test_verify_matching_code_is_valid(self, mock_get_conn):
        conn, _cur = _mock_conn(("current-code",))
        mock_get_conn.return_value.__enter__.return_value = conn

        from src.db import verify_access_code

        assert verify_access_code("current-code") is True

    @patch("src.db.get_conn")
    def test_verify_wrong_code_is_invalid(self, mock_get_conn):
        conn, _cur = _mock_conn(("current-code",))
        mock_get_conn.return_value.__enter__.return_value = conn

        from src.db import verify_access_code

        assert verify_access_code("some-other-code") is False

    @patch("src.db.get_conn")
    def test_verify_no_active_or_expired_code_is_invalid(self, mock_get_conn):
        # WHERE expires_at > now() excludes expired rows, so an expired code
        # looks identical to "no code has ever been generated" — no match.
        conn, _cur = _mock_conn(None)
        mock_get_conn.return_value.__enter__.return_value = conn

        from src.db import verify_access_code

        assert verify_access_code("anything") is False

    def test_verify_empty_code_short_circuits_without_a_db_call(self):
        from src.db import verify_access_code

        with patch("src.db.get_conn") as mock_get_conn:
            assert verify_access_code("") is False
            mock_get_conn.assert_not_called()

    @patch("src.db.get_conn", side_effect=Exception("db unreachable"))
    def test_verify_fails_closed_on_db_error(self, _mock_get_conn):
        """The one non-obvious rule: an unreachable DB must deny sign-in, not allow it."""
        from src.db import verify_access_code

        assert verify_access_code("anything") is False


# ---------------------------------------------------------------------------
# API — POST /auth/generate-code (admin-only)
# ---------------------------------------------------------------------------

class TestGenerateCodeEndpoint:
    def test_503_when_admin_key_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_KEY", "")
        response = client.post(
            "/auth/generate-code", json={}, headers={"X-Admin-Key": "whatever"}
        )
        assert response.status_code == 503

    def test_403_when_admin_key_wrong(self, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_KEY", "correct-key")
        response = client.post(
            "/auth/generate-code", json={}, headers={"X-Admin-Key": "wrong-key"}
        )
        assert response.status_code == 403

    @patch("src.db.generate_access_code", return_value=("k_abc123", "2026-01-08T00:00:00+00:00"))
    def test_generates_code_with_valid_admin_key(self, mock_gen, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_KEY", "correct-key")
        response = client.post(
            "/auth/generate-code",
            json={"ttl_hours": 24},
            headers={"X-Admin-Key": "correct-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "code": "k_abc123",
            "expires_at": "2026-01-08T00:00:00+00:00",
            "ttl_hours": 24,
        }
        mock_gen.assert_called_once_with(24)

    @patch("src.db.generate_access_code", return_value=("k_default", "2026-01-15T00:00:00+00:00"))
    def test_defaults_to_168_hour_ttl(self, mock_gen, monkeypatch):
        monkeypatch.setattr(settings, "ADMIN_KEY", "correct-key")
        response = client.post(
            "/auth/generate-code", json={}, headers={"X-Admin-Key": "correct-key"}
        )
        assert response.status_code == 200
        mock_gen.assert_called_once_with(168)


# ---------------------------------------------------------------------------
# API — POST /auth/signin now checks the DB-backed code, not a fixed value
# ---------------------------------------------------------------------------

class TestSignInAccessCode:
    @patch("src.db.verify_access_code", return_value=True)
    def test_valid_code_signs_in(self, mock_verify):
        response = client.post(
            "/auth/signin",
            json={
                "username": settings.DEMO_USERNAME,
                "password": settings.DEMO_PASSWORD,
                "access_code": "current-code",
            },
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True
        mock_verify.assert_called_once_with("current-code")

    @patch("src.db.verify_access_code", return_value=False)
    def test_expired_or_wrong_code_rejected(self, _mock_verify):
        response = client.post(
            "/auth/signin",
            json={
                "username": settings.DEMO_USERNAME,
                "password": settings.DEMO_PASSWORD,
                "access_code": "stale-code",
            },
        )
        assert response.status_code == 401
        assert response.json()["ok"] is False
