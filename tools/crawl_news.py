import re
import os
import asyncio
from datetime import datetime
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from scraper.tools.ggl_news_feed import get_google_news_feed
from scraper.tools.tools import NEWS_DIR, GENERAL_DIR

CUTOFF_MONTHS=3 
MAX_RESULT=10 
SHOW_RES=True

# fix once to express download time
_exetime = datetime.now().strftime('%y%m%d%H%M') 

def _set_dir_path(dest_dir=None): # and create dirs
    if dest_dir:
        _dest = os.path.join(NEWS_DIR, dest_dir)
    else: 
        _dest = GENERAL_DIR
    os.makedirs(_dest, exist_ok=True)
    return _dest

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
        print("Error:", result.error_message)
        return None

    title_ = title or result.metadata.get("title") 
    dirname = _set_dir_path(dest_dir=dest_dir)

    if published: 
        pdate = published.strftime("%Y-%m-%d") 
    else: 
        pdate = '_'

    filename = _set_filename(pdate, title_)
    _file = os.path.join(dirname, filename)

    with open(_file, "w", encoding="utf-8") as f:
        if title_:
            f.write(f"# {title_}\n\n")
        f.write(f"source: {url}\n")
        f.write(f"published: {pdate}\n")
        f.write(f"scrapped: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(result.markdown.fit_markdown)
        f.write("\n")
        print(f'{filename} is written')

async def _crawl_news(query, kr, cutoff_months, max_result, show_res, dest_dir=None):
    items = await get_google_news_feed(
        query,
        kr_title=kr,
        cutoff_months=cutoff_months,
        max_result=max_result, 
        show_res=show_res,
        )

    async with AsyncWebCrawler() as crawler:
        tasks = [
            _crawl_url_and_save(crawler, i['url'], i['title'], i['published'], dest_dir)
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
        dest_dir=None,
    ):
    asyncio.run(_crawl_news(query, kr=kr, cutoff_months=cutoff_months, max_result=max_result, show_res=show_res, dest_dir=dest_dir))
