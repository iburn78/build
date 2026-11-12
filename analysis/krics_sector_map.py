"""Read the KRICS structure workbook as a nested sector map for the UI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from build.models.settings import KRICS_STRUCTURE_FILE


def _text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _code(value) -> str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except ValueError:
        pass
    return text


def _bilingual_name(value) -> dict[str, str]:
    parts = [_text(part) for part in _text(value).splitlines() if _text(part)]
    return {
        "ko": parts[0] if parts else "",
        "en": parts[1] if len(parts) > 1 else "",
    }


def load_krics_sector_map() -> dict:
    if not KRICS_STRUCTURE_FILE.is_file():
        raise FileNotFoundError(f"KRICS structure workbook not found: {KRICS_STRUCTURE_FILE}")

    frame = pd.read_excel(KRICS_STRUCTURE_FILE, header=2)
    if len(frame.columns) < 10:
        raise ValueError("KRICS structure workbook does not have the expected 10 columns.")

    # The workbook merges parent cells vertically. Fill only sector, group,
    # and industry columns so every subindustry row carries its full lineage.
    for column_index in range(7):
        frame.iloc[:, column_index] = frame.iloc[:, column_index].ffill()

    sectors: list[dict] = []
    sector_lookup: dict[tuple[str, str], dict] = {}
    group_lookup: dict[tuple[str, str, str, str], dict] = {}
    industry_lookup: dict[tuple[str, str, str, str, str, str], dict] = {}

    for row in frame.itertuples(index=False, name=None):
        sector_code = _code(row[0])
        sector_name = _bilingual_name(row[1])
        group_code = _code(row[2])
        group_name = _bilingual_name(row[3])
        industry_code = _code(row[4])
        industry_name = _bilingual_name(row[5])
        industry_definition = _text(row[6])
        subindustry_code = _code(row[7])
        subindustry_name = _bilingual_name(row[8])
        subindustry_definition = _text(row[9])

        if not sector_code or not sector_name["ko"] or not group_code or not group_name["ko"]:
            continue
        sector_key = (sector_code, sector_name["ko"])
        if sector_key not in sector_lookup:
            sector = {"code": sector_code, "name": sector_name, "groups": []}
            sector_lookup[sector_key] = sector
            sectors.append(sector)
        sector = sector_lookup[sector_key]

        group_key = (*sector_key, group_code, group_name["ko"])
        if group_key not in group_lookup:
            group = {"code": group_code, "name": group_name, "industries": []}
            group_lookup[group_key] = group
            sector["groups"].append(group)
        group = group_lookup[group_key]

        if not industry_code or not industry_name["ko"]:
            continue
        industry_key = (*group_key, industry_code, industry_name["ko"])
        if industry_key not in industry_lookup:
            industry = {
                "code": industry_code,
                "name": industry_name,
                "definition": industry_definition,
                "subindustries": [],
            }
            industry_lookup[industry_key] = industry
            group["industries"].append(industry)
        industry = industry_lookup[industry_key]

        if subindustry_code and subindustry_name["ko"]:
            industry["subindustries"].append({
                "code": subindustry_code,
                "name": subindustry_name,
                "definition": subindustry_definition,
            })

    return {"fileName": KRICS_STRUCTURE_FILE.name, "sectors": sectors}


if __name__ == "__main__":
    print(json.dumps(load_krics_sector_map(), ensure_ascii=False))
