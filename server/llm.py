from __future__ import annotations

import logging
import os
import uuid

import httpx
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

load_dotenv()
logger = logging.getLogger(__name__)

GIGACHAT_BASE_URL = "https://gigachat.devices.sberbank.ru/api/v1"
_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"


def _get_gigachat_token() -> str:
    credentials = os.getenv("GIGACHAT_CREDENTIALS", "").strip()
    if not credentials or credentials == "put_your_base64_here":
        raise RuntimeError("GIGACHAT_CREDENTIALS is not configured")
    response = httpx.post(
        _OAUTH_URL,
        data={"scope": "GIGACHAT_API_PERS"},
        headers={
            "Authorization": f"Basic {credentials}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        verify=os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() in {"1", "true", "yes"},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _openai_key() -> str:
    return (
        os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("PROVIDER_API_KEY", "").strip()
    )


def _openai_base_url() -> str | None:
    return os.getenv("OPENAI_BASE_URL") or os.getenv("PROVIDER_BASE_URL") or None


def _build_model(provider: str) -> ChatOpenAI:
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2500"))

    if provider == "gigachat":
        verify_ssl = os.getenv("GIGACHAT_VERIFY_SSL", "false").lower() in {"1", "true", "yes"}
        return ChatOpenAI(
            model=os.getenv("GIGACHAT_MODEL", "GigaChat-2"),
            api_key=_get_gigachat_token(),
            base_url=GIGACHAT_BASE_URL,
            temperature=temperature,
            max_tokens=max_tokens,
            http_client=httpx.Client(verify=verify_ssl),
        )

    api_key = _openai_key()
    if not api_key or api_key == "put_your_key_here":
        raise RuntimeError("OPENAI_API_KEY or PROVIDER_API_KEY is not configured")

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        base_url=_openai_base_url(),
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _provider_chain() -> list[str]:
    preferred = os.getenv("LLM_PROVIDER", "gigachat").strip().lower()
    chain = []
    if preferred == "gigachat":
        chain = ["gigachat", "openai"]
    else:
        chain = ["openai", "gigachat"]
    return chain


def _to_lc_messages(messages: list[dict[str, str]]):
    lc_messages = []
    for item in messages:
        role = item["role"]
        content = item["content"]
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
    return lc_messages


def chat(messages: list[dict[str, str]]) -> str:
    errors: list[str] = []
    for provider in _provider_chain():
        try:
            model = _build_model(provider)
            result = model.invoke(_to_lc_messages(messages))
            return (result.content or "").strip()
        except Exception as exc:
            logger.warning("LLM provider %s failed: %s", provider, exc)
            errors.append(f"{provider}: {exc}")
    raise RuntimeError("Все LLM-провайдеры недоступны. " + "; ".join(errors))
