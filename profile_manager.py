from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from scraper.tools.tools import get_name, get_overview, get_code_name, PROFILES_DIR, NEWS_DIR, llm_selector
from scraper.tools.models import JsonModel
from scraper.tools.crawl_news import crawl_news
from datetime import datetime, timedelta
import os, sys
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

OVERVIEW_REFRESH_THRES = 30 # days
NEWS_REFRESH_THRES = 3 # days
MAX_SEGMENTS = 3
MAX_PRODUCTS = 3
MAX_COMPETITORS = 3

DEFAULT_SEARCH_THEME = ['실적', '전망']
NUM_TO_CRAWL = 3 # number of articles to crawl for each keyword
NUM_TO_FEED_LLM = 5 # number of articles to provide to LLM

AGENT_RETRIES = 3 
NUM_THREAD_TO_RUN = 4

class Overview(BaseModel):
    # crawled from fnguide
    title: str 
    desc: str 
    as_of: str # date fnguide created title/desc; yyyy-mm-dd
    updated: str # date current overview is updated: yyyy-mm-dd

    @classmethod
    def fetch(cls, code):
        info = get_overview(code)
        return cls(
            title=info["title"], 
            desc=info["desc"],
            as_of=info["date"],
            updated=datetime.now().strftime("%Y-%m-%d"),
        )

    def needs_refresh(self): 
        return (
            datetime.now() - datetime.fromisoformat(self.updated)
            >= timedelta(days=OVERVIEW_REFRESH_THRES)
        )

class Business(BaseModel):
    segments: list[str] = Field(
        description="Core business areas of the company (NOT products or competitors)",
        max_length=MAX_SEGMENTS
    )
    key_products: list[str] = Field(
        description="Actual products or services offered by the company",
        max_length=MAX_PRODUCTS
    )
    competitors: list[str] = Field(
        description="Direct competing companies in the same industry",
        max_length=MAX_COMPETITORS
    )
    search_specifier: str = "" # keyword specific to this company to add in all news search
    search_theme: list[str] = Field(default_factory=list)
    updated: str # date current business is updated: yyyy-mm-dd
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
    updated: str = "" # give default so LLM not to generate a value for this field

    def needs_refresh(self):
        if self.updated:
            return (
                datetime.now() - datetime.fromisoformat(self.updated)
                >= timedelta(days=NEWS_REFRESH_THRES)
            )
        return True

class CompanyProfile(JsonModel):
    DIR = PROFILES_DIR
    code: str

    overview: Overview 
    business: Business 
    news_summary: News | None = None
    financials: dict | None = None

    # over-riding load-all dict key to code
    def key(self) -> str:
        return self.code

    def scrape_news(self):
        search_set = self.business.search_theme + DEFAULT_SEARCH_THEME
        search_set = [f"{self.business.search_specifier} {k}" if self.business.search_specifier else k for k in search_set]
        _code_name = get_code_name(self.code, self.name)

        for k in search_set:
            _request = self.name + ' ' + k
            crawl_news(_request, dest_dir=_code_name, max_result=NUM_TO_CRAWL)

        return self._get_news_collection()

    def _get_news_collection(self):
        _code_name = get_code_name(self.code, self.name)
        _dest = Path(os.path.join(NEWS_DIR, _code_name))

        # choose latest INPUT_FILE_NUM articles
        combined = "\n".join(
            md_file.read_text(encoding="utf-8")
            for md_file in sorted(_dest.glob("*.md"), reverse=True)[:NUM_TO_FEED_LLM]
        )

        return combined

# master class that has all profiles in data, and creates profiles if necessary 
class ProfileManager:
    def __init__(self, biz_mode='local', news_mode='ollama'): 
        # llm model for biz
        u, k, m = llm_selector(biz_mode) 
        biz_client = AsyncOpenAI(base_url=u, api_key=k) 
        biz_model = OpenAIChatModel(model_name=m, provider=OpenAIProvider(openai_client=biz_client)) 
        # agent
        self.business_agent = Agent(model=biz_model, output_type=Business, retries=AGENT_RETRIES) 

        # llm model for news
        u, k, m = llm_selector(news_mode) 
        news_client = AsyncOpenAI(base_url=u, api_key=k) 
        news_model = OpenAIChatModel(model_name=m, provider=OpenAIProvider(openai_client=news_client)) 
        # agent
        self.news_agent = Agent(model=news_model, output_type=News, retries=AGENT_RETRIES) 

        # profile dict 
        self._profiles = CompanyProfile.load_all_validated() 

    # batch processing of profile generation / update
    def gen_profiles(self, codes, max_workers=NUM_THREAD_TO_RUN):
        if sys.platform == "win32":
            print("--------------------------------------------------")
            print("Generating profiles - sequential on Windows")
            print("--------------------------------------------------")
            for code in codes:
                self.get_profile(code)
            return

        print("--------------------------------------------------")
        print(f"Generating profiles - max {max_workers} threads")
        print("--------------------------------------------------")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(self.get_profile, codes))
        
    # returns profile if exists and is not outdated, otherwise creates
    def get_profile(self, code: str) -> CompanyProfile:
        cp: CompanyProfile | None = self._profiles.get(code)
        changed = False

        if cp is None:
            CompanyProfile.DIR 
            # find json that contains info 1) either reviewed info and/or 2) from other sources
            _files = list(Path(CompanyProfile.DIR).glob(f"{code}*.json"))
            if len(_files) > 1:
                raise ValueError(f"Expected 1 file for {code}, found {len(_files)}")

            bs = None
            fs = None
            if len(_files) == 1: 
                print(f"Importing info from other sources for {code} and creating new profile")
                with open(_files[0], 'r', encoding="utf-8") as f:
                    existing_json = json.load(f)

                # RETRIEVING 1)
                business_section = existing_json.get('business')
                if business_section and business_section.reviewed:
                    bs = business_section

                # RETRIEVING 2)
                financials_section = existing_json.get('financials')
                if financials_section:
                    fs = financials_section
            else: 
                print(f"Creating new profile for {code}")

            ov = Overview.fetch(code)
            if bs is None: 
                bs = self._gen_business(ov)

            cp = CompanyProfile(
                code=code,
                name=get_name(code),
                overview=ov,
                business=bs,
                financials=fs,
            )
            self._profiles[code] = cp
            changed = True

        elif cp.overview.needs_refresh():
            print(f"Updating profile for {code}")
            cp.overview = Overview.fetch(code)

            if not cp.business.reviewed:
                cp.business = self._gen_business(cp.overview)
            changed = True

        if cp.news_summary is None or cp.news_summary.needs_refresh():
            print(f"Generating news for {code}")
            cp.news_summary = self._gen_news(cp)
            changed = True

        if changed:
            cp.save_to_file(prefix=code)

        return cp

    def _gen_business(self, overview: Overview):
#----------------------------------------------------------------------------------------------------
        request_text = f"""
Extract a company profile from the recent business summary below.

{overview.desc}

Rules:
- segments: extract 1 to {MAX_SEGMENTS} core business areas.
- key_products: extract 1 to {MAX_PRODUCTS} representative products or services.
- competitors: list up to {MAX_COMPETITORS} direct competitors. Use company names only.
- Keep answers concise and structured.
- Use Korean terminology when it is standard in Korean business language; otherwise use English.
"""
#----------------------------------------------------------------------------------------------------
        # returns Business instance
        bs = self.business_agent.run_sync(request_text).output
        # ensure defaults again
        bs.search_specifier = ""
        bs.search_theme = []
        bs.updated = datetime.now().strftime("%Y-%m-%d")
        bs.reviewed = False
        return bs

    def _gen_news(self, profile: CompanyProfile):
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
        res = self.news_agent.run_sync(request_text).output   # CompanyRecentDevs class instance
        res.updated = datetime.now().strftime("%Y-%m-%d") 
        return res

if __name__ == "__main__":
    pm = ProfileManager(biz_mode='ollama', news_mode='ollama')
    code = '251970'
    code = '011200'
    code = '020150'
    code = '021240'
    code = '009830'
    code = '001750'
    profile = pm.get_profile(code)

    # codes = ['001520', '251970'] #, '020150', '055490', '950160', '000660', '005930', '021240', '462980', '011200']
    # pm.gen_profiles(codes)
