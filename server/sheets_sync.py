from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import unicodedata
from typing import Any

import httpx

PERIOD_HEADERS: dict[str, tuple[str, str]] = {
    "число активных участников основы, накопительно на 01.06.26": ("2026-06", "activeCoreParticipants"),
    "число активных участников основы, накопительно на 01.07.26": ("2026-07", "activeCoreParticipants"),
    "число участников бассейна, накопительно на 01.06.26": ("2026-06", "poolParticipants"),
    "число участников бассейна, накопительно на 01.07.26": ("2026-07", "poolParticipants"),
    "число выпускников, накопительно на 01.06.26": ("2026-06", "graduates"),
    "число выпускников, накопительно на 01.07.26": ("2026-07", "graduates"),
    "mau основа + выпускники на 01.06.26": ("2026-06", "mau"),
    "mau основа + выпускники на 01.07.26": ("2026-07", "mau"),
    "wau / mau основы (основа+выпускники) на 01.06.26": ("2026-06", "wauMauRatio"),
    "wau / mau основы (основа+выпускники) на 01.07.26": ("2026-07", "wauMauRatio"),
    "количество мероприятий на 01.06.26": ("2026-06", "eventsCount"),
    "количество мероприятий на 01.07.26": ("2026-07", "eventsCount"),
    "количество посетивших мероприятия на 01.06.26": ("2026-06", "eventVisitors"),
    "количество посетивших мероприятия на 01.07.26": ("2026-07", "eventVisitors"),
    "количество стажировок от партнеров на 01.06.26": ("2026-06", "internshipsCount"),
    "количество стажировок от партнеров на 01.07.26": ("2026-07", "internshipsCount"),
}

FIELD_HEADERS: dict[str, str] = {
    "кампус": "campus",
    "день рождения кампуса": "foundationDate",
    "количество рабочих мест": "workplaces",
    "вид кампуса": "campusType",
    "общая площадь, м2": "totalArea",
    "полезная площадь, м2 (полезная - за вычетом технических помещений и общих пространств)": "usableArea",
    "общежитие": "dormitory",
    "наличие скуд": "accessControl",
    "количество кластеров": "clustersCount",
    "количество мест в кластерах (название кластера- кол-во мест)": "clusterSeatsDetail",
    "количество мест в конференц зале": "conferenceHall",
    "количество арм в кластерах (кластер-количество арм) обязательно сверьтесь по информации с sup или ops кампуса": "armDetail",
    "количество флипчартов": "flipcharts",
    "количество маркерных досок": "whiteboards",
    "количество одинаковых столов для использования на блоках коммерческих интенсивов (стол примерно на 6 чел.)": "intensiveTables",
    "полное юридичнское наименование": "legalName",
    "учредитель": "founder",
    "система налогообложения": "taxSystem",
    "наличие ндс": "vat",
    "обоснование отсутствия ндс": "vatReason",
    "лицензия на образовательную деятельность": "educationLicense",
    "csi рег заказчика": "csiCustomer",
    "csi участников": "csiParticipants",
    "директор фио директора": "directorName",
    "копоративная электронная почта директоров": "directorEmail",
    "день рождение директора кампуса": "directorBirthday",
}

INT_FIELDS = {
    "workplaces", "clustersCount", "flipcharts", "whiteboards", "intensiveTables",
    "activeCoreParticipants", "poolParticipants", "graduates", "mau",
    "eventsCount", "eventVisitors", "internshipsCount",
}
FLOAT_FIELDS = {"csiCustomer", "csiParticipants", "wauMauRatio"}
PERIOD_KPI_KEYS = {
    "activeCoreParticipants",
    "poolParticipants",
    "graduates",
    "mau",
    "wauMauRatio",
    "eventsCount",
    "eventVisitors",
    "internshipsCount",
}

# Поля, которых нет в CSV Google Таблицы — не затираем при синхронизации.
PRESERVE_FIELDS = (
    "schedule",
    "address",
    "conferenceHall",
    "legalForm",
    "vatReason",
    "campusAgeText",
)


def _normalize_header(header: str) -> str:
    text = unicodedata.normalize("NFKC", header or "")
    text = text.replace("\n", " ").replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _normalize_key(header: str) -> str | tuple[str, str] | None:
    norm = _normalize_header(header)
    if norm in FIELD_HEADERS:
        return FIELD_HEADERS[norm]
    for key, pair in PERIOD_HEADERS.items():
        key_norm = _normalize_header(key)
        if norm == key_norm or key_norm in norm:
            return pair
    return None


def _slug(name: str) -> str:
    s = name.strip().lower().replace(" ", "-")
    s = re.sub(r"[^a-zа-яё0-9\-]", "", s)
    return s or "campus"


def _empty(val: Any) -> bool:
    if val is None:
        return True
    text = str(val).strip()
    return text in {"", "—", "-", "не указано", "не указана", "null", "н/д", "n/a", "n/d"}


def _parse_value(field: str, raw: str) -> Any:
    if _empty(raw):
        return None
    text = str(raw).strip()
    if field == "workplaces":
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else None
    if field in INT_FIELDS:
        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else None
    if field in FLOAT_FIELDS:
        cleaned = text.replace(",", ".").replace("%", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    if field == "directorBirthday":
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            parts = m.group(1).split("-")
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return text
    if field == "accessControl":
        low = text.lower()
        if low in {"да", "yes", "true", "1"}:
            return "да"
        if low in {"нет", "no", "false", "0"}:
            return "нет"
        return text
    if field == "educationLicense":
        low = text.lower()
        if low.startswith("да"):
            return "Да"
        if low.startswith("нет"):
            return "Нет"
        return text
    return text


def _find_existing(campuses: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    key = name.strip().lower()
    for campus in campuses:
        if (campus.get("campus") or "").strip().lower() == key:
            return campus
    return None


def _is_data_row(name: str) -> bool:
    if not name or _empty(name):
        return False
    low = name.lower()
    if "измеряемые" in low or low == "кампус":
        return False
    return True


def _row_to_campus(row: dict[str, str], base: dict[str, Any] | None) -> dict[str, Any]:
    campus: dict[str, Any] = dict(base) if base else {}
    periods: dict[str, dict[str, Any]] = dict(campus.get("periods") or {})
    periods.setdefault("2026-06", {})
    periods.setdefault("2026-07", {})

    for header, raw in row.items():
        mapped = _normalize_key(header)
        if mapped is None:
            continue
        if isinstance(mapped, tuple):
            period_key, field = mapped
            value = _parse_value(field, raw)
            if value is not None:
                periods.setdefault(period_key, {})[field] = value
            continue
        value = _parse_value(mapped, raw)
        if value is not None:
            campus[mapped] = value

    name = campus.get("campus")
    if not name:
        raise ValueError("В строке таблицы не указан кампус")

    campus["id"] = campus.get("id") or _slug(name)
    if campus.get("workplaces") is not None:
        campus["workplacesRaw"] = f"{campus['workplaces']} рм"

    if campus.get("accessControl") is not None:
        low = str(campus["accessControl"]).lower()
        campus["accessControlBool"] = low in {"да", "yes", "true", "1"}
    if campus.get("educationLicense") is not None:
        campus["educationLicenseBool"] = str(campus["educationLicense"]).lower().startswith("да")

    p07 = periods.get("2026-07") or {}
    for key in PERIOD_KPI_KEYS:
        if key in p07:
            campus[key] = p07[key]
    for key in ("csiCustomer", "csiParticipants"):
        if campus.get(key) is not None:
            continue

    if base:
        for field in PRESERVE_FIELDS:
            if base.get(field) is not None:
                campus[field] = base[field]

    campus["periods"] = periods
    return campus


def _fetch_sheet_text(url: str) -> str:
    verify = os.getenv("GOOGLE_SHEET_VERIFY_SSL", "true").lower() in {"1", "true", "yes"}
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30.0, verify=verify)
        response.raise_for_status()
        return response.text
    except Exception:
        proc = subprocess.run(
            ["curl", "-fsSL", url],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout


def sync_from_google_sheet(url: str, *, base_data: dict[str, Any]) -> dict[str, Any]:
    text = _fetch_sheet_text(url)
    if text.startswith("\ufeff"):
        text = text[1:]
    if text.lstrip().startswith("<!DOCTYPE") or text.lstrip().startswith("<html"):
        raise ValueError("Google Таблица недоступна. Проверьте доступ по ссылке и URL экспорта.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV из Google Таблицы пустой или без заголовков")

    base_campuses = base_data.get("campuses") or []
    campuses: list[dict[str, Any]] = []

    for row in reader:
        normalized = {_normalize_header(k): v for k, v in row.items()}
        name = (normalized.get("кампус") or "").strip()
        if not _is_data_row(name):
            continue
        existing = _find_existing(base_campuses, name)
        row_for_parse = {k: v for k, v in row.items()}
        campuses.append(_row_to_campus(row_for_parse, existing))

    if not campuses:
        raise ValueError("В Google Таблице не найдено ни одной строки с кампусами")

    result = dict(base_data)
    result["campuses"] = campuses
    result["periodsAvailable"] = ["2026-06", "2026-07"]
    result["periodLabels"] = {"2026-06": "01.06.2026", "2026-07": "01.07.2026"}
    return result
