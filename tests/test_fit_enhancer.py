"""Unit tests for FitEnhancer in Karoo2Garmin."""

import tempfile
import unittest
from pathlib import Path

from src.fit_enhancer import FitEnhancer, _calc_np


class TestFitEnhancer(unittest.TestCase):
    def test_calc_np_empty(self):
        self.assertEqual(_calc_np([]), 0.0)

    def test_calc_np_constant(self):
        powers = [220.0] * 50
        self.assertAlmostEqual(_calc_np(powers), 220.0, places=1)

    def test_calc_np_variable(self):
        powers = [120.0, 320.0] * 50
        self.assertGreater(_calc_np(powers), 220.0)

    def test_disabled_spoofing_returns_original_path(self):
        enhancer = FitEnhancer(spoof_device=False)
        with tempfile.NamedTemporaryFile(suffix=".fit") as tmp:
            result = enhancer.enhance(tmp.name)
            self.assertEqual(result, tmp.name)

    def test_nonexistent_file_raises_error(self):
        enhancer = FitEnhancer()
        with self.assertRaises(FileNotFoundError):
            enhancer.enhance("/nonexistent/path/to/ride.fit")

    def test_cleanup_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        self.assertTrue(Path(tmp_path).exists())
        FitEnhancer.cleanup_file(tmp_path)
        self.assertFalse(Path(tmp_path).exists())


if __name__ == "__main__":
    unittest.main()
