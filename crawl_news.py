import re
import os
import asyncio
from datetime import datetime
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from ggl_news_feed import get_google_news_feed

CUTOFF_MONTHS=6 
MAX_RESULT=10 
SHOW_RES=True

cd_ = os.path.dirname(os.path.abspath(__file__)) 
CRAWL_NEWS_DIR = os.path.join(cd_, 'data')

# if destination is None:
GENERAL_DEST = os.path.join(CRAWL_NEWS_DIR, 'general')

# fix once
_exctime = datetime.now().strftime('%Y-%m-%d_%H%M%S_')[:-4] 

def _set_dir_path(destination=None): # and create dirs
    if destination:
        _dest = os.path.join(CRAWL_NEWS_DIR, destination)
    else: 
        _dest = GENERAL_DEST
    os.makedirs(_dest, exist_ok=True)
    return _dest

def _set_filename(no, keywords=None):
    prefix = _exctime+f"[{no}]"
    if keywords:
        safe_keywords = re.sub(r'[\\/*?:"<>|]', "_", keywords)
        filename = f"{prefix}_{'_'.join(safe_keywords.split()[:3])}.md"
    else: 
        filename = f"{prefix}_untitled.md"
    return filename

async def _crawl_url_and_save(crawler, url, no, title=None, published=None, destination=None):
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
        print("Error:", result.error_message)
        return None

    title_ = title or result.metadata.get("title") 
    dirname = _set_dir_path(destination=destination)
    filename = _set_filename(no, title_)
    _file = os.path.join(dirname, filename)

    if published: 
        pdate = published.strftime("%Y-%m-%d") 
    else: 
        pdate = "-----"

    with open(_file, "w", encoding="utf-8") as f:
        if title_:
            f.write(f"# {title_}\n\n")
        f.write(f"source: {url}\n")
        f.write(f"published: {pdate}\n\n")
        f.write(result.markdown.fit_markdown)
        print(f'{filename} is written')

async def _crawl_news(query, kr, cutoff_months, max_result, show_res, destination=None):
    items = await get_google_news_feed(
        query,
        kr_title=kr,
        cutoff_months=cutoff_months,
        max_result=max_result, 
        show_res=show_res,
        )

    async with AsyncWebCrawler() as crawler:
        tasks = [
            _crawl_url_and_save(crawler, i['url'], i['no'], i['title'], i['published'], destination)
            for i in items
            if items
        ]
    
        await asyncio.gather(*tasks)

def crawl_news(
        query, 
        kr=True, 
        cutoff_months=CUTOFF_MONTHS, 
        max_result=MAX_RESULT, 
        show_res=SHOW_RES,
        destination=None,
    ):
    asyncio.run(_crawl_news(query, kr=kr, cutoff_months=cutoff_months, max_result=max_result, show_res=show_res, destination=destination))
