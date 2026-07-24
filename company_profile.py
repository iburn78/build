#%% 
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from scraper.tools.tools import get_name, get_overview
from scraper.tools.tools import PROFILES_DIR, NEWS_DIR, llm_selector
from scraper.tools.crawl_news import crawl_news
from datetime import datetime, timedelta
import os
from pathlib import Path

BIZ_SUMMARY_REFRESH_PERIOD = 30 # days
MAX_BUSINESS_AREAS = 3
MAX_PRODUCTS = 3
MAX_COMPETITORS = 3

NUM_TO_CRAWL = 7 # number of articles to crawl
NUM_TO_FEED_LLM = 5 # number of articles to provide to LLM
RETRIES = 3 

class Overview(BaseModel):
    # crawled from fnguide
    key_theme: str 
    description: str 
    updated: str 

    @classmethod
    def fetch(cls, code):
        info = get_overview(code)
        return cls(
            key_theme=info["title"], 
            description=info["desc"],
            updated=info["date"],
        )

    def needs_refresh(self): 
        if self.updated:
            return (
                datetime.now() - datetime.fromisoformat(self.updated)
                > timedelta(days=BIZ_SUMMARY_REFRESH_PERIOD)
            )
        return True

class Business(BaseModel):
    segments: list[str] = Field(
        description="Core business areas of the company (NOT products or competitors)",
        max_length=MAX_BUSINESS_AREAS
    )
    key_products: list[str] = Field(
        description="Actual products or services offered by the company",
        max_length=MAX_PRODUCTS
    )
    competitors: list[str] = Field(
        description="Direct competing companies in the same industry",
        max_length=MAX_COMPETITORS
    )
    reviewed: bool = False # if true, do not regenerate LLM part

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

class CompanyProfile(BaseModel):
    code: str
    name: str | None = None

    overview: Overview | None = None
    business: Business | None = None
    news_summary: News | None = None

    @classmethod
    def create(cls, code: str):
        cp = cls(code=code, name=get_name(code))
        cp.overview = Overview.fetch(code)
        cp.business =  ###_ 
        return cp

    def refresh_overview(self):

    def save_to_file(self): 
        path = Path(PROFILES_DIR) / f"{self.code}.json"

        path.write_text(
            self.model_dump_json(
                indent=4,
                exclude_none=True,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path):
        path = Path(path)
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def gen_business_info(self, mode='local'):
        # Basic parameters 
        u, k, m = llm_selector(mode)

        self.client = AsyncOpenAI(
            base_url=u,
            api_key=k,
        )

        self.model = OpenAIChatModel(
            model_name=m,
            provider=OpenAIProvider(openai_client=self.client),
        )

        self.agent = Agent(
            model=self.model,
            output_type=Business,
            retries=RETRIES,
        )

#----------------------------------------------------------------------------------------------------
        request_text = f"""
Extract a company profile from the recent business summary below.

{self.overview.description if self.overview else ''}

Rules:
- segments: extract 1 to {MAX_BUSINESS_AREAS} core business areas.
- key_products: extract 1 to {MAX_PRODUCTS} representative products or services.
- competitors: list up to {MAX_COMPETITORS} direct competitors. Use company names only.
- Keep answers concise and structured.
- Use Korean terminology when it is standard in Korean business language; otherwise use English.
"""
#----------------------------------------------------------------------------------------------------
        self.business = self.agent.run_sync(request_text).output

        return attrs

        for path in Path(PROFILES_DIR).glob("*.json"):
            profile = CompanyProfile.load_from_file(path)

    # returns profile if exists and is not outdated, otherwise creates
    def get_profile(self, code: str) -> CompanyProfile:
        cp = self._profile_dict.get(code)
        changed = False

        if cp is None:
            print(f"Creating new profile for {code}")

            info = get_overview(code)
            attrs = self._get_llm_part(info)

            business = Business(
                segments=attrs.segments,
                key_products=attrs.key_products,
                competitors=attrs.competitors,
            )

            cp = CompanyProfile(
                code=code,
                name=get_name(code),
                business=business,
            )

            self._profile_dict[code] = cp
            changed = True

        elif cp.needs_refresh():
            print(f"Updating profile for {code}")

            info = get_overview(code)

            cp.key_theme = info["title"]
            cp.business_summary = info["summary"]
            cp.updated = info["date"]

            if cp.business is None or not cp.business.reviewed:
                attrs = self._get_llm_part(info)
                business = Business(
                    segments = attrs.segments, 
                    key_products = attrs.key_products,
                    competitors = attrs.competitors,
                )
                cp.business = business

            changed = True

        if changed:
            cp.save_to_file()

        return cp

class NewsManager:
    def __init__(self, profile, mode='local'):
        self.profile: CompanyProfile = profile

        # Basic parameters 
        self.retires = 3
        u, k, m = llm_selector(mode)
        self.input_file_num = NUM_TO_FEED_LLM

        self.client = AsyncOpenAI(
            base_url=u,
            api_key=k,
        )

        self.model = OpenAIChatModel(
            # model_name='gemma4:31b-cloud',
            model_name=m,
            provider=OpenAIProvider(openai_client=self.client),
        )

        self.agent = Agent(
            model=self.model,
            output_type=News,
            retries=self.retires,
        )

    def get_llm_summary(self):
        news_collection = self._get_news_collection()
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
        res = self.agent.run_sync(request_text).output   # CompanyRecentDevs class instance
        print(res)
        self.profile.news_summary = res
        self.profile.save_to_file()

    def _get_news_collection(self, dest='performance'):
        _dest = Path(os.path.join(NEWS_DIR, self.profile.code, dest))

        # choose latest INPUT_FILE_NUM articles
        combined = "\n".join(
            md_file.read_text(encoding="utf-8")
            for md_file in sorted(_dest.glob("*.md"), reverse=True)[:self.input_file_num]
        )

        return combined

    def scrap_news(self):
        search_set = ['', '실적'] 

        # Dest Dir: code as dir name
        _dest = self.profile.code

        # under company code as dir name: subdirs are ...
        subdir_set = ['general', 'performance']

        for k, d in zip(search_set, subdir_set):        
            _request = self.profile.name + ' ' + k
            _dest_dir = os.path.join(_dest, d)
            crawl_news(_request, dest_dir=_dest_dir, max_result=NUM_TO_CRAWL)

        # If not satisfactory, then may refine search using keywords
        pass

if __name__ == "__main__":
    code = '000660'
    # code = "950160" # 코티
    pm = ProfileManager()
    profile = pm.get_profile(code)

    nm = NewsManager(profile, mode='ollama')
    # nm = NewsManager(profile, mode='openai')
    # nm.scrap_news()
    nm.get_llm_summary()