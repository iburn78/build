from pydantic import BaseModel, Field
from build.tools.crawl_news import crawl_news
from build.tools.tools import get_name, get_overview, PROFILES_DIR, NEWS_DIR
from build.models.json_models import JsonModel, JsonModelManager, InfoSection
from datetime import datetime, timedelta
import os
from pathlib import Path

OVERVIEW_REFRESH_THRES = 30 # days
NEWS_REFRESH_THRES = 3 # days
MAX_SEGMENTS = 3
MAX_PRODUCTS = 3
MAX_COMPETITORS = 3

DEFAULT_SEARCH_THEME = ['실적', '전망']
NUM_TO_CRAWL = 3 # number of articles to crawl for each keyword
NUM_TO_FEED_LLM = 5 # number of articles to provide to LLM

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

class Business(InfoSection):
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

class CompanyProfile(JsonModel):
    DIR = PROFILES_DIR
    code: str

    overview: Overview 
    business: Business 
    news_summary: News | None = None
    financials: dict | None = None

    def save_to_file(self, prefix=None):
        if prefix is None: prefix = self.code
        return super().save_to_file(prefix)

    # over-riding load-all dict key to code
    def key(self) -> str:
        return self.code

    def scrape_news(self):
        search_set = self.business.search_theme + DEFAULT_SEARCH_THEME
        search_set = [f"{self.business.search_specifier} {k}" if self.business.search_specifier else k for k in search_set]
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

class ProfileManager(JsonModelManager):
    MODEL = CompanyProfile

    def __init__(self, biz_mode='local', news_mode='ollama'): 
        self.business_agent = self._make_agent(llm_mode=biz_mode, output_type=Business)
        self.news_agent = self._make_agent(llm_mode=news_mode, output_type=News)
        super().__init__()

    # key: code
    def _validate_key(self, key):
        if len(key) != 6 or not key[0].isdigit():
            raise ValueError(f"Invalid key: {key}")

    def _create_new_item(self, key, existing_json: dict | None = None, **kwargs) -> CompanyProfile:
        bs, fs = self._extract_from_json(key, existing_json, 'business', Business)

        ov = Overview.fetch(key)
        if bs is None: 
            bs = self._gen_business(ov)

        profile = CompanyProfile(
            code=key,
            name=get_name(key),
            overview=ov,
            business=bs,
            financials=fs,
        )
        # news summary is filled after profile creation
        profile.news_summary = self._gen_news(profile)

        return profile

    def _update(self, item) -> bool:
        changed = False
        if item.overview.needs_refresh():
            print(f"Updating overview for {item.code}")
            item.overview = Overview.fetch(item.code)

            if not item.business.reviewed:
                item.business = self._gen_business(item.overview)
            changed = True

        if item.news_summary is None or item.news_summary.needs_refresh():
            print(f"Generating news_summary for {item.code}")
            item.news_summary = self._gen_news(item)
            changed = True

        return changed


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
        try:
            res = self.news_agent.run_sync(request_text).output   # CompanyRecentDevs class instance
        except Exception as e:
            print(f"News generation failed for {profile.code}: {e}")
            return None

        res.updated = datetime.now().strftime("%Y-%m-%d") 
        return res

if __name__ == "__main__":
    pm = ProfileManager(biz_mode='ollama', news_mode='ollama')
    # single code
    code = '001570'
    profile = pm.get_item(code)

    # multiple codes
    codelist = ['001520', '251970', '020150', '055490', '950160', '000660', '005930', '021240', '462980', '011200']
    pm.batch_process(codelist)

    # from component
    # cm = ComponentManager()
    # codelist = cm.get_item('Memory').get_codelist()
    # pm.batch_process(codelist)
