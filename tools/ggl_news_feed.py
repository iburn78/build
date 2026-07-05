from urllib.parse import quote, urlparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio
import re
import feedparser
from playwright.async_api import async_playwright 
from rapidfuzz import fuzz

# sites that detect crawling
BANNED_DOMAINS = {
    "msn.com",
    "bing.com",
    "daum.net",
    "naver.com",
    "sbs.co.kr",
    "nate.com",
}

DEDUPLICATE_THRESHOLD = 75 # close enough / not too close
MIN_DATES_TO_PASS = 3 # mimimum date difference not to compare titles

async def get_google_news_feed(
    query,
    kr_title: bool, # Korean words have to be included in title if True
    cutoff_months: int, # recent n months
    max_result: int,
    show_res: bool,
):

    if kr_title:
        hl, gl, ceid = "ko", "KR", "KR:ko"
    else:
        hl, gl, ceid = "en", "US", "US:en"

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}"
        f"&hl={hl}"
        f"&gl={gl}"
        f"&ceid={ceid}"
    )

    feed = feedparser.parse(rss_url)

    cutoff = (
        datetime.now(ZoneInfo("Asia/Seoul"))
        - timedelta(days=30 * cutoff_months)
    )

    # preprocess
    entries = []

    for e in feed.entries:

        if not hasattr(e, "published_parsed"):
            continue

        pub_dt = (
            datetime(
                *e.published_parsed[:6],
                tzinfo=timezone.utc
            )
            .astimezone(ZoneInfo("Asia/Seoul"))
        )

        if pub_dt < cutoff:
            continue

        if kr_title and not re.search(r"[가-힣]", e.title):
            continue

        entries.append({
            "title": e.title,
            "link": e.link,
            "published": pub_dt,
        })

    # newest first
    entries.sort(
        key=lambda x: x["published"],
        reverse=True
    )

    # filter titles that are obviously so close
    entries = _deduplicate_titles(
        entries,
    )

    items = []

    batch_size = int(max_result*1.5)
    finished = False
    for start in range(0, len(entries), batch_size):
        batch = entries[start:start + batch_size]

        urls = await asyncio.gather(
            *[
                _resolve_google_news_url(e["link"])
                for e in batch
            ]
        )

        i = 0
        for e, url in zip(batch, urls):

            if url is None:
                continue

            items.append({
                "no": i+1,
                "title": e["title"],
                "url": url,
                "published": e["published"],
            })
            i += 1

            if i >= max_result:
                finished = True
                break

        if finished: break

    if show_res:
        print("---------------------------------------------------------------------------")
        print(f'Google news search for: {query}')
        print("---------------------------------------------------------------------------")
        for i, item in enumerate(items):
            print(f'[{i+1}] {item["title"]}')
            print(f'[{i+1}] {item["url"]}')
            print(f'[{i+1}] {item["published"]}')

    return items

def _is_valid_url(url: str) -> bool:
    """Return True if the URL is supported by Crawl4AI."""
    return url.startswith(("http://", "https://", "file://", "raw:"))

def _is_banned(url: str) -> bool:
    try:
        domain = urlparse(url).netloc.lower()
        return any(b in domain for b in BANNED_DOMAINS)
    except:
        return True

async def _resolve_google_news_url(link):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            page = await browser.new_page()

            await page.goto(
                link,
                wait_until="commit",
                timeout=10000,
            )

            try:
                await page.wait_for_url(
                    lambda u: "news.google.com" not in u,
                    timeout=10000,
                )
            except:
                return None

            if not _is_valid_url(page.url):
                return None

            if not _is_banned(page.url):
                return page.url
        finally:
            await browser.close()

        return None

def _deduplicate_titles(
    entries,
    threshold=DEDUPLICATE_THRESHOLD, # close enough
    min_dates_to_pass=MIN_DATES_TO_PASS, # mimimum date difference not to compare titles
):
    kept = []
    for e in entries:
        duplicate = False
        nt = _normalize_title(e["title"])

        for k in kept:

            days = abs(
                (e["published"] - k["published"]).days
            )

            if days >= min_dates_to_pass:
                continue

            score = fuzz.token_set_ratio(
                nt,
                _normalize_title(k["title"])
            )

            if score >= threshold:
                duplicate = True
                break

        if not duplicate:
            kept.append(e)

    return kept

def _normalize_title(title):
    title = title.lower()

    # remove [xxx]
    title = re.sub(
        r"\[[^\]]+\]",
        "",
        title
    )

    # remove (xxx)
    title = re.sub(
        r"\([^)]*\)",
        "",
        title
    )

    # normalize punctuation → space
    title = re.sub(
        r"[.,:;!?\"'`·•\-_/]+",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    )

    return title.strip()

