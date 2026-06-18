from __future__ import annotations

import logging
import os
import re
from html import unescape
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

_EXPLICIT_SEARCH_RE = re.compile(
    r"погугл|в интернет|поиск в сети|найди в интернет|search the web|поищи в сети|"
    r"загугли|поищи в интернете|найди в сети|посмотри в интернет",
    re.IGNORECASE,
)
_NEWS_RE = re.compile(
    r"новост|актуальн|последн|что пишут|сейчас на сайте|свеж",
    re.IGNORECASE,
)
_ADMISSION_RE = re.compile(
    r"поступ|регистрац|заявк|дедлайн|как попасть|как поступить|приём|прием",
    re.IGNORECASE,
)
_SCHOOL21_RE = re.compile(r"школ\w*\s*21|21-school|school\s*21", re.IGNORECASE)
_DASHBOARD_RE = re.compile(
    r"\bmau\b|csi|kpi|зон[аеу]|кампус|дашборд|метрик|выпускник|стажировк|"
    r"рабочих мест|wau|мероприят",
    re.IGNORECASE,
)


def should_web_search(message: str) -> bool:
    if os.getenv("WEB_SEARCH_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return False
    if _EXPLICIT_SEARCH_RE.search(message):
        return True
    if _NEWS_RE.search(message):
        return True
    if _SCHOOL21_RE.search(message) and _ADMISSION_RE.search(message) and not _DASHBOARD_RE.search(message):
        return True
    return False


def _search_duckduckgo_package(query: str, max_results: int) -> list[dict[str, str]]:
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        rows = list(ddgs.text(query, max_results=max_results, region="ru-ru"))
    return [
        {"title": row.get("title", ""), "url": row.get("href", ""), "snippet": row.get("body", "")}
        for row in rows
        if row.get("href")
    ]


def _http_verify() -> bool:
    return os.getenv("WEB_SEARCH_VERIFY_SSL", "true").lower() in {"1", "true", "yes"}


def fetch_school21_official() -> str:
    try:
        response = httpx.get(
            "https://21-school.ru/",
            headers={"User-Agent": "Mozilla/5.0 (compatible; Shkola21Bot/1.0)"},
            timeout=15.0,
            follow_redirects=True,
            verify=_http_verify(),
        )
        response.raise_for_status()
        html = response.text
        html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
        html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", html)
        text = unescape(re.sub(r"\s+", " ", text)).strip()
        if len(text) > 4000:
            text = text[:4000] + "…"
        return f"## Фрагмент с официального сайта 21-school.ru\n\n{text}"
    except Exception as exc:
        logger.warning("fetch 21-school.ru failed: %s", exc)
        return ""


def should_fetch_official_site(message: str) -> bool:
    if not _SCHOOL21_RE.search(message):
        return False
    if _DASHBOARD_RE.search(message):
        return False
    return bool(_ADMISSION_RE.search(message) or re.search(r"что такое|расскаж|программ|бассейн|основа|методик", message, re.I))


def _search_duckduckgo_html(query: str, max_results: int) -> list[dict[str, str]]:
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    response = httpx.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Shkola21Bot/1.0)"},
        timeout=15.0,
        follow_redirects=True,
        verify=_http_verify(),
    )
    response.raise_for_status()
    html = response.text
    blocks = re.split(r'<div class="result\s+results_links[^"]*">', html)[1:]
    results: list[dict[str, str]] = []
    for block in blocks:
        title_m = re.search(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        snippet_m = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>', block, re.S)
        if not title_m:
            continue
        title = re.sub(r"<[^>]+>", "", title_m.group(2))
        snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)) if snippet_m else ""
        results.append(
            {
                "title": unescape(title).strip(),
                "url": unescape(title_m.group(1)).strip(),
                "snippet": unescape(snippet).strip(),
            }
        )
        if len(results) >= max_results:
            break
    return results


def search_web(query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
    limit = max_results or int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    search_query = query.strip()
    if _SCHOOL21_RE.search(search_query) and "21-school" not in search_query.lower():
        search_query = f"{search_query} Школа 21 site:21-school.ru OR школа 21"

    try:
        return _search_duckduckgo_package(search_query, limit)
    except Exception as exc:
        logger.warning("duckduckgo_search package failed: %s", exc)

    try:
        return _search_duckduckgo_html(search_query, limit)
    except Exception as exc:
        logger.warning("DuckDuckGo HTML fallback failed: %s", exc)
        return []


def format_search_results(query: str, results: list[dict[str, str]]) -> str:
    if not results:
        return f"## Результаты поиска в интернете\n\nПо запросу «{query}» ничего не найдено."
    lines = [f"## Результаты поиска в интернете\n\nЗапрос: {query}", ""]
    for idx, row in enumerate(results, start=1):
        lines.append(f"{idx}. **{row['title']}**")
        lines.append(f"   URL: {row['url']}")
        if row.get("snippet"):
            lines.append(f"   {row['snippet']}")
        lines.append("")
    lines.append(
        "_Используй эти результаты для актуальной информации. "
        "Цифры KPI и кампусов — только из данных дашборда._"
    )
    return "\n".join(lines)
