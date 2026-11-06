from pathlib import Path
import re

from playwright.sync_api import sync_playwright

URL = "https://index.krx.co.kr/contents/MKD/03/0303/03030304/MKD03030304.jsp"
OUT_DIR = Path(__file__).resolve().parent / "refs" / "krics"

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


if __name__ == "__main__":
    download_all()
