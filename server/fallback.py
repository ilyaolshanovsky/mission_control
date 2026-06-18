from __future__ import annotations

import re
from datetime import date
from typing import Any

from .context import GROWTH_KEYS, KPI_LABELS, _campus_zone, find_campuses_in_query, load_data

SCHEDULE_QUERY_RE = re.compile(
    r"старт|старты|бассейн|интенсив|график\s*старт|ближайш|расписан|когда\s+нач|"
    r"январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр",
    re.IGNORECASE,
)

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

MONTH_NAMES_PREP = {
    1: "январе",
    2: "феврале",
    3: "марте",
    4: "апреле",
    5: "мае",
    6: "июне",
    7: "июле",
    8: "августе",
    9: "сентябре",
    10: "октябре",
    11: "ноябре",
    12: "декабре",
}

METRIC_ALIASES: dict[str, list[str]] = {
    "csiCustomer": [
        "csi рег",
        "csi заказчик",
        "csi рег. заказчика",
        "csi рег заказчика",
        "csi заказчика",
    ],
    "csiParticipants": ["csi участник", "csi участников"],
    "mau": ["mau"],
    "wauMauRatio": ["wau/mau", "wau mau", "wau"],
    "workplaces": ["рабоч", "рабочих мест", "рм"],
    "activeCoreParticipants": ["основ", "участник основы", "участников основы"],
    "poolParticipants": ["бассейн", "участник бассейна", "участников бассейна"],
    "graduates": ["выпуск"],
    "eventsCount": ["мероприят"],
    "eventVisitors": ["посетител"],
    "internshipsCount": ["стажиров"],
    "clustersCount": ["кластер"],
    "campusType": ["тип кампуса", "вид кампуса"],
    "address": ["адрес"],
    "directorName": ["директор"],
    "educationLicense": ["лиценз"],
    "dormitory": ["общежит"],
    "accessControl": ["скуд"],
}


def _fmt_value(key: str, value: Any) -> str:
    if value is None:
        return "—"
    if key == "wauMauRatio" and isinstance(value, (int, float)):
        return f"{round(value * 100)}%"
    if key in {"csiCustomer", "csiParticipants"} and isinstance(value, (int, float)):
        return str(value).replace(".", ",")
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _csi_zone(data: dict[str, Any], key: str, value: Any) -> str | None:
    if value is None:
        return None
    norms = data.get("norms") or {}
    if key == "csiCustomer":
        n = norms.get("csiCustomer") or {}
        if value < n.get("red", 4.2):
            return "красная"
        if value <= n.get("yellow", 4.5):
            return "жёлтая"
        return "зелёная"
    if key == "csiParticipants":
        n = norms.get("csiParticipants") or {}
        if value < n.get("red", 4.3):
            return "красная"
        return "зелёная"
    return None


def _detect_metric(query: str) -> str | None:
    q = query.lower()
    for key, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            if alias in q:
                return key
    return None


def _campuses_by_zone(zone: str) -> list[dict[str, Any]]:
    data = load_data()
    return [c for c in data["campuses"] if _campus_zone(c) == zone]


def _zone_reasons(campus: dict[str, Any]) -> list[str]:
    prev = (campus.get("periods") or {}).get("2026-06") or {}
    cur = (campus.get("periods") or {}).get("2026-07") or {}
    reasons = []
    for key in GROWTH_KEYS:
        p, c = prev.get(key), cur.get(key)
        if p is None or c is None:
            continue
        if c < p:
            label = KPI_LABELS.get(key, key)
            reasons.append(f"{label}: {p} → {c}")
    return reasons


def _format_campus_metric(campus: dict[str, Any], metric_key: str) -> str:
    data = load_data()
    label = KPI_LABELS.get(metric_key, metric_key)
    if metric_key in campus:
        value = campus.get(metric_key)
    else:
        value = None
    zone = _csi_zone(data, metric_key, value) if metric_key.startswith("csi") else None
    lines = [
        f"**{label}** — кампус **{campus['campus']}**: **{_fmt_value(metric_key, value)}**",
    ]
    if zone:
        lines.append(f"Зона по норме: **{zone}**")
    lines.append("")
    lines.append("_Ответ сформирован по данным дашборда._")
    return "\n".join(lines)


def _format_campus_card(campus: dict[str, Any]) -> str:
    data = load_data()
    zone = _campus_zone(campus)
    p07 = (campus.get("periods") or {}).get("2026-07") or {}
    lines = [
        f"**Кампус {campus['campus']}**",
        "",
        f"- Тип: {campus.get('campusType') or '—'}",
        f"- Адрес: {campus.get('address') or '—'}",
        f"- Рабочих мест: {_fmt_value('workplaces', campus.get('workplaces'))}",
        f"- Зона динамики: {zone or 'нет данных'}",
        f"- CSI рег. заказчика: {_fmt_value('csiCustomer', campus.get('csiCustomer'))}",
        f"- CSI участников: {_fmt_value('csiParticipants', campus.get('csiParticipants'))}",
        f"- MAU (07.2026): {_fmt_value('mau', p07.get('mau'))}",
        f"- Участников Основы (07.2026): {_fmt_value('activeCoreParticipants', p07.get('activeCoreParticipants'))}",
        "",
        "_Ответ сформирован по данным дашборда._",
    ]
    return "\n".join(lines)


def _format_zone_answer(zone: str, title: str) -> str:
    campuses = _campuses_by_zone(zone)
    if not campuses:
        return f"Кампусов в {title} сейчас нет."
    lines = [f"**{title}** ({len(campuses)} кампусов):", ""]
    for c in campuses:
        reasons = _zone_reasons(c)
        lines.append(f"- **{c['campus']}**")
        if reasons:
            lines.append("  Снижение по метрикам: " + "; ".join(reasons[:4]))
    lines.append("")
    lines.append("_Ответ сформирован по данным дашборда (сравнение 06.2026 и 07.2026)._")
    return "\n".join(lines)


def _format_top_mau(limit: int = 5) -> str:
    data = load_data()
    ranked = []
    for c in data["campuses"]:
        p07 = (c.get("periods") or {}).get("2026-07") or {}
        mau = p07.get("mau")
        if mau is not None:
            ranked.append((mau, c["campus"]))
    ranked.sort(reverse=True)
    lines = [f"**Топ-{limit} кампусов по MAU (июль 2026):**", ""]
    for i, (mau, name) in enumerate(ranked[:limit], 1):
        lines.append(f"{i}. **{name}** — {mau:,}".replace(",", " "))
    lines.append("")
    lines.append("_Ответ сформирован по данным дашборда._")
    return "\n".join(lines)


def _format_network_summary() -> str:
    data = load_data()
    zones = {"зелёная": 0, "жёлтая": 0, "красная": 0, "нет данных": 0}
    for c in data["campuses"]:
        zone = _campus_zone(c)
        zones[zone or "нет данных"] += 1
    lines = [
        "**Сводка по сети кампусов «Школа 21»**",
        "",
        f"- Дата актуальности: {data['updatedAt']}",
        f"- Кампусов в сети: {len(data['campuses'])}",
        f"- Зелёная зона: {zones['зелёная']}",
        f"- Жёлтая зона: {zones['жёлтая']}",
        f"- Красная зона: {zones['красная']}",
        f"- Без данных для оценки: {zones['нет данных']}",
        "",
        "_Ответ сформирован по данным дашборда._",
    ]
    return "\n".join(lines)


def _format_report() -> str:
    data = load_data()
    zones = {"зелёная": [], "жёлтая": [], "красная": [], "нет данных": []}
    for c in data["campuses"]:
        zone = _campus_zone(c) or "нет данных"
        zones[zone].append(c["campus"])

    lines = [
        "# Сводный отчёт по сети кампусов «Школа 21»",
        "",
        f"**Дата актуальности данных:** {data['updatedAt']}",
        f"**Период сравнения:** 06.2026 → 07.2026",
        "",
        "## Распределение по зонам динамики",
        "",
        "| Зона | Кол-во | Кампусы |",
        "|------|--------|---------|",
    ]
    for zone, names in zones.items():
        lines.append(f"| {zone} | {len(names)} | {', '.join(names) or '—'} |")

    lines.extend(["", "## Топ-5 по MAU (07.2026)", ""])
    ranked = []
    for c in data["campuses"]:
        p07 = (c.get("periods") or {}).get("2026-07") or {}
        mau = p07.get("mau")
        if mau is not None:
            ranked.append((mau, c["campus"]))
    ranked.sort(reverse=True)
    for i, (mau, name) in enumerate(ranked[:5], 1):
        lines.append(f"{i}. {name} — {mau}")

    lines.extend(
        [
            "",
            "## Выводы и рекомендации",
            "",
            "- Проконтролировать кампусы в красной зоне по динамике KPI.",
            "- Сравнить показатели MAU и вовлечённость (WAU/MAU) у лидеров и аутсайдеров.",
            "- Для кампусов без данных по периодам уточнить загрузку истории.",
            "",
            "[[REPORT: да]]",
        ]
    )
    return "\n".join(lines)


def _parse_ru_date(raw: str) -> date | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", (raw or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _days_label(target: date) -> str:
    delta = (target - date.today()).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta < 0:
        return f"{abs(delta)} дн. назад"
    return f"через {delta} дн."


def _parse_month_from_query(q: str) -> int | None:
    for month_num, stems in MONTH_STEMS:
        if any(stem in q for stem in stems):
            return month_num
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*(?:-?й\s+)?(?:месяц|мес)\b", q)
    if m:
        return int(m.group(1))
    return None


def _parse_year_from_query(q: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", q)
    return int(m.group(1)) if m else None


def _collect_start_dates(
    campuses: list[dict[str, Any]] | None = None,
    *,
    future_only: bool = True,
    month: int | None = None,
    year: int | None = None,
    limit: int = 20,
) -> list[tuple[date, str, str]]:
    data = load_data()
    pool = campuses if campuses else data.get("campuses") or []
    today = date.today()
    rows: list[tuple[date, str, str]] = []
    for campus in pool:
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
                if future_only and month is None and parsed < today:
                    continue
                rows.append((parsed, name, raw))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows[:limit]


def _schedule_title(
    *,
    campuses: list[dict[str, Any]] | None,
    month: int | None,
    year: int | None,
) -> str:
    if month is not None:
        month_label = MONTH_NAMES_PREP.get(month, f"месяце {month}")
        year_bit = f" {year}" if year else ""
        base = f"**Старты бассейнов в {month_label}{year_bit}**"
    else:
        base = "**Ближайшие старты бассейнов**"
    if campuses:
        return f"{base} — {', '.join(c['campus'] for c in campuses)}"
    if month is not None:
        return f"{base} по сети"
    return "**Ближайшие старты бассейнов по сети**"


def _format_schedule_rows(
    rows: list[tuple[date, str, str]],
    *,
    title: str,
    empty_hint: str,
) -> str:
    if not rows:
        return (
            f"{title}\n\n"
            f"{empty_hint}\n\n"
            "_Данные из блока «График стартов» дашборда._"
        )

    by_date: dict[date, list[tuple[str, str]]] = {}
    for parsed, name, raw in rows:
        by_date.setdefault(parsed, []).append((name, raw))

    lines = [title, ""]
    for parsed in sorted(by_date):
        entries = by_date[parsed]
        display_date = entries[0][1]
        campus_names = ", ".join(sorted({name for name, _ in entries}))
        lines.append(f"- **{display_date}** — {campus_names} ({_days_label(parsed)})")

    lines.extend(["", "_Данные из блока «График стартов» дашборда._"])
    return "\n".join(lines)


def _format_upcoming_starts(message: str) -> str:
    q = message.lower()
    campuses = find_campuses_in_query(message)
    month = _parse_month_from_query(q)
    year = _parse_year_from_query(q)
    rows = _collect_start_dates(
        campuses or None,
        future_only=month is None,
        month=month,
        year=year,
        limit=20,
    )
    title = _schedule_title(campuses=campuses or None, month=month, year=year)
    if month is not None:
        month_label = MONTH_NAMES_PREP.get(month, str(month))
        empty_hint = f"В графике нет стартов в {month_label}{f' {year}' if year else ''}."
    else:
        empty_hint = "В графике нет будущих дат стартов для выбранного фильтра."
    return _format_schedule_rows(rows, title=title, empty_hint=empty_hint)


def _format_campus_starts(campus: dict[str, Any], message: str) -> str:
    q = message.lower()
    month = _parse_month_from_query(q)
    year = _parse_year_from_query(q)
    rows = _collect_start_dates(
        [campus],
        future_only=month is None,
        month=month,
        year=year,
        limit=20,
    )
    name = campus.get("campus") or "—"
    if month is not None:
        month_label = MONTH_NAMES_PREP.get(month, str(month))
        title = f"**Старты бассейнов в {month_label}{f' {year}' if year else ''} — {name}**"
        empty_hint = f"В графике нет стартов в {month_label}{f' {year}' if year else ''} для кампуса {name}."
    else:
        title = f"**График стартов — {name}**"
        empty_hint = f"Будущих дат стартов бассейна для кампуса {name} в данных нет."
    return _format_schedule_rows(rows, title=title, empty_hint=empty_hint)


def try_local_answer(message: str) -> tuple[str, bool] | None:
    q = message.lower().strip()

    if q in {"привет", "здравствуй", "здравствуйте", "hello", "hi", "добрый день", "добрый вечер"}:
        return (
            "Привет! Я **Ольга**, ассистент дашборда сети кампусов «Школа 21». "
            "Знаю всё про дашборд (KPI, зоны, кампусы, график стартов), "
            "расскажу про программу и поступление в Школу 21, "
            "и могу поискать актуальную информацию в интернете.\n\n"
            "Попробуйте: **Красная зона**, **Топ MAU**, **Сводный отчёт**, "
            "«где ближайшие старты», «как поступить в Школу 21».",
            False,
        )

    if re.search(r"красн\w*\s+зон", q) or "красная зона" in q or q == "красная зона":
        return _format_zone_answer("красная", "Красная зона"), False

    if re.search(r"жёлт\w*\s+зон|желт\w*\s+зон", q):
        return _format_zone_answer("жёлтая", "Жёлтая зона"), False

    if re.search(r"зелён\w*\s+зон|зелен\w*\s+зон", q):
        return _format_zone_answer("зелёная", "Зелёная зона"), False

    if "зон" in q and ("сет" in q or "распредел" in q or "сколько кампус" in q):
        return _format_network_summary(), False

    if "топ" in q and "mau" in q:
        return _format_top_mau(), False

    if any(w in q for w in ("сводный отчёт", "сводный отчет", "сводк")) or re.search(r"\bотч[её]т\b", q):
        return _format_report(), True

    if SCHEDULE_QUERY_RE.search(q):
        campuses = find_campuses_in_query(message)
        if campuses and len(campuses) == 1:
            return _format_campus_starts(campuses[0], message), False
        return _format_upcoming_starts(message), False

    campuses = find_campuses_in_query(message)
    metric = _detect_metric(q)

    if campuses and metric:
        return _format_campus_metric(campuses[0], metric), False

    if campuses and len(campuses) == 1:
        if any(w in q for w in ("расскаж", "информац", "покаж", "карточк", "данные", "про кампус", "о кампус")):
            return _format_campus_card(campuses[0]), False
        if re.search(r"^(что|какой|какая|какие|сколько)\b", q):
            return _format_campus_card(campuses[0]), False

    if metric and not campuses:
        data = load_data()
        lines = [f"**{KPI_LABELS.get(metric, metric)}** по сети:", ""]
        for c in data["campuses"]:
            if metric in c and c.get(metric) is not None:
                lines.append(f"- **{c['campus']}**: {_fmt_value(metric, c.get(metric))}")
        if len(lines) > 2:
            lines.extend(["", "_Ответ сформирован по данным дашборда._"])
            return "\n".join(lines), False

    return None
