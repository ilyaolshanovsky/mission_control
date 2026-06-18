from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from .data_store import load_data

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "campus_data.json"

KPI_LABELS = {
    "workplaces": "Рабочие места",
    "activeCoreParticipants": "Участники Основы (накоп.)",
    "poolParticipants": "Участники бассейна (накоп.)",
    "graduates": "Выпускники (накоп.)",
    "csiCustomer": "CSI рег. заказчика",
    "mau": "MAU",
    "wauMauRatio": "WAU/MAU основы",
    "eventsCount": "Мероприятия",
    "eventVisitors": "Посетители мероприятий",
    "internshipsCount": "Стажировки",
    "csiParticipants": "CSI участников",
}

GROWTH_KEYS = [
    "activeCoreParticipants",
    "poolParticipants",
    "graduates",
    "mau",
    "wauMauRatio",
    "eventsCount",
    "eventVisitors",
    "internshipsCount",
]

SECTION_LABELS = {
    "block1": "Сводный дашборд",
    "block2": "Карточки кампусов",
    "block3": "График стартов",
}


def load_data() -> dict[str, Any]:
    from .data_store import load_data as _load

    return _load()


def _trend(prev: Any, cur: Any) -> str | None:
    if prev is None or cur is None:
        return None
    if cur > prev:
        return "рост"
    if cur < prev:
        return "снижение"
    return "без изменений"


def _campus_zone(campus: dict[str, Any]) -> str | None:
    periods = campus.get("periods") or {}
    prev = periods.get("2026-06") or {}
    cur = periods.get("2026-07") or {}
    counts = {"рост": 0, "снижение": 0, "без изменений": 0}
    any_trend = False
    for key in GROWTH_KEYS:
        t = _trend(prev.get(key), cur.get(key))
        if t is None:
            continue
        any_trend = True
        counts[t] += 1
    if not any_trend:
        return None
    if counts["снижение"] >= counts["рост"] and counts["снижение"] >= counts["без изменений"]:
        return "красная"
    if counts["рост"] >= counts["без изменений"]:
        return "зелёная"
    return "жёлтая"


def _compact_campus(campus: dict[str, Any], *, detailed: bool = False) -> str:
    p06 = (campus.get("periods") or {}).get("2026-06") or {}
    p07 = (campus.get("periods") or {}).get("2026-07") or {}
    zone = _campus_zone(campus)
    lines = [
        f"### {campus.get('campus')}",
        f"- Тип: {campus.get('campusType') or '—'}; адрес: {campus.get('address') or '—'}",
        f"- Открыт: {campus.get('foundationDate') or '—'}; рабочих мест: {campus.get('workplaces') or '—'}",
        f"- Зона динамики: {zone or 'нет данных'}",
        f"- KPI 2026-06: " + ", ".join(f"{KPI_LABELS[k]}={p06.get(k, '—')}" for k in KPI_LABELS if k in p06 or k in campus),
        f"- KPI 2026-07: " + ", ".join(f"{KPI_LABELS[k]}={p07.get(k, '—')}" for k in KPI_LABELS if k in p07),
    ]
    if detailed:
        lines.extend(
            [
                f"- Общежитие: {campus.get('dormitory') or '—'}",
                f"- СКУД: {campus.get('accessControl') or '—'}",
                f"- Кластеры: {campus.get('clustersCount') or '—'}",
                f"- Юр. лицо: {campus.get('legalName') or '—'}",
                f"- Учредитель: {campus.get('founder') or '—'}",
                f"- Лицензия: {campus.get('educationLicense') or '—'}",
                f"- Директор: {campus.get('directorName') or '—'}",
            ]
        )
        schedule = campus.get("schedule")
        if schedule:
            months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
            sched_bits = []
            for month_idx, dates in sorted(schedule.items(), key=lambda x: int(x[0])):
                if dates:
                    sched_bits.append(f"{months[int(month_idx)-1]}: {', '.join(dates)}")
            if sched_bits:
                lines.append("- Старты бассейнов: " + "; ".join(sched_bits))
    return "\n".join(lines)


def _parse_ru_date(raw: str) -> date | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", (raw or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


MONTH_STEMS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("январ", "янв")),
    (2, ("феврал", "фев")),
    (3, ("март", "мар")),
    (4, ("апрел", "апр")),
    (5, ("май", "мая")),
    (6, ("июн",)),
    (7, ("июл",)),
    (8, ("август", "авг")),
    (9, ("сентябр", "сен")),
    (10, ("октябр", "окт")),
    (11, ("ноябр", "ноя")),
    (12, ("декабр", "дек")),
]


def _parse_month_from_query(q: str) -> int | None:
    for month_num, stems in MONTH_STEMS:
        if any(stem in q for stem in stems):
            return month_num
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*(?:-?й\s+)?(?:месяц|мес)\b", q)
    if m:
        return int(m.group(1))
    return None


def _schedule_overview(
    data: dict[str, Any],
    *,
    user_message: str = "",
    limit: int = 15,
) -> str:
    today = date.today()
    q = user_message.lower()
    month = _parse_month_from_query(q)
    year_m = re.search(r"\b(20\d{2})\b", q)
    year = int(year_m.group(1)) if year_m else None
    rows: list[tuple[date, str, str]] = []
    for campus in data.get("campuses") or []:
        name = campus.get("campus") or "—"
        for dates in (campus.get("schedule") or {}).values():
            for raw in dates:
                parsed = _parse_ru_date(raw)
                if not parsed:
                    continue
                if month is not None and parsed.month != month:
                    continue
                if year is not None and parsed.year != year:
                    continue
                if month is None and parsed < today:
                    continue
                rows.append((parsed, name, raw))
    rows.sort(key=lambda row: (row[0], row[1]))
    if not rows:
        if month is not None:
            return f"Старты бассейнов в месяце {month}: нет дат в данных."
        return "Ближайшие старты бассейнов: нет будущих дат в данных."
    if month is not None:
        lines = [f"Старты бассейнов в месяце {month} по сети:"]
    else:
        lines = ["Ближайшие старты бассейнов по сети:"]
    for parsed, name, raw in rows[:limit]:
        lines.append(f"- {raw} — {name}")
    return "\n".join(lines)


def _zones_breakdown(data: dict[str, Any]) -> str:
    buckets: dict[str, list[str]] = {"зелёная": [], "жёлтая": [], "красная": [], "нет данных": []}
    for campus in data.get("campuses") or []:
        zone = _campus_zone(campus) or "нет данных"
        buckets[zone].append(campus.get("campus") or "—")
    lines = ["Распределение кампусов по зонам динамики:"]
    for zone, names in buckets.items():
        if names:
            lines.append(f"- {zone}: {', '.join(sorted(names))}")
    return "\n".join(lines)


def _kpi_table(data: dict[str, Any]) -> str:
    campuses = data.get("campuses") or []
    if not campuses:
        return ""
    headers = ["Кампус", "Тип", "РМ", "MAU", "CSI зак.", "CSI уч.", "Зона"]
    rows = [f"| {' | '.join(headers)} |", f"| {' | '.join(['---'] * len(headers))} |"]
    for campus in campuses:
        p07 = (campus.get("periods") or {}).get("2026-07") or {}
        zone = _campus_zone(campus) or "—"
        rows.append(
            "| "
            + " | ".join(
                [
                    campus.get("campus") or "—",
                    campus.get("campusType") or "—",
                    str(campus.get("workplaces") or "—"),
                    str(p07.get("mau") if p07.get("mau") is not None else campus.get("mau") or "—"),
                    str(
                        p07.get("csiCustomer")
                        if p07.get("csiCustomer") is not None
                        else campus.get("csiCustomer") or "—"
                    ),
                    str(
                        p07.get("csiParticipants")
                        if p07.get("csiParticipants") is not None
                        else campus.get("csiParticipants") or "—"
                    ),
                    zone,
                ]
            )
            + " |"
        )
    return "## Таблица KPI по всем кампусам (период 2026-07)\n\n" + "\n".join(rows)


def _network_summary(data: dict[str, Any]) -> str:
    campuses = data.get("campuses") or []
    zones = {"зелёная": 0, "жёлтая": 0, "красная": 0, "нет данных": 0}
    total_workplaces = 0
    total_core_07 = 0
    total_pool_07 = 0
    for c in campuses:
        zone = _campus_zone(c)
        zones[zone or "нет данных"] += 1
        total_workplaces += c.get("workplaces") or 0
        p07 = (c.get("periods") or {}).get("2026-07") or {}
        total_core_07 += p07.get("activeCoreParticipants") or 0
        total_pool_07 += p07.get("poolParticipants") or 0
    return (
        f"Дата актуальности: {data.get('updatedAt')}\n"
        f"Кампусов в сети: {len(campuses)}\n"
        f"Суммарно рабочих мест: {total_workplaces}\n"
        f"Суммарно участников Основы (07.2026): {total_core_07}\n"
        f"Суммарно участников бассейна (07.2026): {total_pool_07}\n"
        f"Зоны динамики: зелёная={zones['зелёная']}, жёлтая={zones['жёлтая']}, "
        f"красная={zones['красная']}, без данных={zones['нет данных']}\n"
        f"Доступные периоды: {', '.join(data.get('periodsAvailable') or [])}"
    )


def _name_in_query(name: str, q: str) -> int:
    if not name:
        return 0
    lower_name = name.lower()
    if lower_name in q:
        return 10
    stem = lower_name[: max(4, len(lower_name) - 2)]
    for token in re.findall(r"[а-яёa-z0-9-]{3,}", q):
        if len(lower_name) >= 4 and token.startswith(stem):
            return 8
        if len(token) >= 4 and lower_name.startswith(token[:4]):
            return 6
    for part in re.split(r"[\s\-]+", lower_name):
        if len(part) < 4:
            continue
        if part in q:
            return 6
        for token in re.findall(r"[а-яёa-z0-9-]{3,}", q):
            if token.startswith(part[:4]) or part.startswith(token[:4]):
                return 5
    return 0


def _match_campuses(campuses: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = query.lower()
    matched: list[tuple[int, dict[str, Any]]] = []
    for campus in campuses:
        score = 0
        name = campus.get("campus") or ""
        score += _name_in_query(name, q)
        if name and any(part in q for part in name.lower().split("-")):
            score += 4
        blob = json.dumps(campus, ensure_ascii=False).lower()
        for token in re.findall(r"[а-яёa-z0-9]{3,}", q):
            if token in blob:
                score += 1
        if score:
            matched.append((score, campus))
    matched.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in matched]


def build_context(
    *,
    user_message: str,
    active_section: str | None = None,
    extra_sections: list[str] | None = None,
) -> str:
    data = load_data()
    campuses = data.get("campuses") or []
    q = user_message.lower()
    wants_report = any(w in q for w in ("отчёт", "отчет", "report", "сводк"))
    schedule_query = bool(
        re.search(r"старт|бассейн|график|интенсив|ближайш|расписан|когда\s+нач", q)
    )
    broad_query = wants_report or not _match_campuses(campuses, user_message)
    detailed = wants_report or active_section in {"block2", "block3"} or schedule_query or broad_query
    matched = _match_campuses(campuses, user_message)

    parts = [
        _network_summary(data),
        "",
        _zones_breakdown(data),
        "",
        _kpi_table(data),
        "",
        "Нормы CSI:",
        f"- CSI рег. заказчика: красная < {data['norms']['csiCustomer']['red']}, "
        f"жёлтая до {data['norms']['csiCustomer']['yellow']}",
        f"- CSI участников: красная < {data['norms']['csiParticipants']['red']}",
        "",
        _schedule_overview(data, user_message=user_message),
    ]
    if active_section:
        parts.extend(["", f"Пользователь сейчас на вкладке: {SECTION_LABELS.get(active_section, active_section)}"])

    selected = matched[:8] if matched else campuses[:8]
    if matched:
        parts.extend(["", "Релевантные кампусы (детально):"])
    elif broad_query and len(campuses) > 8:
        parts.extend(["", "Детали по кампусам (первые 8; полная таблица KPI выше):"])
    else:
        parts.extend(["", "Детали по кампусам:"])

    for campus in selected:
        parts.append(_compact_campus(campus, detailed=detailed or campus in matched[:3]))
        parts.append("")

    if wants_report and len(matched) <= 1:
        parts.append("Подсказка: сформируй отчёт в markdown с таблицами и выводами.")

    if extra_sections:
        parts.extend(extra_sections)

    return "\n".join(parts).strip()


def find_campuses_in_query(query: str) -> list[dict[str, Any]]:
    data = load_data()
    return _match_campuses(data.get("campuses") or [], query)
