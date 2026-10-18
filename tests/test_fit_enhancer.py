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

    def test_enhance_ungrowable_device_info(self):
        try:
            from fit_tool.definition_message import DefinitionMessage
            from fit_tool.fit_file import FitFile
            from fit_tool.fit_file_header import FitFileHeader
            from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
            from fit_tool.profile.messages.file_id_message import FileIdMessage
            from fit_tool.profile.profile_type import FileType, Manufacturer
            from fit_tool.record import Record
        except ImportError:
            return  # Skip if fit-tool is unavailable

        file_id = FileIdMessage()
        file_id.type = FileType.ACTIVITY
        file_id.manufacturer = 255
        file_id.product = 999

        dev = DeviceInfoMessage()
        dev.manufacturer = 255
        dev.product = 999

        records = [
            Record.from_message(DefinitionMessage.from_data_message(file_id)),
            Record.from_message(file_id),
            Record.from_message(DefinitionMessage.from_data_message(dev)),
            Record.from_message(dev),
        ]
        rec_bytes = b"".join(r.to_bytes() for r in records)
        header = FitFileHeader(records_size=len(rec_bytes))
        fit = FitFile(header, records)

        with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
            fit.to_file(tmp.name)
            src_path = tmp.name

        enhancer = FitEnhancer(device_product_id=3927)
        out_path = enhancer.enhance(src_path)

        # Must not have fallen back to source path due to ungrowable error
        self.assertNotEqual(out_path, src_path)

        enhanced_fit = FitFile.from_file(out_path)
        found_dev = False
        found_file_id = False
        for r in enhanced_fit.records:
            if isinstance(r.message, DeviceInfoMessage):
                self.assertEqual(r.message.manufacturer, 1)
                self.assertEqual(r.message.product, 3927)
                found_dev = True
            elif isinstance(r.message, FileIdMessage):
                self.assertEqual(r.message.manufacturer, 1)
                self.assertEqual(r.message.product, 3927)
                found_file_id = True

        self.assertTrue(found_dev)
        self.assertTrue(found_file_id)

    def test_cleanup_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        self.assertTrue(Path(tmp_path).exists())
        FitEnhancer.cleanup_file(tmp_path)
        self.assertFalse(Path(tmp_path).exists())


if __name__ == "__main__":
    unittest.main()
