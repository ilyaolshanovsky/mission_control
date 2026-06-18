from __future__ import annotations

import json
import re
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


def _match_campuses(campuses: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    q = query.lower()
    matched: list[tuple[int, dict[str, Any]]] = []
    for campus in campuses:
        score = 0
        name = (campus.get("campus") or "").lower()
        if name and name in q:
            score += 10
        if name and any(part in q for part in name.split("-")):
            score += 4
        blob = json.dumps(campus, ensure_ascii=False).lower()
        for token in re.findall(r"[а-яёa-z0-9]{3,}", q):
            if token in blob:
                score += 1
        if score:
            matched.append((score, campus))
    matched.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in matched]


def build_context(*, user_message: str, active_section: str | None = None) -> str:
    data = load_data()
    campuses = data.get("campuses") or []
    wants_report = any(w in user_message.lower() for w in ("отчёт", "отчет", "report", "сводк"))
    detailed = wants_report or active_section in {"block2", "block3"}
    matched = _match_campuses(campuses, user_message)

    parts = [
        _network_summary(data),
        "",
        "Нормы CSI:",
        f"- CSI рег. заказчика: красная < {data['norms']['csiCustomer']['red']}, "
        f"жёлтая до {data['norms']['csiCustomer']['yellow']}",
        f"- CSI участников: красная < {data['norms']['csiParticipants']['red']}",
    ]
    if active_section:
        parts.extend(["", f"Пользователь сейчас на вкладке: {SECTION_LABELS.get(active_section, active_section)}"])

    selected = matched[:8] if matched else campuses
    if matched:
        parts.extend(["", "Релевантные кампусы:"])
    else:
        parts.extend(["", "Данные по кампусам:"])

    for campus in selected:
        parts.append(_compact_campus(campus, detailed=detailed or campus in matched[:3]))
        parts.append("")

    if wants_report and len(matched) <= 1:
        parts.append("Подсказка: сформируй отчёт в markdown с таблицами и выводами.")
    return "\n".join(parts).strip()


def find_campuses_in_query(query: str) -> list[dict[str, Any]]:
    data = load_data()
    return _match_campuses(data.get("campuses") or [], query)
