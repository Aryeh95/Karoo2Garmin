"""Unit tests for GarminClient datetime parsing and formatting."""

import unittest
from datetime import datetime, timezone

from src.garmin_client import format_local_datetime, parse_activity_datetime


class TestGarminClientUtils(unittest.TestCase):
    def test_parse_iso_string(self):
        dt = parse_activity_datetime("2026-10-12T14:30:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 12)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_numeric_epoch(self):
        # 1700000000 = 2023-11-14T22:13:20Z
        dt = parse_activity_datetime(1700000000)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2023)

        # Milliseconds
        dt_ms = parse_activity_datetime(1700000000000)
        self.assertIsNotNone(dt_ms)
        self.assertEqual(dt_ms.year, 2023)

    def test_parse_dict_datetime(self):
        dt = parse_activity_datetime({"iso": "2026-10-18T10:00:00Z"})
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 18)

    def test_format_local_datetime(self):
        res = format_local_datetime("2026-10-12T14:30:00Z")
        self.assertTrue(len(res) > 0)
        self.assertNotIn("T", res)


if __name__ == "__main__":
    unittest.main()
