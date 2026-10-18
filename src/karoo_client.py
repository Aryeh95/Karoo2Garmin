"""Client for communicating with Hammerhead Karoo cloud services."""

import base64
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests.exceptions import RequestException
except ImportError:
    requests = None  # type: ignore

    class RequestException(Exception):  # type: ignore
        pass

try:
    import jwt
except ImportError:
    jwt = None

logger = logging.getLogger(__name__)


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """Decode JWT payload without verifying signature (works with or without PyJWT)."""
    if jwt is not None:
        try:
            return jwt.decode(token, algorithms=["HS256", "RS256"], options={"verify_signature": False})
        except Exception:
            pass

    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid JWT token format")

    payload_b64 = parts[1]
    # Pad to base64 length multiple of 4
    rem = len(payload_b64) % 4
    if rem > 0:
        payload_b64 += "=" * (4 - rem)

    decoded = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
    return json.loads(decoded.decode("utf-8"))


def _extract_numeric(val: Any) -> float:
    """Safely extract a float from a number, string, or dictionary."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for k in (
            "value",
            "moving_time",
            "movingTime",
            "elapsed_time",
            "elapsedTime",
            "total",
            "seconds",
            "duration",
            "distance",
        ):
            if k in val and val[k] is not None:
                try:
                    return float(val[k])
                except (ValueError, TypeError):
                    pass
        for v in val.values():
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _extract_date(act: Dict[str, Any]) -> str:
    """Safely extract date string or timestamp representation from activity dict."""
    for k in ("startTime", "start_time", "date", "createdAt", "created_at", "timestamp"):
        v = act.get(k)
        if not v:
            continue
        if isinstance(v, str):
            return v
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, dict):
            for sub_k in ("iso", "startTime", "start_time", "value", "timestamp", "formatted", "date"):
                sub_v = v.get(sub_k)
                if sub_v:
                    return str(sub_v)
    return ""


class KarooClient:
    """Handles authentication and activity downloading from Hammerhead Karoo."""

    AUTH_URL = "https://dashboard.hammerhead.io/v1/auth/token"
    DASHBOARD_BASE_URL = "https://dashboard.hammerhead.io/v1"
    API_BASE_URL = "https://api.hammerhead.io"

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        auth_token: Optional[str] = None,
    ):
        self.email = email
        self.password = password
        self.auth_token = auth_token
        self.user_id: Optional[str] = None
        self.session = requests.Session() if requests else None

        if self.auth_token:
            self._extract_user_id()

    def _extract_user_id(self) -> None:
        """Extract user ID (sub) from JWT access token."""
        if not self.auth_token:
            return
        try:
            payload = decode_jwt_payload(self.auth_token)
            self.user_id = payload.get("sub") or payload.get("user_id") or payload.get("uid")
            if self.user_id:
                logger.info("Identified Hammerhead user ID from token: %s", self.user_id)
        except Exception as exc:
            logger.warning("Could not decode user ID from auth token: %s", exc)

    def login(self) -> bool:
        """Authenticate with Hammerhead Dashboard and obtain access token."""
        if self.auth_token and self.user_id:
            return True

        if not self.email or not self.password:
            raise ValueError("Email and password or valid auth_token required for Karoo authentication")

        logger.info("Logging into Hammerhead Dashboard as %s...", self.email)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "grant_type": "password",
            "username": self.email,
            "password": self.password,
        }

        try:
            response = self.session.post(self.AUTH_URL, headers=headers, data=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            token = data.get("access_token")
            if not token:
                raise RuntimeError(f"Authentication response did not contain access_token: {data}")

            self.auth_token = token
            self._extract_user_id()

            if not self.user_id:
                raise RuntimeError("Could not determine user ID from Hammerhead authentication token")

            logger.info("Successfully authenticated with Hammerhead Karoo (User ID: %s)", self.user_id)
            return True

        except RequestException as exc:
            logger.exception("Network error during Hammerhead authentication: %s", exc)
            raise RuntimeError(f"Hammerhead authentication failed: {exc}") from exc

    def ensure_authenticated(self) -> None:
        """Ensure an active access token and user ID are present."""
        if not self.auth_token or not self.user_id:
            self.login()

    def get_activities(self, limit: int = 10, page: int = 1) -> List[Dict[str, Any]]:
        """Fetch list of user activities from Hammerhead Karoo.

        Returns:
            List of standardized activity dictionaries containing:
            - id: str
            - name: str
            - date: str (ISO timestamp)
            - distance: float (meters)
            - duration: float (seconds)
        """
        self.ensure_authenticated()

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Accept": "application/json",
            "User-Agent": "Karoo2Garmin/1.0",
        }

        # Try dashboard endpoint first, fallback to api endpoint if needed
        urls = [
            f"{self.DASHBOARD_BASE_URL}/users/{self.user_id}/activities",
            f"{self.API_BASE_URL}/users/{self.user_id}/activities",
        ]

        last_error = None
        for url in urls:
            try:
                logger.debug("Requesting activities from %s (page: %d)", url, page)
                response = self.session.get(url, headers=headers, params={"page": page, "limit": limit}, timeout=30)

                if response.status_code == 401:
                    logger.warning("Hammerhead token expired, attempting re-authentication...")
                    self.login()
                    headers["Authorization"] = f"Bearer {self.auth_token}"
                    response = self.session.get(url, headers=headers, params={"page": page, "limit": limit}, timeout=30)

                response.raise_for_status()
                data = response.json()

                raw_list = []
                if isinstance(data, list):
                    raw_list = data
                elif isinstance(data, dict):
                    raw_list = data.get("data") or data.get("activities") or data.get("items") or []

                standardized = []
                for act in raw_list:
                    act_id = str(act.get("id") or act.get("activityId") or act.get("_id") or "")
                    if not act_id:
                        continue

                    name_val = act.get("name") or act.get("title")
                    if isinstance(name_val, dict):
                        name = str(name_val.get("value") or name_val.get("text") or "Karoo Ride")
                    elif name_val:
                        name = str(name_val)
                    else:
                        name = "Karoo Ride"

                    date_val = _extract_date(act)
                    distance = _extract_numeric(
                        act.get("distance")
                        or act.get("total_distance")
                        or act.get("totalDistance")
                    )
                    duration = _extract_numeric(
                        act.get("duration")
                        or act.get("movingTime")
                        or act.get("moving_time")
                        or act.get("elapsedTime")
                        or act.get("elapsed_time")
                    )

                    standardized.append({
                        "id": act_id,
                        "name": name,
                        "date": date_val,
                        "distance": distance,
                        "duration": duration,
                        "raw": act,
                    })

                logger.info("Found %d activities on Hammerhead Karoo.", len(standardized))
                return standardized[:limit]

            except RequestException as exc:
                last_error = exc
                logger.debug("Attempt with %s failed: %s", url, exc)
                continue

        logger.error("Failed to retrieve activities from Hammerhead: %s", last_error)
        raise RuntimeError(f"Failed to fetch activities from Hammerhead: {last_error}")

    def download_activity_fit(self, activity: Dict[str, Any], output_dir: Optional[str] = None) -> str:
        """Download original FIT file for an activity from Hammerhead Dashboard.

        Args:
            activity: Standardized activity dict containing 'id'
            output_dir: Optional destination folder. Defaults to system temp.

        Returns:
            Path to downloaded binary FIT file on local filesystem.
        """
        self.ensure_authenticated()
        act_id = activity["id"]

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "User-Agent": "Karoo2Garmin/1.0",
        }

        urls = [
            f"{self.DASHBOARD_BASE_URL}/users/{self.user_id}/activities/{act_id}/file?format=fit",
            f"{self.API_BASE_URL}/users/{self.user_id}/activities/{act_id}/file?format=fit",
            f"{self.DASHBOARD_BASE_URL}/users/{self.user_id}/activities/{act_id}/fit",
        ]

        dest_dir = output_dir or tempfile.gettempdir()
        dest_path = os.path.join(dest_dir, f"karoo_{act_id}.fit")

        last_error = None
        for url in urls:
            try:
                logger.info("Downloading FIT file for Karoo activity %s from %s...", act_id, url)
                with self.session.get(url, headers=headers, stream=True, timeout=60) as resp:
                    if resp.status_code == 401:
                        self.login()
                        headers["Authorization"] = f"Bearer {self.auth_token}"
                        resp = self.session.get(url, headers=headers, stream=True, timeout=60)

                    resp.raise_for_status()

                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)

                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    logger.info("Downloaded %d bytes to %s", os.path.getsize(dest_path), dest_path)
                    return dest_path

            except RequestException as exc:
                last_error = exc
                logger.debug("FIT download attempt at %s failed: %s", url, exc)
                continue

        raise RuntimeError(f"Could not download FIT file for activity {act_id}: {last_error}")
