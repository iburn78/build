from pathlib import Path
import re, json
import requests
from datetime import datetime
import pandas as pd
from build.tools.tools import df_krx, sanitized_filename, nfc
from build.models.settings import REFS_DIR, CLASSIFICATION_STRUCTURE_FILE 
from playwright.sync_api import sync_playwright

URL = "https://index.krx.co.kr/contents/MKD/03/0303/03030304/MKD03030304.jsp"
OUT_DIR = REFS_DIR / f"krics_{datetime.now():%Y-%m-%d}"
STRUCTURE_SOURCE_FILE = "https://index.krx.co.kr/contents/MKD/03/0303/03030301/2026-krics-structure-korean_KRX.xlsx"

def download_and_create_krics_summary(out_dir = OUT_DIR) -> pd.DataFrame:
    """Download KRICS files into out_dir and save their combined Excel map beside it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded_files = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(accept_downloads=True)

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Find the sector dropdown
        select = page.locator("select").first

        options = select.locator("option").evaluate_all(
            "(els) => els.map(e => ({value: e.value, text: e.textContent.trim()}))"
        )

        print("Available sectors:")
        for option in options:
            print(option["text"], option["value"])

        # Exclude empty/default options
        sectors = [
            o for o in options
            if o["value"] and o["text"]
        ]

        for sector in sectors:
            name = sector["text"]
            value = sector["value"]

            print(f"Downloading: {name}")

            # Select sector
            select.select_option(value=value)

            # Click 조회
            page.get_by_text("조회", exact=True).last.click()
            page.wait_for_timeout(1500)

            # Click Excel and capture download
            with page.expect_download(timeout=30000) as download_info:
                page.get_by_text(
                    re.compile(r"Excel|엑셀", re.I)
                ).last.click()

            download = download_info.value

            # Save with sector name
            ext = Path(download.suggested_filename).suffix or ".xlsx"
            filepath = out_dir / f"{sanitized_filename(name)}{ext}"

            download.save_as(filepath)
            downloaded_files.append(filepath)
            print(f"  Saved: {filepath.name}")

        browser.close()

    rows = []
    for filepath in sorted(downloaded_files):
        if filepath.suffix.lower() not in {".xls", ".xlsx"}:
            continue

        # A name like "산업재-복합 기업(30-50)" identifies sector/subsector.
        match = re.fullmatch(r"(.+)\((\d+)-(\d+)\)", filepath.stem)
        if not match:
            # Top-level files such as "산업재(30)" do not identify a subsector.
            continue

        names, sector_code, subsector_code = match.groups()
        sector, separator, subsector = names.partition("-")
        if not separator or not sector.strip() or not subsector.strip():
            print(f"Skipping file with unrecognized sector/subsector name: {filepath.name}")
            continue

        try:
            workbook = pd.read_excel(
                filepath,
                usecols=["종목코드", "종목명"],
                dtype={"종목코드": str, "종목명": str},
            )
        except ImportError as error:
            raise ImportError(
                f"Could not read {filepath.name}. Reading .xls files requires xlrd."
            ) from error

        for code, name in workbook[["종목코드", "종목명"]].itertuples(index=False, name=None):
            if pd.isna(code) or pd.isna(name):
                continue
            code = re.sub(r"\.0+$", "", str(code).strip())
            if code.isdigit():
                code = code.zfill(6)
            rows.append({
                "code": code,
                "name": str(name).strip(),
                "sector": sector.strip(),
                "sector_code": str(sector_code),
                "subsector": subsector.strip(),
                "subsector_code": str(subsector_code),
            })

    if not rows:
        raise ValueError(f"No sector/subsector stock rows found in {out_dir}")

    summary = pd.DataFrame(rows).drop_duplicates()
    summary["code"] = summary["code"].astype(str)
    conflicting_codes = summary.groupby("code").nunique().gt(1).any(axis=1)
    if conflicting_codes.any():
        codes = ", ".join(conflicting_codes[conflicting_codes].index[:10])
        raise ValueError(f"Stocks occur in multiple KRICS categories: {codes}")
    summary = summary.drop_duplicates("code").set_index("code").sort_index()
    for column in ("name", "sector", "subsector"):
        summary[column] = summary[column].map(nfc)

    sector_count = summary["sector_code"].nunique()
    subsector_count = summary[["sector_code", "subsector_code"]].drop_duplicates().shape[0]
    print(f"Sectors found: {sector_count}")
    print(f"Subsectors found: {subsector_count}")

    krx_codes = pd.Index(df_krx.index.astype(str))
    summary_codes = pd.Index(summary.index.astype(str))
    covered = krx_codes.intersection(summary_codes)
    missing_from_krics = krx_codes.difference(summary_codes)
    unknown_to_krx = summary_codes.difference(krx_codes)
    print(f"df_krx codes with sector info: {len(covered)}")
    print(f"df_krx codes without sector info: {len(missing_from_krics)}")
    print(f"KRICS codes not found in df_krx: {len(unknown_to_krx)}")
    if len(unknown_to_krx):
        print("Unknown KRICS codes:", ", ".join(unknown_to_krx))

    output_path = out_dir / "summary.xlsx"
    excel_summary = summary.reset_index()
    excel_summary.to_excel(output_path, index=False)
    print(f"Saved {len(summary)} rows to {output_path}")
    return summary


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
            if number not in range(10, 100, 10):
                raise ValueError(f"review code structure: {number} exists")
            return str(int(number / 10))
    except ValueError:
        pass
    return text

def _bilingual_name(value) -> dict[str, str]:
    parts = [_text(part) for part in _text(value).splitlines() if _text(part)]
    return {
        "ko": parts[0] if parts else "",
        "en": parts[1] if len(parts) > 1 else "",
    }

def _download_file(url, save_dir):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    filename = url.split("/")[-1].split("?")[0]
    response = requests.get(url)
    response.raise_for_status()

    path = save_dir / filename
    path.write_bytes(response.content)

    return path

def create_structure_json(out_dir = OUT_DIR):
    source_file = _download_file(STRUCTURE_SOURCE_FILE, out_dir)
    frame = pd.read_excel(source_file, header=2)

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
        group_code = sector_code + _code(row[2])
        group_name = _bilingual_name(row[3])
        industry_code = group_code + _code(row[4])
        industry_name = _bilingual_name(row[5])
        industry_definition = _text(row[6])
        subindustry_code = industry_code + _code(row[7])
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

    with open(CLASSIFICATION_STRUCTURE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"sectors": sectors},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Saved classification structure to {CLASSIFICATION_STRUCTURE_FILE}")

def runner():
    # if CLASSIFICATION_STRUCTURE_FILE.exists():
    #     print(f"TARGET FILE EXISTS: {CLASSIFICATION_STRUCTURE_FILE}")
    #     print("Delete it before running again to overwrite.")
    #     return
    # download_and_create_krics_summary()
    create_structure_json()

if __name__ == "__main__":
    runner()
