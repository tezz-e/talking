import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app, SERVER_API_TOKEN, ALLOWED_ORIGINS
from backend.models import Contact

class SecurityMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        from backend.main import db
        self.db = db
        self.test_contact = self.db.add_contact(Contact(name="Security Test User"))

    def tearDown(self):
        try:
            self.db.delete_contact(self.test_contact.id)
        except Exception:
            pass

    # ── 1. Foreign Origin Rejected ──
    def test_foreign_origin_rejected_on_post(self):
        res = self.client.post(
            "/api/watcher/start",
            headers={"Origin": "http://evil.com", "X-Talking-Token": SERVER_API_TOKEN},
            json={
                "contact_id": self.test_contact.id,
                "instagram_url": "https://www.instagram.com/direct/t/12345/",
            }
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden origin", res.json().get("detail", ""))

    def test_foreign_origin_rejected_on_get(self):
        res = self.client.get(
            "/api/watcher/status",
            headers={"Origin": "https://malicious-site.org"}
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden origin", res.json().get("detail", ""))

    def test_allowed_origin_accepted_on_get(self):
        res = self.client.get(
            "/api/watcher/status",
            headers={"Origin": "http://localhost:8000"}
        )
        self.assertEqual(res.status_code, 200)

    # ── 2. Missing & Invalid Token Rejected on Watcher Routes ──
    def test_missing_token_rejected_on_watcher_start(self):
        res = self.client.post(
            "/api/watcher/start",
            json={
                "contact_id": self.test_contact.id,
                "instagram_url": "https://www.instagram.com/direct/t/12345/",
            }
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid or missing X-Talking-Token", res.json().get("detail", ""))

    def test_missing_token_rejected_on_watcher_stop(self):
        res = self.client.post("/api/watcher/stop")
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid or missing X-Talking-Token", res.json().get("detail", ""))

    def test_missing_token_rejected_on_watcher_send(self):
        res = self.client.post("/api/watcher/send", json={"text": "Hello"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid or missing X-Talking-Token", res.json().get("detail", ""))

    def test_invalid_token_rejected(self):
        res = self.client.post(
            "/api/watcher/start",
            headers={"X-Talking-Token": "invalid_fake_token_value"},
            json={
                "contact_id": self.test_contact.id,
                "instagram_url": "https://www.instagram.com/direct/t/12345/",
            }
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid or missing X-Talking-Token", res.json().get("detail", ""))

    # ── 3. Valid Token Accepted ──
    def test_valid_token_accepted_on_watcher_start(self):
        with patch("backend.instagram_watcher.start_watcher") as mock_start:
            res = self.client.post(
                "/api/watcher/start",
                headers={"X-Talking-Token": SERVER_API_TOKEN},
                json={
                    "contact_id": self.test_contact.id,
                    "instagram_url": "https://www.instagram.com/direct/t/12345/",
                    "mood": "chill",
                    "full_auto": False
                }
            )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json()["status"], "started")
            mock_start.assert_called_once()

    def test_valid_token_accepted_on_watcher_stop(self):
        with patch("backend.instagram_watcher.stop_watcher") as mock_stop:
            res = self.client.post(
                "/api/watcher/stop",
                headers={"X-Talking-Token": SERVER_API_TOKEN}
            )
            self.assertEqual(res.status_code, 200)
            mock_stop.assert_called_once()

    # ── 4. Full Auto Protection ──
    def test_full_auto_rejected_without_env_flag(self):
        with patch.dict(os.environ, {"ALLOW_FULL_AUTO": "0"}, clear=False):
            res = self.client.post(
                "/api/watcher/start",
                headers={"X-Talking-Token": SERVER_API_TOKEN},
                json={
                    "contact_id": self.test_contact.id,
                    "instagram_url": "https://www.instagram.com/direct/t/12345/",
                    "full_auto": True,
                    "confirm_full_auto": True
                }
            )
            self.assertEqual(res.status_code, 403)
            self.assertIn("ALLOW_FULL_AUTO=1", res.json().get("detail", ""))

    def test_full_auto_rejected_without_confirm_field(self):
        with patch.dict(os.environ, {"ALLOW_FULL_AUTO": "1"}, clear=False):
            res = self.client.post(
                "/api/watcher/start",
                headers={"X-Talking-Token": SERVER_API_TOKEN},
                json={
                    "contact_id": self.test_contact.id,
                    "instagram_url": "https://www.instagram.com/direct/t/12345/",
                    "full_auto": True,
                    "confirm_full_auto": False
                }
            )
            self.assertEqual(res.status_code, 403)
            self.assertIn("confirm_full_auto", res.json().get("detail", ""))

    def test_full_auto_accepted_with_env_and_confirm(self):
        with patch.dict(os.environ, {"ALLOW_FULL_AUTO": "1"}, clear=False):
            with patch("backend.instagram_watcher.start_watcher") as mock_start:
                res = self.client.post(
                    "/api/watcher/start",
                    headers={"X-Talking-Token": SERVER_API_TOKEN},
                    json={
                        "contact_id": self.test_contact.id,
                        "instagram_url": "https://www.instagram.com/direct/t/12345/",
                        "full_auto": True,
                        "confirm_full_auto": True
                    }
                )
                self.assertEqual(res.status_code, 200)
                mock_start.assert_called_once()
                self.assertTrue(mock_start.call_args[1].get("full_auto"))

    # ── 5. Auth Token Endpoint ──
    def test_auth_token_endpoint_same_origin(self):
        res = self.client.get("/api/auth/token")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("token"), SERVER_API_TOKEN)

    def test_auth_token_endpoint_foreign_origin_rejected(self):
        res = self.client.get("/api/auth/token", headers={"Origin": "http://evil.com"})
        self.assertEqual(res.status_code, 403)

    # ── 6. Host Header & DNS Rebinding Protection ──
    def test_foreign_host_header_rejected(self):
        res = self.client.get("/api/watcher/status", headers={"Host": "attacker.com:8000"})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Forbidden host", res.json().get("detail", ""))

    def test_valid_host_header_accepted(self):
        res = self.client.get("/api/watcher/status", headers={"Host": "localhost:8000"})
        self.assertEqual(res.status_code, 200)

        res_ip = self.client.get("/api/watcher/status", headers={"Host": "127.0.0.1:8000"})
        self.assertEqual(res_ip.status_code, 200)

    # ── 7. Strict Production Allowed Origins ──
    def test_default_production_allowed_origins(self):
        from backend.main import get_allowed_origins
        with patch.dict(os.environ, {"ADDITIONAL_ALLOWED_ORIGINS": ""}, clear=False):
            origins = get_allowed_origins()
            self.assertEqual(sorted(origins), sorted(["http://localhost:8000", "http://127.0.0.1:8000"]))

    def test_additional_allowed_origins_env(self):
        from backend.main import get_allowed_origins
        with patch.dict(os.environ, {"ADDITIONAL_ALLOWED_ORIGINS": "http://localhost:9999,http://127.0.0.1:9999"}, clear=False):
            origins = get_allowed_origins()
            self.assertIn("http://localhost:9999", origins)
            self.assertIn("http://127.0.0.1:9999", origins)

if __name__ == "__main__":
    unittest.main()
