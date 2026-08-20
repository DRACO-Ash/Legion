"""Configuration and credential loading.

Read all config from the environment (never a committed file). Real secret
values never enter the repository, the image, or any log.

UDL credentials specifically: env vars are the production/App-Store path.
A local-dev-only fallback reads ~/.config/phase_offset/credentials.ini,
section [udl], matching the convention already used by Ash's Script-mode
tools (spacetrack_geo_monitor.py and siblings) - so this app and those
scripts can share one credentials file on a workstation. That file is never
present inside the deployed container; the fallback simply does not fire
there because it does not exist.
"""

from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("udl_tactics_app.config")

CRED_PATH: Path = Path.home() / ".config" / "phase_offset" / "credentials.ini"


def _load_credentials_ini(section: str = "udl") -> tuple[str, str] | None:
    """Read (username, password) from the shared credentials.ini, or None.

    Never prompts interactively: this runs inside a server process with no
    TTY. A missing file or section is a normal, silent miss here; the caller
    decides whether that is fatal.
    """
    parser = configparser.ConfigParser(interpolation=None)
    try:
        found = parser.read(CRED_PATH, encoding="utf-8")
    except (OSError, configparser.Error) as exc:
        logger.warning("Could not read credentials file: %s", exc)
        return None
    if found and parser.has_section(section):
        username = parser.get(section, "username", fallback="").strip()
        password = parser.get(section, "password", fallback="")
        if username and password:
            logger.info(
                "UDL credentials loaded from credentials.ini (section [%s])", section
            )
            return username, password
        logger.warning("credentials.ini section [%s] present but incomplete", section)
    return None


def _strip_invisible(value: str) -> str:
    """Strip surrounding quotes/whitespace/control chars from a pasted env value."""
    return value.strip().strip('"').strip("'")


@dataclass(frozen=True)
class Settings:
    port: int
    allowed_origin: str
    team_token: str | None
    udl_base_url: str
    udl_username: str | None
    udl_password: str | None
    udl_timeout_seconds: float
    udl_jco_hrr_window_hours: int

    @property
    def udl_credentials_configured(self) -> bool:
        return bool(self.udl_username and self.udl_password)

    @property
    def auth_required(self) -> bool:
        """Auth is enforced once a team token is actually configured."""
        return bool(self.team_token)


def load_settings() -> Settings:
    """Build Settings by reading process.env at call time (not at import time).

    Precedence for UDL credentials: explicit env vars first (the required
    path for the App Store / any hosted deployment), then the local
    credentials.ini fallback (development convenience only, never present
    in the container).
    """
    port = int(_strip_invisible(os.environ.get("PORT", "8080")) or "8080")
    allowed_origin = _strip_invisible(os.environ.get("ALLOWED_ORIGIN", ""))
    team_token_raw = os.environ.get("TEAM_TOKEN", "")
    team_token = _strip_invisible(team_token_raw) or None

    udl_base_url = _strip_invisible(
        os.environ.get("UDL_BASE_URL", "https://unifieddatalibrary.com")
    ).rstrip("/")

    udl_username = os.environ.get("UDL_USERNAME")
    udl_password = os.environ.get("UDL_PASSWORD")
    if udl_username:
        udl_username = _strip_invisible(udl_username)
    if not udl_username or not udl_password:
        ini_creds = _load_credentials_ini("udl")
        if ini_creds:
            udl_username, udl_password = ini_creds

    timeout_raw = _strip_invisible(os.environ.get("UDL_TIMEOUT_SECONDS", "15"))
    udl_timeout_seconds = float(timeout_raw or "15")

    window_raw = _strip_invisible(os.environ.get("UDL_JCO_HRR_WINDOW_HOURS", "24"))
    udl_jco_hrr_window_hours = int(window_raw or "24")

    return Settings(
        port=port,
        allowed_origin=allowed_origin,
        team_token=team_token,
        udl_base_url=udl_base_url,
        udl_username=udl_username,
        udl_password=udl_password,
        udl_timeout_seconds=udl_timeout_seconds,
        udl_jco_hrr_window_hours=udl_jco_hrr_window_hours,
    )
