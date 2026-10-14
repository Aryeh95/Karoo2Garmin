"""Unit tests for SyncEngine orchestration in Karoo2Garmin."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.config import Config
from src.sync_engine import SyncEngine
from src.sync_store import SyncStore


class TestSyncEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_engine.db"
        self.store = SyncStore(self.db_path)

        self.config = Config(
            karoo_email="test@karoo.com",
            karoo_password="pass",
            karoo_auth_token=None,
            garmin_username=None,
            garmin_password=None,
            garmin_token_dir=Path(self.temp_dir.name),
            data_dir=Path(self.temp_dir.name),
            check_duplicates=False,
            spoof_garmin_device=False,
        )

        self.mock_karoo = MagicMock()
        self.mock_garmin = MagicMock()
        self.mock_enhancer = MagicMock()

        self.engine = SyncEngine(
            config=self.config,
            karoo=self.mock_karoo,
            garmin=self.mock_garmin,
            enhancer=self.mock_enhancer,
            store=self.store,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sync_latest_processes_only_single_newest_activity(self):
        self.mock_karoo.get_activities.return_value = [
            {"id": "act_old", "name": "Old Ride", "date": "2026-01-01T10:00:00Z"},
            {"id": "act_newest", "name": "Latest Ride", "date": "2026-10-12T10:00:00Z"},
            {"id": "act_mid", "name": "Mid Ride", "date": "2026-06-01T10:00:00Z"},
        ]
        self.mock_karoo.download_activity_fit.return_value = "/tmp/fake_karoo.fit"
        self.mock_enhancer.enhance.return_value = "/tmp/fake_enh.fit"
        self.mock_garmin.upload_activity.return_value = {"status": "uploaded"}

        stats = self.engine.run_sync(sync_latest=True)

        self.assertEqual(stats["uploaded"], 1)
        self.assertEqual(stats["total_found"], 1)

        self.assertTrue(self.store.is_synced("act_newest"))
        self.assertFalse(self.store.is_synced("act_mid"))
        self.assertFalse(self.store.is_synced("act_old"))

    def test_duplicate_on_garmin_skips_upload(self):
        self.config.check_duplicates = True
        self.mock_garmin.check_duplicate.return_value = True
        self.mock_karoo.get_activities.return_value = [
            {"id": "act_dup", "name": "Already On Garmin", "date": "2026-10-12T10:00:00Z"},
        ]

        stats = self.engine.run_sync(sync_latest=True)

        self.assertEqual(stats["skipped_duplicate"], 1)
        self.assertEqual(stats["uploaded"], 0)
        self.assertTrue(self.store.is_synced("act_dup"))
        self.mock_garmin.upload_activity.assert_not_called()


if __name__ == "__main__":
    unittest.main()
