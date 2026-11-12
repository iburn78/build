from pathlib import Path
import re
import pandas as pd
from build.tools.tools import df_krx, sanitized_filename, nfc
from build.models.settings import REFS_DIR
from playwright.sync_api import sync_playwright

URL = "https://index.krx.co.kr/contents/MKD/03/0303/03030304/MKD03030304.jsp"
_SECTOR_MAP = None

def download_and_create_sector_map(out_dir: Path) -> pd.DataFrame:
    """Download KRICS files into out_dir and save their combined Excel map beside it."""
    global _SECTOR_MAP
    out_dir = Path(out_dir)
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
        print("Unknown KRICS codes:", ", ".join(unknown_to_krx[:20]))

    output_path = out_dir.parent / f"{out_dir.name}.xlsx"
    excel_summary = summary.reset_index()
    excel_summary.to_excel(output_path, index=False)
    _SECTOR_MAP = summary
    print(f"Saved {len(summary)} rows to {output_path}")
    return summary


if __name__ == "__main__":
    download_and_create_sector_map(REFS_DIR / "krics_downloads")
