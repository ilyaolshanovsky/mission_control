from __future__ import annotations

from typing import Any

from .context import KPI_LABELS, _campus_zone, load_data


def _conclusions() -> list[str]:
    return [
        "Проконтролировать кампусы в красной зоне по динамике KPI.",
        "Сравнить показатели MAU и вовлечённость (WAU/MAU) у лидеров и аутсайдеров.",
        "Для кампусов без данных по периодам уточнить загрузку истории.",
    ]


def build_report_data() -> dict[str, Any]:
    data = load_data()
    zones: dict[str, list[str]] = {"зелёная": [], "жёлтая": [], "красная": [], "нет данных": []}
    campus_rows: list[dict[str, Any]] = []
    top_mau: list[dict[str, Any]] = []

    for campus in data.get("campuses") or []:
        zone = _campus_zone(campus) or "нет данных"
        zones[zone].append(campus["campus"])
        p06 = (campus.get("periods") or {}).get("2026-06") or {}
        p07 = (campus.get("periods") or {}).get("2026-07") or {}
        campus_rows.append(
            {
                "campus": campus.get("campus"),
                "campusType": campus.get("campusType"),
                "zone": zone,
                "workplaces": campus.get("workplaces"),
                "csiCustomer": campus.get("csiCustomer"),
                "csiParticipants": campus.get("csiParticipants"),
                "activeCoreParticipants_06": p06.get("activeCoreParticipants"),
                "activeCoreParticipants_07": p07.get("activeCoreParticipants"),
                "poolParticipants_06": p06.get("poolParticipants"),
                "poolParticipants_07": p07.get("poolParticipants"),
                "graduates_06": p06.get("graduates"),
                "graduates_07": p07.get("graduates"),
                "mau_06": p06.get("mau"),
                "mau_07": p07.get("mau"),
                "wauMauRatio_07": p07.get("wauMauRatio"),
                "eventsCount_07": p07.get("eventsCount"),
                "eventVisitors_07": p07.get("eventVisitors"),
                "internshipsCount_07": p07.get("internshipsCount"),
            }
        )
        mau = p07.get("mau")
        if mau is not None:
            top_mau.append({"campus": campus["campus"], "mau": mau})

    top_mau.sort(key=lambda x: x["mau"], reverse=True)

    zone_summary = [
        {"zone": zone, "count": len(names), "campuses": ", ".join(names) or "—"}
        for zone, names in zones.items()
    ]

    return {
        "title": "Сводный отчёт по сети кампусов «Школа 21»",
        "updatedAt": data.get("updatedAt"),
        "comparisonPeriod": "2026-06 → 2026-07",
        "kpiLabels": KPI_LABELS,
        "zoneSummary": zone_summary,
        "topMau": top_mau[:10],
        "campuses": campus_rows,
        "conclusions": _conclusions(),
    }
