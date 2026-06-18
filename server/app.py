from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .context import build_context
from .data_store import get_sync_status, load_data, refresh_from_sheet
from .fallback import try_local_answer
from .llm import chat
from .prompts import ASSISTANT_NAME, SYSTEM_PROMPT
from .report_data import build_report_data

load_dotenv()
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = ROOT / "dashboard.html"


async def _sheet_sync_loop() -> None:
    interval = max(60, int(os.getenv("SHEET_SYNC_INTERVAL_SEC", "300")))
    while True:
        if os.getenv("GOOGLE_SHEET_CSV_URL", "").strip():
            await asyncio.to_thread(refresh_from_sheet)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("GOOGLE_SHEET_CSV_URL", "").strip():
        await asyncio.to_thread(refresh_from_sheet)
        task = asyncio.create_task(_sheet_sync_loop())
    else:
        task = None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Школа 21 — Ольга", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list)
    active_section: str | None = None


class ChatResponse(BaseModel):
    reply: str
    is_report: bool = False
    assistant_name: str = ASSISTANT_NAME
    report_data: dict | None = None


def _parse_report_flag(reply: str) -> tuple[str, bool]:
    is_report = "[[REPORT: да]]" in reply or "[[REPORT: yes]]" in reply
    cleaned = re.sub(r"\[\[REPORT:\s*(да|yes)\]\]\s*", "", reply, flags=re.I).strip()
    return cleaned, is_report


def _chat_response(reply: str) -> ChatResponse:
    reply, is_report = _parse_report_flag(reply)
    payload = build_report_data() if is_report else None
    return ChatResponse(reply=reply, is_report=is_report, report_data=payload)


@app.get("/api/data")
def campus_data() -> dict:
    return load_data()


@app.get("/api/sync/status")
def sync_status() -> dict:
    return get_sync_status()


@app.post("/api/sync")
def sync_now() -> dict:
    if not os.getenv("GOOGLE_SHEET_CSV_URL", "").strip():
        raise HTTPException(
            status_code=400,
            detail="GOOGLE_SHEET_CSV_URL не задан в .env",
        )
    try:
        data = refresh_from_sheet(force=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "updatedAt": data.get("updatedAt"), "campuses": len(data.get("campuses", []))}


@app.get("/api/report")
def report_data() -> dict:
    return build_report_data()


@app.get("/")
def index() -> FileResponse:
    if not DASHBOARD_HTML.exists():
        raise HTTPException(status_code=404, detail="dashboard.html not found")
    return FileResponse(DASHBOARD_HTML)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "assistant": ASSISTANT_NAME}


@app.post("/api/chat", response_model=ChatResponse)
def olga_chat(req: ChatRequest) -> ChatResponse:
    local = try_local_answer(req.message)
    if local is not None:
        return _chat_response(local[0])

    context = build_context(user_message=req.message, active_section=req.active_section)
    system = SYSTEM_PROMPT.format(context=context)
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for item in req.history[-10:]:
        messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": req.message})
    try:
        reply = chat(messages)
    except (RuntimeError, Exception):
        local = try_local_answer(req.message)
        if local is not None:
            return _chat_response(local[0])
        raise HTTPException(
            status_code=503,
            detail="LLM недоступен. Попробуйте конкретный вопрос: «CSI рег. заказчика в Ташкенте», «Красная зона», «Топ MAU».",
        ) from None
    return _chat_response(reply)
