"""Unit tests for SyncStore SQLite storage."""

import tempfile
import unittest
from pathlib import Path

from src.sync_store import SyncStore


class TestSyncStore(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_sync.db"
        self.store = SyncStore(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_record_and_check_is_synced(self):
        self.assertFalse(self.store.is_synced("ride_123"))

        self.store.record_activity(
            karoo_id="ride_123",
            name="Epic Gravel Ride",
            activity_date="2026-10-12T10:00:00Z",
            status="UPLOADED",
            notes="Device: Edge 1040",
        )

        self.assertTrue(self.store.is_synced("ride_123"))

    def test_get_synced_ids(self):
        self.store.record_activity("r1", "Ride 1", "2026-10-10", "UPLOADED")
        self.store.record_activity("r2", "Ride 2", "2026-10-11", "SKIPPED_DUPLICATE")

        ids = self.store.get_synced_ids()
        self.assertEqual(ids, {"r1", "r2"})

    def test_get_stats(self):
        self.store.record_activity("r1", "Ride 1", "2026-10-10", "UPLOADED")
        self.store.record_activity("r2", "Ride 2", "2026-10-11", "SKIPPED_DUPLICATE")
        self.store.record_activity("r3", "Ride 3", "2026-10-12", "FAILED")

        stats = self.store.get_stats()
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["uploaded"], 1)
        self.assertEqual(stats["skipped_duplicate"], 1)
        self.assertEqual(stats["failed"], 1)


if __name__ == "__main__":
    unittest.main()
