"""FIT file device enhancer to enable Garmin Physio TrueUp and training metrics for Karoo rides."""

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _calc_np(power_values: List[float]) -> float:
    """Calculate Normalized Power (NP): 4th power average followed by 4th root."""
    if not power_values:
        return 0.0
    avg_4th = sum(p**4 for p in power_values) / len(power_values)
    return avg_4th**0.25


def _safe_set(obj: object, attr: str, val: object) -> None:
    """Set attribute on object safely ignoring missing attributes."""
    try:
        setattr(obj, attr, val)
    except Exception:
        pass


class FitEnhancer:
    """Modifies Karoo FIT file headers and device signatures to unlock Garmin training load/effect."""

    def __init__(
        self,
        spoof_device: bool = True,
        device_product_id: int = 3927,  # Garmin Edge 1040 (default), 4024 for Edge 840
        software_version: float = 27.10,
        athlete_ftp: float = 0.0,
    ):
        self.spoof_device = spoof_device
        self.device_product_id = device_product_id
        self.software_version = software_version
        self.athlete_ftp = athlete_ftp

    def enhance(self, input_path: str, output_path: Optional[str] = None) -> str:
        """Enhance a Karoo FIT file with Garmin Edge device signatures.

        Preserves:
            - Real-world GPS trackpoints and coordinates
            - Barometric elevation and temperatures
            - ANT+ / Bluetooth sensor pairings (HR monitors, power meters, radar)
            - Electronic gear shifting data (SRAM AXS, Shimano Di2)
            - Sport / SubSport classification (Road, Gravel, MTB, Indoor)

        Args:
            input_path: Path to the original Karoo FIT file.
            output_path: Optional destination path. If not provided, a temp file is used.

        Returns:
            Path to the output FIT file (modified if enabled, or original if bypassed).
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Source FIT file not found: {input_path}")

        if not self.spoof_device:
            logger.info("Device spoofing disabled; using original Karoo FIT file.")
            return input_path

        try:
            from fit_tool.fit_file import FitFile
            from fit_tool.profile.messages.file_id_message import FileIdMessage
            from fit_tool.profile.messages.file_creator_message import FileCreatorMessage
            from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
            from fit_tool.profile.messages.sport_message import SportMessage
            from fit_tool.profile.messages.record_message import RecordMessage
            from fit_tool.profile.messages.lap_message import LapMessage
            from fit_tool.profile.messages.session_message import SessionMessage
            from fit_tool.profile.profile_type import (
                FileType,
                Manufacturer,
                Sport,
                SubSport,
                Intensity,
                SessionTrigger,
            )
        except ImportError as exc:
            logger.warning(
                "fit-tool library not available (%s); uploading original file without spoofing.",
                exc,
            )
            return input_path

        dest_path = output_path or os.path.join(
            tempfile.gettempdir(), f"enhanced_{os.path.basename(input_path)}"
        )

        logger.info(
            "Patching Karoo FIT file %s -> Garmin Edge (Product ID %d, SW %.2f)...",
            os.path.basename(input_path),
            self.device_product_id,
            self.software_version,
        )

        try:
            with open(input_path, "rb") as f:
                raw_bytes = f.read()

            fit_file = FitFile.from_bytes(raw_bytes, check_crc=False)

            cadence_vals: List[float] = []
            power_vals: List[float] = []
            hr_vals: List[float] = []
            all_cadence: List[float] = []
            all_power: List[float] = []
            all_hr: List[float] = []

            primary_device_patched = False

            for record in fit_file.records:
                msg = record.message
                msg_type = type(msg)

                # 1. FileId: Spoof file creator as Garmin Edge
                if msg_type is FileIdMessage:
                    msg.type = FileType.ACTIVITY
                    msg.manufacturer = (
                        Manufacturer.GARMIN.value
                        if hasattr(Manufacturer.GARMIN, "value")
                        else 1
                    )
                    msg.product = self.device_product_id
                    continue

                if msg_type is FileCreatorMessage:
                    continue

                # 2. DeviceInfo: Spoof primary device only, preserving external ANT+/BLE sensors & SRAM AXS
                if msg_type is DeviceInfoMessage:
                    dev_index = getattr(msg, "device_index", None)
                    # device_index 0 is the primary recording unit (Karoo head unit)
                    if dev_index in (0, None) and not primary_device_patched:
                        msg.manufacturer = (
                            Manufacturer.GARMIN.value
                            if hasattr(Manufacturer.GARMIN, "value")
                            else 1
                        )
                        msg.product = self.device_product_id
                        msg.software_version = self.software_version
                        primary_device_patched = True
                    continue

                # 3. Sport: Preserve Karoo's sport and sub_sport (do NOT force Virtual Activity!)
                if msg_type is SportMessage:
                    if not getattr(msg, "sport", None):
                        msg.sport = Sport.CYCLING
                    continue

                # 4. Records: Collect metrics while preserving GPS and sensor data
                if msg_type is RecordMessage:
                    c = getattr(msg, "cadence", None)
                    if c and c > 0:
                        cadence_vals.append(float(c))
                        all_cadence.append(float(c))

                    p = getattr(msg, "power", None)
                    if p and p > 0:
                        power_vals.append(float(p))
                        all_power.append(float(p))

                    hr = getattr(msg, "heart_rate", None)
                    if hr and hr > 0:
                        hr_vals.append(float(hr))
                        all_hr.append(float(hr))
                    continue

                # 5. Lap: Fill intensity and averages if missing
                if msg_type is LapMessage:
                    _safe_set(msg, "intensity", Intensity.ACTIVE)
                    if not getattr(msg, "avg_cadence", None) and cadence_vals:
                        _safe_set(msg, "avg_cadence", round(sum(cadence_vals) / len(cadence_vals)))
                    if not getattr(msg, "avg_power", None) and power_vals:
                        _safe_set(msg, "avg_power", round(sum(power_vals) / len(power_vals)))
                    if not getattr(msg, "max_power", None) and power_vals:
                        _safe_set(msg, "max_power", round(max(power_vals)))
                    if not getattr(msg, "avg_heart_rate", None) and hr_vals:
                        _safe_set(msg, "avg_heart_rate", round(sum(hr_vals) / len(hr_vals)))
                    if not getattr(msg, "max_heart_rate", None) and hr_vals:
                        _safe_set(msg, "max_heart_rate", round(max(hr_vals)))
                    cadence_vals, power_vals, hr_vals = [], [], []
                    continue

                # 6. Session: Ensure sport & calculate training metrics
                if msg_type is SessionMessage:
                    if not getattr(msg, "sport", None):
                        msg.sport = Sport.CYCLING
                    _safe_set(msg, "trigger", SessionTrigger.ACTIVITY_END)

                    if not getattr(msg, "avg_cadence", None) and all_cadence:
                        _safe_set(msg, "avg_cadence", round(sum(all_cadence) / len(all_cadence)))
                    if not getattr(msg, "avg_power", None) and all_power:
                        avg_p = sum(all_power) / len(all_power)
                        _safe_set(msg, "avg_power", round(avg_p))
                    if not getattr(msg, "max_power", None) and all_power:
                        _safe_set(msg, "max_power", round(max(all_power)))
                    if not getattr(msg, "avg_heart_rate", None) and all_hr:
                        _safe_set(msg, "avg_heart_rate", round(sum(all_hr) / len(all_hr)))
                    if not getattr(msg, "max_heart_rate", None) and all_hr:
                        _safe_set(msg, "max_heart_rate", round(max(all_hr)))

                    # Total work (Joules = avg_power * timer_seconds)
                    timer_sec = getattr(msg, "total_timer_time", None) or getattr(msg, "total_elapsed_time", None)
                    avg_p = getattr(msg, "avg_power", None)
                    if avg_p and timer_sec and avg_p > 0 and timer_sec > 0:
                        _safe_set(msg, "total_work", int(avg_p * timer_sec))

                    # Normalized Power, IF, and TSS if FTP provided
                    if self.athlete_ftp > 0 and all_power:
                        np_val = _calc_np(all_power)
                        intensity_factor = np_val / self.athlete_ftp
                        _safe_set(msg, "normalized_power", round(np_val))
                        _safe_set(msg, "intensity_factor", round(intensity_factor, 3))
                        if timer_sec and timer_sec > 0:
                            tss = (timer_sec * np_val * intensity_factor) / (self.athlete_ftp * 3600) * 100
                            _safe_set(msg, "training_stress_score", round(tss))
                    continue

            fit_file.crc = None  # Force CRC recalculation on save
            fit_file.to_file(dest_path)
            logger.info("Successfully enhanced Karoo FIT file saved to %s", dest_path)
            return dest_path

        except Exception as exc:
            logger.exception("Failed to modify FIT file: %s. Using original file.", exc)
            return input_path

    @staticmethod
    def cleanup_file(path: Optional[str]) -> None:
        """Safely delete a temporary file."""
        if not path:
            return
        try:
            p = Path(path)
            if p.exists() and p.is_file():
                p.unlink()
                logger.debug("Cleaned up temporary file: %s", path)
        except OSError as exc:
            logger.warning("Could not delete temporary file %s: %s", path, exc)
