import re
import asyncio
import atexit
import contextvars
from datetime import datetime
from pathlib import Path
from threading import RLock, current_thread
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from build.tools.ggl_news_feed import (
    add_banned_domain,
    close_google_news_browser,
    get_google_news_feed,
)
from build.models.settings import NEWS_CUTOFF_MONTHS, NUM_TO_CRAWL_DEFAULT, SHOW_CRAWL_RES

CUTOFF_MONTHS=NEWS_CUTOFF_MONTHS

_CRAWL_RUNNERS = {}
_CRAWL_RUNNERS_LOCK = RLock()


def _get_crawl_runner() -> asyncio.Runner:
    """Reuse one event loop per calling thread instead of creating one per query."""
    thread = current_thread()
    with _CRAWL_RUNNERS_LOCK:
        runner = _CRAWL_RUNNERS.get(thread)
        if runner is None:
            runner = asyncio.Runner()
            _CRAWL_RUNNERS[thread] = runner
        return runner


def _close_crawl_runners() -> None:
    with _CRAWL_RUNNERS_LOCK:
        runners = list(_CRAWL_RUNNERS.values())
        _CRAWL_RUNNERS.clear()
    for runner in runners:
        try:
            runner.run(close_google_news_browser(), context=contextvars.Context())
        except Exception:
            pass
        try:
            runner.close()
        except Exception:
            # Process shutdown should not be interrupted by async cleanup.
            pass


atexit.register(_close_crawl_runners)

# fix once to express download time
_exetime = datetime.now().strftime('%y%m%d%H%M') 

def _set_dir_path(dest_dir): # and create dirs
    if dest_dir is None:
        raise ValueError("A destination directory is required when crawling news.")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir

def _set_filename(timestamp, title=None):
    if title:
        title = re.sub(r'[<>:"/\\|?*\'`‘’“”,]+', '', title)

        _titles = title.split('-')
        if len(_titles) > 1: 
            _media = _titles[-1].strip()
        else: 
            _media = ""
        _title = "-".join(_titles[:-1])
        
        filename = f"{timestamp}_[{''.join(_media.split()[:3])}]_{'_'.join(_title.split()[:10])}.md"
    else: 
        filename = f"{timestamp}_untitled.md"
    return filename

async def _crawl_url_and_save(crawler, url, title=None, published=None, dest_dir=None):
    prune_filter = PruningContentFilter(
        # higher for more content pruned [0, 1]
        threshold=0.99,
        # dynamic adjustment of threshold
        threshold_type="dynamic",  
        # Ignore nodes with <10 words
        min_word_threshold=10
    )

    md_generator = DefaultMarkdownGenerator(content_filter=prune_filter)
    config = CrawlerRunConfig(markdown_generator=md_generator)

    result = await crawler.arun(url=url, config=config)
    if not result.success:
        err = (result.error_message or "").lower()

        ANTI_BOT_PATTERNS = (
            "acs-goto",
            "captcha",
            "cloudflare",
            "403",
            "forbidden",
            "access denied",
            "err_http_response_code_failure",
            "proxy direct failed",
        )

        if any(p in err for p in ANTI_BOT_PATTERNS):
            add_banned_domain(url)

        print(result.error_message)
        return

    title_ = title or result.metadata.get("title") 
    dirname = _set_dir_path(dest_dir=dest_dir)

    if published: 
        pdate = published.strftime("%Y-%m-%d") 
    else: 
        pdate = '_'

    filename = _set_filename(pdate, title_)
    _file = dirname / filename

    with _file.open("w", encoding="utf-8") as f:
        if title_:
            f.write(f"# {title_}\n\n")
        f.write(f"source: {url}\n")
        f.write(f"published: {pdate}\n")
        f.write(f"scrapped: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(result.markdown.fit_markdown)
        f.write("\n")
        print(f"Saved: {filename}")

async def _crawl_news(query, kr, cutoff_months, max_result, show_res, dest_dir):
    items = await get_google_news_feed(
        query,
        kr_title=kr,
        cutoff_months=cutoff_months,
        max_result=max_result, 
        show_res=show_res,
        )
    if not items:
        return

    async with AsyncWebCrawler() as crawler:
        tasks = [
            _crawl_url_and_save(crawler, i['url'], i['title'], i['published'], dest_dir)
            for i in items
        ]
        await asyncio.gather(*tasks)

def crawl_news(
        query, 
        kr=True, 
        cutoff_months=CUTOFF_MONTHS, 
        max_result=NUM_TO_CRAWL_DEFAULT, 
        show_res=SHOW_CRAWL_RES,
        dest_dir=None,
    ):
    crawl = _crawl_news(
        query,
        kr=kr,
        cutoff_months=cutoff_months,
        max_result=max_result,
        show_res=show_res,
        dest_dir=dest_dir,
    )
    try:
        _get_crawl_runner().run(crawl, context=contextvars.copy_context())
    except BaseException:
        # The runner can fail before scheduling the coroutine (for example,
        # if the process has exhausted its file descriptors).
        crawl.close()
        raise
