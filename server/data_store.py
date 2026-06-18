from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

from .sheets_sync import sync_from_google_sheet

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "campus_data.json"

_cache: dict[str, Any] | None = None
_last_sync_at: str | None = None
_last_sync_error: str | None = None
_last_sync_source: str = "file"


def _read_file() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _write_file(data: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_data() -> dict[str, Any]:
    global _cache
    if _cache is None:
        _cache = _read_file()
    return _cache


def get_sync_status() -> dict[str, Any]:
    return {
        "source": _last_sync_source,
        "lastSyncAt": _last_sync_at,
        "lastError": _last_sync_error,
        "sheetUrlConfigured": bool(os.getenv("GOOGLE_SHEET_CSV_URL", "").strip()),
        "intervalSec": int(os.getenv("SHEET_SYNC_INTERVAL_SEC", "300")),
    }


def refresh_from_sheet(*, force: bool = False) -> dict[str, Any]:
    """Fetch Google Sheet and update in-memory cache + JSON file."""
    global _cache, _last_sync_at, _last_sync_error, _last_sync_source

    url = os.getenv("GOOGLE_SHEET_CSV_URL", "").strip()
    if not url:
        _last_sync_source = "file"
        _cache = _read_file()
        return _cache

    try:
        base = _read_file()
        merged = sync_from_google_sheet(url, base_data=base)
        merged["updatedAt"] = date.today().isoformat()
        _cache = merged
        _write_file(merged)
        _last_sync_at = merged["updatedAt"]
        _last_sync_error = None
        _last_sync_source = "google_sheet"
        logger.info("Synced %s campuses from Google Sheet", len(merged.get("campuses", [])))
        return merged
    except Exception as exc:
        _last_sync_error = str(exc)
        logger.exception("Google Sheet sync failed")
        if _cache is None:
            _cache = _read_file()
            _last_sync_source = "file"
        if force:
            raise
        return _cache
