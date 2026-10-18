"""Unit tests for KarooClient and JWT decoding."""

import base64
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.karoo_client import KarooClient, decode_jwt_payload


class TestKarooClient(unittest.TestCase):
    def test_decode_jwt_payload(self):
        payload_data = {"sub": "user_12345", "name": "Cyclist", "exp": 1893456000}
        b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"eyJhbGciOiJIUzI1NiJ9.{b64}.signature"

        decoded = decode_jwt_payload(fake_jwt)
        self.assertEqual(decoded["sub"], "user_12345")
        self.assertEqual(decoded["name"], "Cyclist")

    def test_auth_token_initialization(self):
        payload_data = {"sub": "user_hammer_999"}
        b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64}.sig"

        client = KarooClient(auth_token=fake_jwt)
        self.assertEqual(client.user_id, "user_hammer_999")
        self.assertEqual(client.auth_token, fake_jwt)

    @patch("src.karoo_client.requests.Session")
    def test_login_success(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        payload_data = {"sub": "user_abc"}
        b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64}.sig"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": fake_jwt}
        mock_session.post.return_value = mock_resp

        client = KarooClient(email="rider@example.com", password="pass")
        client.session = mock_session

        self.assertTrue(client.login())
        self.assertEqual(client.user_id, "user_abc")
        self.assertEqual(client.auth_token, fake_jwt)

    @patch("src.karoo_client.requests.Session")
    def test_get_activities_standardization(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        payload_data = {"sub": "user_abc"}
        b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64}.sig"

        client = KarooClient(auth_token=fake_jwt)
        client.session = mock_session

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "ride_1",
                    "name": "Morning Gravel",
                    "startTime": "2026-10-12T08:00:00Z",
                    "distance": 45000.0,
                    "duration": 5400.0,
                },
                {
                    "id": "ride_2",
                    "title": "Evening Commute",
                    "createdAt": "2026-10-11T17:00:00Z",
                    "total_distance": 15000.0,
                    "movingTime": 2100.0,
                },
            ]
        }
        mock_session.get.return_value = mock_resp

        activities = client.get_activities(limit=5)
        self.assertEqual(len(activities), 2)
        self.assertEqual(activities[0]["id"], "ride_1")
        self.assertEqual(activities[0]["name"], "Morning Gravel")
        self.assertEqual(activities[0]["distance"], 45000.0)
        self.assertEqual(activities[1]["id"], "ride_2")
        self.assertEqual(activities[1]["name"], "Evening Commute")

    @patch("src.karoo_client.requests.Session")
    def test_get_activities_dict_metrics(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        payload_data = {"sub": "user_abc"}
        b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64}.sig"

        client = KarooClient(auth_token=fake_jwt)
        client.session = mock_session

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "ride_dict_1",
                    "name": {"value": "Mountain Loop"},
                    "startTime": {"iso": "2026-10-18T00:00:00Z"},
                    "distance": {"value": 52100.5, "unit": "meters"},
                    "duration": {"moving_time": 6400, "elapsed_time": 7100},
                }
            ]
        }
        mock_session.get.return_value = mock_resp

        activities = client.get_activities(limit=1)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0]["id"], "ride_dict_1")
        self.assertEqual(activities[0]["name"], "Mountain Loop")
        self.assertEqual(activities[0]["date"], "2026-10-18T00:00:00Z")
        self.assertEqual(activities[0]["distance"], 52100.5)
        self.assertEqual(activities[0]["duration"], 6400.0)

    @patch("src.karoo_client.requests.Session")
    def test_download_activity_fit(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        payload_data = {"sub": "user_abc"}
        b64 = base64.urlsafe_b64encode(json.dumps(payload_data).encode("utf-8")).decode("utf-8").rstrip("=")
        fake_jwt = f"header.{b64}.sig"

        client = KarooClient(auth_token=fake_jwt)
        client.session = mock_session

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b".FIT_BINARY_DATA"]
        mock_resp.__enter__.return_value = mock_resp
        mock_session.get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = client.download_activity_fit({"id": "ride_xyz"}, output_dir=tmp_dir)
            self.assertTrue(path.endswith("karoo_ride_xyz.fit"))
            with open(path, "rb") as f:
                content = f.read()
            self.assertEqual(content, b".FIT_BINARY_DATA")


if __name__ == "__main__":
    unittest.main()
