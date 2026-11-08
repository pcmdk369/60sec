import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.main import _password_matches, _issue_token, _verify_token, app, health


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "ADMIN_USERNAME": "LocalAdmin",
            "SESSION_SECRET": "unit-test-secret-that-is-at-least-32-bytes-long",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_password_hash_verifies_and_rejects_wrong_password(self):
        import hashlib
        salt = b"0123456789abcdef"
        rounds = 200_000
        digest = hashlib.pbkdf2_hmac("sha256", b"correct horse battery", salt, rounds).hex()
        encoded = f"pbkdf2_sha256${rounds}${salt.hex()}${digest}"
        self.assertTrue(_password_matches("correct horse battery", encoded))
        self.assertFalse(_password_matches("wrong password", encoded))
        self.assertFalse(_password_matches("correct horse battery", "invalid"))

    def test_signed_session_round_trip(self):
        token = _issue_token("LocalAdmin")
        payload = _verify_token(token)
        self.assertEqual(payload["sub"], "LocalAdmin")

    def test_tampered_session_is_rejected(self):
        token = _issue_token("LocalAdmin")
        body, signature = token.split(".", 1)
        altered = ("A" if signature[0] != "A" else "B") + signature[1:]
        with self.assertRaises(HTTPException) as error:
            _verify_token(body + "." + altered)
        self.assertEqual(error.exception.status_code, 401)

    def test_expected_api_routes_exist(self):
        paths = {route.path for route in app.routes}
        expected = {
            "/health", "/api/auth/login", "/api/auth/session",
            "/api/jobs", "/api/jobs/{job_id}", "/api/jobs/{job_id}/download",
        }
        self.assertTrue(expected.issubset(paths), expected - paths)

    def test_health_does_not_require_external_llm(self):
        with patch.dict(os.environ, {"LLM_API_KEY": "", "LLM_API_URL": "", "LLM_MODEL_ID": ""}):
            result = health()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["emergency_llm_configured"])


if __name__ == "__main__":
    unittest.main()
