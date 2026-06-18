from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
SESSIONS_PATH = ROOT / "data" / "chat_sessions.json"
_lock = threading.Lock()

Role = Literal["user", "assistant"]


def _max_messages() -> int:
    return max(10, int(os.getenv("CHAT_SESSION_MAX_MESSAGES", "50")))


def _history_for_llm() -> int:
    return max(4, int(os.getenv("CHAT_HISTORY_FOR_LLM", "20")))


def _load_store() -> dict[str, Any]:
    if not SESSIONS_PATH.exists():
        return {"sessions": {}}
    try:
        data = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sessions": {}}
    if not isinstance(data, dict) or "sessions" not in data:
        return {"sessions": {}}
    return data


def _save_store(data: dict[str, Any]) -> None:
    SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_session_id(session_id: str | None) -> str:
    sid = (session_id or "").strip()
    if sid and len(sid) <= 64 and sid.replace("-", "").isalnum():
        return sid
    return str(uuid.uuid4())


def get_history(session_id: str) -> list[dict[str, str]]:
    with _lock:
        store = _load_store()
        session = store["sessions"].get(session_id) or {}
        history = session.get("history") or []
        return [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and item.get("content")
        ]


def append_exchange(session_id: str, user_message: str, assistant_message: str) -> list[dict[str, str]]:
    with _lock:
        store = _load_store()
        sessions = store.setdefault("sessions", {})
        session = sessions.setdefault(
            session_id,
            {"createdAt": datetime.now(timezone.utc).isoformat(), "history": []},
        )
        history: list[dict[str, str]] = list(session.get("history") or [])
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_message})
        session["history"] = history[-_max_messages() :]
        session["updatedAt"] = datetime.now(timezone.utc).isoformat()
        _save_store(store)
        return list(session["history"])


def history_for_llm(session_id: str) -> list[dict[str, str]]:
    return get_history(session_id)[-_history_for_llm() :]


def clear_session(session_id: str) -> None:
    with _lock:
        store = _load_store()
        if session_id in store.get("sessions", {}):
            del store["sessions"][session_id]
            _save_store(store)
