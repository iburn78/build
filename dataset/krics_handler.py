from pathlib import Path
import re
import unicodedata
from datetime import datetime
import pandas as pd
from build.tools.tools import df_krx
from build.models.component import Component
from build.models.valuechain import ValueChain
from playwright.sync_api import sync_playwright

URL = "https://index.krx.co.kr/contents/MKD/03/0303/03030304/MKD03030304.jsp"
updated = datetime.now().strftime("%Y-%m-%d")
OUT_DIR = Path(__file__).resolve().parent / "refs" / f"krics_{updated}"
_SECTOR_MAP = None


def _nfc(value):
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


def _nfd(value):
    return unicodedata.normalize("NFD", value) if isinstance(value, str) else value

def safe_filename(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()

def download_all():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

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
            filepath = OUT_DIR / f"{safe_filename(name)}{ext}"

            download.save_as(filepath)
            print(f"  Saved: {filepath.name}")

        browser.close()

def create_sector_map():
    global _SECTOR_MAP
    download_dirs = sorted(
        path for path in OUT_DIR.parent.glob("krics_????-??-??")
        if path.is_dir()
    )
    source_dir = OUT_DIR if OUT_DIR.is_dir() else (download_dirs[-1] if download_dirs else None)
    if source_dir is None:
        raise FileNotFoundError(f"No dated KRICS download directory found in {OUT_DIR.parent}")

    rows = []
    for filepath in sorted(source_dir.iterdir()):
        if not filepath.is_file() or filepath.suffix.lower() not in {".xls", ".xlsx"}:
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
        raise ValueError(f"No sector/subsector stock rows found in {source_dir}")

    summary = pd.DataFrame(rows).drop_duplicates()
    summary["code"] = summary["code"].astype(str)
    conflicting_codes = summary.groupby("code").nunique().gt(1).any(axis=1)
    if conflicting_codes.any():
        codes = ", ".join(conflicting_codes[conflicting_codes].index[:10])
        raise ValueError(f"Stocks occur in multiple KRICS categories: {codes}")
    summary = summary.drop_duplicates("code").set_index("code").sort_index()
    for column in ("name", "sector", "subsector"):
        summary[column] = summary[column].map(_nfc)

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

    output_path = source_dir.parent / f"{source_dir.name}.xlsx"
    excel_summary = summary.reset_index()
    excel_summary.to_excel(output_path, index=False)
    _SECTOR_MAP = summary
    print(f"Saved {len(summary)} rows to {output_path}")
    return summary


def _get_sector_map():
    global _SECTOR_MAP
    if _SECTOR_MAP is None:
        excel_paths = sorted(OUT_DIR.parent.glob("krics_????-??-??.xlsx"))
        if not excel_paths:
            raise FileNotFoundError(
                f"No KRICS sector map found in {OUT_DIR.parent}; run create_sector_map() first."
            )
        _SECTOR_MAP = pd.read_excel(excel_paths[-1], dtype={"code": str}).set_index("code")
    return _SECTOR_MAP


def subsector_to_component(sector=None, subsector=None, sector_code=None, subsector_code=None):
    """Create/update matching components; names or codes may filter the groups.

    A sector-only filter processes every subsector in that sector; no filters
    processes every subsector in the KRICS map.
    """
    sector_map = _get_sector_map().reset_index()
    filters = (
        ("sector", sector),
        ("subsector", subsector),
        ("sector_code", sector_code),
        ("subsector_code", subsector_code),
    )
    for column, value in filters:
        if value is not None:
            value = str(value).strip()
            if column in {"sector", "subsector"}:
                value = _nfc(value)
            sector_map = sector_map[sector_map[column] == value]

    if sector_map.empty:
        raise ValueError("No KRICS companies match the requested sector/subsector.")

    category_columns = ["sector", "sector_code", "subsector", "subsector_code"]
    components = []
    for (sector_name, sector_id, subsector_name, subsector_id), companies in sector_map.groupby(
        category_columns, sort=True
    ):
        component_key = (
            f"{sector_name}-{subsector_name}({sector_id}-{subsector_id})"
        )
        component_key = _nfd(component_key)
        codes = companies["code"].drop_duplicates().tolist()

        # Component.get_item resolves these listed-company keys through
        # Profile.get_item() while building/updating the component's subitems.
        component = Component.get_item(component_key, keylist=codes)
        components.append(component)
        print(f"Created/updated {component_key}: {len(codes)} companies")

    return components


def sector_to_valuechain(sector=None, sector_code=None):
    """Create/update a sector ValueChain by its name, code, or both."""
    if sector is None and sector_code is None:
        raise ValueError("Enter sector or sector_code to select a ValueChain.")

    sector_map = _get_sector_map().reset_index()
    rows = sector_map
    if sector is not None:
        rows = rows[rows["sector"] == _nfc(str(sector).strip())]
    if sector_code is not None:
        rows = rows[rows["sector_code"] == str(sector_code).strip()]
    if rows.empty:
        raise ValueError("No KRICS sector matches the supplied name/code.")

    sectors = rows[["sector", "sector_code"]].drop_duplicates()
    if len(sectors) > 1:
        raise ValueError("Sector name is ambiguous; provide sector_code.")
    sector_name, sector_id = sectors.iloc[0]
    categories = rows[["sector", "sector_code", "subsector", "subsector_code"]].drop_duplicates()
    component_keys = [
        _nfd(f"{row.sector}-{row.subsector}({row.sector_code}-{row.subsector_code})")
        for row in categories.itertuples(index=False)
    ]

    missing = [
        key for key in component_keys
        if Component._get_json_path_from_prefix(key) is None
    ]
    if missing:
        raise ValueError(
            f"Cannot create ValueChain {sector_name}({sector_id}); missing subsector "
            f"Components: {', '.join(missing)}. Run subsector_to_component() for this sector first."
        )

    key = _nfd(f"{sector_name}({sector_id})")
    valuechain = ValueChain.get_item(key, component_keys=component_keys)
    print(f"Created/updated {key} with {len(component_keys)} subsector components")
    return valuechain

if __name__ == "__main__":
    # download_all() 
    create_sector_map() 
    subsector_to_component(sector_code='10', subsector_code='10')
