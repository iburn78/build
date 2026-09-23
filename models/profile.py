import os
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import ClassVar
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from build.models.json_models import JsonModel, InfoSection
from build.models.segment import Segment, FinancialsAdjuster
from build.tools.settings import llm_selector
from build.tools.settings import PROFILES_DIR, NEWS_DIR, get_name, DEFAULT_BIZ_LLM, DEFAULT_NEWS_LLM, get_FN_GUIDE_url
from build.tools.crawl_news import crawl_news

OVERVIEW_REFRESH_THRES = 30 # days
NEWS_REFRESH_THRES = 3 # days
MAX_SEGMENTS = 3
MAX_PRODUCTS = 3
MAX_COMPETITORS = 3

DEFAULT_SEARCH_THEME = ['실적', '전망']
NUM_TO_CRAWL = 3 # number of articles to crawl for each keyword
NUM_TO_FEED_LLM = 5 # number of articles to provide to LLM
AGENT_RETRIES = 5 

class Overview(BaseModel):
    # crawled from fnguide
    title: str 
    desc: str 
    as_of: str # date fnguide created title/desc; yyyy-mm-dd
    updated: str # date current overview is updated: yyyy-mm-dd

    def needs_refresh(self): 
        return (
            datetime.now() - datetime.fromisoformat(self.updated)
            >= timedelta(days=OVERVIEW_REFRESH_THRES)
        )

    @classmethod
    def fetch(cls, code):
        url = get_FN_GUIDE_url(code)

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        r = requests.get(
            url,
            headers=headers,
            timeout=10,
        )

        r.raise_for_status()

        soup = BeautifulSoup(
            r.text,
            "html.parser",
        )

        title = soup.select_one(
            "#bizSummaryHeader"
        )

        date = soup.select_one(
            "#bizSummaryDate"
        )

        content = soup.select_one(
            "#bizSummaryContent"
        )

        desc = ""
        if content:
            desc = "\n\n".join(
                li.get_text(
                    " ",
                    strip=True,
                )
                for li in content.select("li")
            )
        return cls(
            title = title.get_text(strip=True) if title else "", 
            desc = desc,
            as_of = date.get_text(strip=True).strip("[]").replace("/","-") if date else "", 
            updated = datetime.now().strftime("%Y-%m-%d")
        )

class Business(InfoSection):
    ###_ needs update
    segments: list[str] = Field(
        description="Core business areas of the company (NOT products or competitors)",
        max_length=MAX_SEGMENTS
    )
    segment_share: list[float] = Field(
        description="Relative revenue size of segments of this company (total is 1)",
        max_length=MAX_SEGMENTS
    )
    create_segments: bool = False
    key_products: list[str] = Field(
        description="Actual products or services offered by the company",
        max_length=MAX_PRODUCTS
    )
    competitors: list[str] = Field(
        description="Direct competing companies in the same industry",
        max_length=MAX_COMPETITORS
    )
    search_specifier: str | None = None # keyword specific to this company to add in all news search
    search_theme: list[str] = Field(default_factory=list)

class News(BaseModel):
    key_facts: list[str] = Field(
        description="Article-specific factual developments, explicitly stated.",
        min_length=1,
        max_length=5,
    )
    key_issues: list[str] = Field(
        description="Explicitly stated risks, issues, or uncertainties (include resolution only if stated).",
        min_length=1,
        max_length=5,
    )
    news_summary: str = Field(
        description="Single concise synthesis of all articles.",
        max_length=500,
    )
    updated: str = "" # give default so LLM not to generate a value for this field (also reassigned later)

    def needs_refresh(self):
        if self.updated:
            return (
                datetime.now() - datetime.fromisoformat(self.updated)
                >= timedelta(days=NEWS_REFRESH_THRES)
            )
        return True

class Profile_LLM_Manager:
    def __init__(self, biz_mode=DEFAULT_BIZ_LLM, news_mode=DEFAULT_NEWS_LLM): 
        self.business_agent = self._make_agent(llm_mode=biz_mode, output_type=Business)
        self.news_agent = self._make_agent(llm_mode=news_mode, output_type=News)

    def _make_agent(self, llm_mode, output_type): # llm_selector parameter - local, ollama, openai, etc
        u, k, m = llm_selector(llm_mode)
        client = AsyncOpenAI(base_url=u, api_key=k)
        model = OpenAIChatModel(
            model_name=m,
            provider=OpenAIProvider(openai_client=client),
        )
        return Agent(
            model=model,
            output_type=output_type,
            retries=AGENT_RETRIES,
        )

###_ needs update
    def _gen_business(self, overview: Overview) -> Business:
#----------------------------------------------------------------------------------------------------
        request_text = f"""
Extract a company profile from the recent business summary below.

{overview.desc}

Rules:
- segments: extract 1 to {MAX_SEGMENTS} core business areas.
- segment_share: estimate relative revenue size for each segment as a number, where the company total revenue is 1
- key_products: extract 1 to {MAX_PRODUCTS} representative products or services.
- competitors: list up to {MAX_COMPETITORS} direct competitors. Use company names only.
- Keep answers concise and structured.
- Use Korean terminology when it is standard in Korean business language; otherwise use English.
"""
#----------------------------------------------------------------------------------------------------
        # returns Business instance
        bs = self.business_agent.run_sync(request_text).output

        # ensure defaults again
        bs.create_segments = False
        bs.search_specifier = ""
        bs.search_theme = []
        bs.updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        bs.reviewed = False
        return bs

    def _gen_news(self, profile: Profile):
        news_collection = profile.scrape_news()
#----------------------------------------------------------------------------------------------------
        request_text = f"""
Summarize the news articles about the company.

Output must follow the schema.

Rules:
- Use only information explicitly stated in the text.
- Merge duplicate points across articles.
- Keep facts company-specific and time-specific.
- Write in Korean.

Articles:

{news_collection}
"""
#----------------------------------------------------------------------------------------------------
        try:
            res = self.news_agent.run_sync(request_text).output   # CompanyRecentDevs class instance
        except Exception as e:
            print(f"News generation failed for {profile.code}: {e}")
            return None

        res.updated = datetime.now().strftime("%Y-%m-%d") 
        return res

class Profile(JsonModel):
    DIR = PROFILES_DIR
    info_section_class = Business

    code: str
    name: str

    overview: Overview | None = None
    news_summary: News | None = None

    llm_manager: ClassVar[Profile_LLM_Manager] = Profile_LLM_Manager()

    def get_qualitative_dict(self):
        default = super().get_qualitative_dict()
        return default | {
            'overview': self.overview,
            'news_summary': self.news_summary,
        }

    def _build_sub_items_info(self):
        ###_ needs update (just incomplete/testing) 
        if self.info_section.reviewed and self.info_section.create_segments:
            for i, sg in enumerate(self.info_section.segments):
                id = chr(ord('A')+i) # 0 to A, 1 to B, etc
                key = self.code + f'({id})'
                self._sub_items_info[key] = {
                    'segment_name': sg,
                    'revenue_share': self.info_section.segment_share[i],
                } 

    def _cleanup_sub_items(self):
        # removing unnecessaries
        paths = [p for p in Path(self.DIR).glob("*.json") if p.name.startswith(self.key)]
        base = [self.get_json_path()] + [v.get_json_path() for v in self._sub_items.values()]
        to_remove = [p for p in paths if p not in base]
        # removing not only json, but also html, png, etc
        for p in to_remove:
            for _p in p.parent.glob(f"{p.stem}.*"):
                _p.unlink(missing_ok=True)

    def get_news_dir(self):
        paths = [
            p for p in Path(NEWS_DIR).glob("*")
            if p.is_dir() and p.name.startswith(f"{self.key}_")
        ]
        if len(paths) != 1:
            print(f"cannot find unique news dir with {self.key}...")
            return None 
        return paths[0]

    def _update(self, **kwargs):
        changed = False
        if self.overview.needs_refresh():
            print(f"Updating overview for {self.key}")
            self.overview = Overview.fetch(self.key)

            if not self.info_section.reviewed:
                self.info_section = self.llm_manager._gen_business(self.overview)
            changed = True

        if self.news_summary is None or self.news_summary.needs_refresh():
            print(f"Generating news_summary for {self.key}")
            self.news_summary = self.llm_manager._gen_news(self)
            changed = True

        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        ov = Overview.fetch(key)
        if isection is None: 
            isection = cls.llm_manager._gen_business(ov)

        name = get_name(key)
        filename = f"{key}_{name}"

        profile = Profile(
            key=key,
            filename=filename,
            code=key,
            name=name,
            overview=ov,
            info_section=isection,
        )
        # news summary is filled after profile creation
        profile.news_summary = cls.llm_manager._gen_news(profile)
        return profile

    def scrape_news(self):
        search_set = self.info_section.search_theme + DEFAULT_SEARCH_THEME
        search_set = [f"{self.info_section.search_specifier} {k}" if self.info_section.search_specifier else k for k in search_set]
        _code_name = self.code + '_' + self.name

        for k in search_set:
            _request = self.name + ' ' + k
            crawl_news(_request, dest_dir=_code_name, max_result=NUM_TO_CRAWL)

        return self._get_news_collection()

    def _get_news_collection(self):
        _code_name = self.code + '_' + self.name
        _dest = Path(os.path.join(NEWS_DIR, _code_name))

        # choose latest INPUT_FILE_NUM articles
        combined = "\n".join(
            md_file.read_text(encoding="utf-8")
            for md_file in sorted(_dest.glob("*.md"), reverse=True)[:NUM_TO_FEED_LLM]
        )

        return combined
