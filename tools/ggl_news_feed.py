from urllib.parse import quote, urlparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import asyncio
import re
import feedparser
import requests
from rapidfuzz import fuzz
from pathlib import Path

# sites that detect crawling, etc 
BANNED_FILE = Path(__file__).with_name("banned_domains.txt")

DEFAULT_BANNED = {
    "msn.com",
    "bing.com",
    "daum.net",
    "naver.com",
    "nate.com",
    "investing.com",
    "judal.co.kr",
    # "tradingkey.com",
    # "sbs.co.kr",
}

if BANNED_FILE.exists():
    with open(BANNED_FILE, encoding="utf-8") as f:
        BANNED_DOMAINS = DEFAULT_BANNED | {
            line.strip()
            for line in f
            if line.strip()
        }
else:
    BANNED_DOMAINS = set(DEFAULT_BANNED)

def add_banned_domain(url: str):
    domain = urlparse(url).netloc.lower().removeprefix("www.")

    if domain in BANNED_DOMAINS:
        return

    BANNED_DOMAINS.add(domain)

    with open(BANNED_FILE, "a", encoding="utf-8") as f:
        f.write(domain + "\n")

    print(f"Added banned domain: {domain}")

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

    # Google News RSS links resolve through HTTP redirects. Resolve them with
    # bounded concurrent requests instead of starting a Chromium process for
    # every query; update_all_models runs thousands of queries in one process.
    batch_size = max(1, min(4, int(max_result * 1.5)))
    for start in range(0, len(entries), batch_size):
        batch = entries[start:start + batch_size]
        urls = await asyncio.gather(
            *(asyncio.to_thread(_resolve_google_news_url, entry["link"]) for entry in batch)
        )

        for entry, url in zip(batch, urls):
            if url is None:
                continue

            items.append({
                "title": entry["title"],
                "url": url,
                "published": entry["published"],
            })

            if len(items) >= max_result:
                break

        if len(items) >= max_result:
            break

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
        return any(
                domain == b or domain.endswith("." + b)
                for b in BANNED_DOMAINS
            )
    except:
        return True

def _resolve_google_news_url(link):
    try:
        response = requests.get(
            link,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
            stream=True,
            timeout=(5, 10),
        )
        try:
            url = response.url
        finally:
            response.close()

        if "news.google.com" in url or not _is_valid_url(url):
            return None

        if not _is_banned(url):
            return url
        return None
    except requests.RequestException:
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

