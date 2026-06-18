from __future__ import annotations

import re
from typing import Any

from .context import GROWTH_KEYS, KPI_LABELS, _campus_zone, find_campuses_in_query, load_data

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


def try_local_answer(message: str) -> tuple[str, bool] | None:
    q = message.lower().strip()

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
