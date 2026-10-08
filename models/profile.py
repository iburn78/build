import shutil
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import ClassVar
from pydantic import BaseModel, Field
from build.models.json_model import JsonModel, InfoSection, NewsModel, LLM_Manager
from build.models.segment import Segment
from build.tools.settings import PROFILES_DIR, PROFILE_NEWS_DIR, get_id, get_name, DEFAULT_BIZ_LLM, get_FN_GUIDE_url
from build.analysis.sector_analysis import FinancialsData, SectorAnalysis

OVERVIEW_REFRESH_THRES = 30 # days
MAX_SEGMENTS = 3
MAX_PRODUCTS = 3
MAX_COMPETITORS = 3
PROFILE_SEARCH_THEME = ['실적', '전망']

class Overview(BaseModel):
    # crawled from fnguide
    title: str
    desc: str
    as_of: str # date fnguide created title/desc; yyyy-mm-dd
    updated: str # current overview update time: yyyy-mm-dd HH:MM

    def needs_refresh(self):
        try:
            updated = datetime.fromisoformat(self.updated)
            age = datetime.now() - updated
        except (TypeError, ValueError):
            # Invalid or timezone-aware timestamps cannot be compared with
            # datetime.now(); treat them as stale so the overview is refreshed.
            return True

        return age >= timedelta(days=OVERVIEW_REFRESH_THRES)

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
            updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        )

class Business(InfoSection):
    segments: list[str] = Field(
        default_factory=list,
        description="Core business areas of the company (NOT products or competitors)"
    )
    revenue_share: list[float] = Field(
        default_factory=list,
        description="Relative revenue size of segments of this company (total is 1)"
    )
    create_segments: bool = False
    key_products: list[str] = Field(
        default_factory=list,
        description="Actual products or services offered by the company"
    )
    competitors: list[str] = Field(
        default_factory=list,
        description="Direct competing companies in the same industry"
    )
    search_specifier: str = "" # keyword specific to this profile to add in all news search
    search_theme: list[str] = Field(default_factory=list)

class News(NewsModel):
    key_facts: list[str] = Field(
        description="Article-specific factual developments, explicitly stated.",
        min_length=0,
        max_length=5,
    )
    key_issues: list[str] = Field(
        description="Explicitly stated risks, issues, or uncertainties (include resolution only if stated).",
        min_length=0,
        max_length=5,
    )
    news_summary: str = Field(
        description="Single concise synthesis of all articles.",
        max_length=500,
    )

class Profile_LLM_Manager(LLM_Manager):
    def __init__(self, biz_mode=DEFAULT_BIZ_LLM):
        self.business_agent = self._make_agent(llm_mode=biz_mode, output_type=Business)
        super().__init__(news_type=News)

    def gen_business(self, overview: Overview) -> Business | None:
#----------------------------------------------------------------------------------------------------
        request_text = f"""
Extract a company profile from the recent business summary below.

{overview.desc}

Rules:
- For segments, identify 1 to {MAX_SEGMENTS} of the company's core business areas. Do not list products or competitors as segments.
- For revenue_share, estimate each segment's share of total company revenue as a number between 0 and 1. The shares should sum to 1 or less.
- For key_products, list 1 to {MAX_PRODUCTS} representative products or services.
- For competitors, list up to {MAX_COMPETITORS} direct competitors using company names only.
- Keep the answers concise and structured.
- Use Korean terminology when it is standard in Korean business language; otherwise, use English.
"""
#----------------------------------------------------------------------------------------------------
        # returns Business instance
        try:
            bs = self.business_agent.run_sync(request_text).output
        except Exception as e:
            print(f"Business generation failed for an overview {overview.title[:30]}: {e}")
            return None


        # ensure defaults again
        bs.create_segments = False
        bs.search_specifier = ""
        bs.search_theme = []
        bs.updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        bs.reviewed = False
        return bs

    def _get_news_request_text(self, target: JsonModel, news_collection: str):
#----------------------------------------------------------------------------------------------------
        request_text = f"""
Summarize the following news articles about the company.

Output must follow the schema.

Rules:
- Use only information explicitly stated in the articles.
- Merge duplicate points across articles.
- Keep each fact specific to the company and time-bound.
- Use empty lists when the articles contain no supported facts or issues.
- Write in Korean.

Articles:

{news_collection}
"""
#----------------------------------------------------------------------------------------------------
        return request_text

class Profile(JsonModel):
    DIR = PROFILES_DIR
    info_section: Business

    code: str
    name: str

    overview: Overview

    news: News | None = None
    llm_manager: ClassVar[Profile_LLM_Manager] = Profile_LLM_Manager()

    def _get_name(self):
        return self.name

    def get_qualitative_dict(self):
        default = super().get_qualitative_dict()
        return default | {
            'overview': self.overview,
            'news': self.news,
        }

    def get_news_dir(self):
        return Path(PROFILE_NEWS_DIR) / self.filename

    def scrape_news(self, query_prefix="", search_theme=[]):
        query_prefix = self.name
        search_theme = PROFILE_SEARCH_THEME
        return super().scrape_news(query_prefix, search_theme)

    def _get_subitems(self):
        self._sub_items.clear()
        if self.info_section.reviewed and self.info_section.create_segments:
            for i, segment_name in enumerate(self.info_section.segments):
                id = chr(ord('A')+i) # 0 to A, 1 to B, etc
                key = self.code + f'({id})'

                revenue_share = self.info_section.revenue_share[i]
                self._sub_items[key] = Segment.get_item(
                    key=key,
                    profile_name=self.name,
                    segment_name=segment_name,
                    revenue_share=revenue_share,
                )

        # Reconcile even when review or segment creation is disabled, so stale
        # segment files are removed when either setting is turned off.
        self._reconcile_sub_items()

    def _reconcile_sub_items(self):
        # removing unnecessary stall sub-item files
        paths = [p for p in Path(self.DIR).glob("*.json") if p.name.startswith(self.key)]
        base = [self.get_json_path()] + [v.get_json_path() for v in self._sub_items.values()]
        to_remove = [p for p in paths if p not in base]
        # removing not only json, but also html, png, etc
        for p in to_remove:
            for _p in p.parent.glob(f"{p.stem}.*"):
                _p.unlink(missing_ok=True)

        # Segment news directories are keyed by segment key and profile name.
        # Remove directories for segments that are no longer active, including
        # directories left behind when a segment name changes.
        active_news_dirs = {
            segment.filename
            for segment in self._sub_items.values()
        }
        stale_news_dirs = [
            p for p in Path(PROFILE_NEWS_DIR).iterdir()
            if p.is_dir()
            and p.name.startswith(f"{self.key}(")
            and p.name not in active_news_dirs
        ]
        for p in stale_news_dirs:
            shutil.rmtree(p)

    def _get_financials(self, **kwargs):
        _sa = SectorAnalysis()
        _sa.meta['name'] = self.name
        _sa.meta['code'] = self.code

        fd_list = [FinancialsData(key=self.key)]
        _sa.process(fd_list, 
                    subitems_financials=self._get_subitems_financials(),
                    plot_path=self.get_json_path().with_suffix('.png'))
        self.financials = _sa.financials
        self._subitems_financials_processed = _sa._subitems_financials_processed

    def _update(self, **kwargs):
        overview_changed = False
        info_section_changed = False
        news_changed = False
        _info_section = kwargs.get('info_section')

        if self.overview.needs_refresh():
            print(f"Updating overview for {self.key}")
            self.overview = Overview.fetch(self.key)

            if not self.info_section.reviewed and not _info_section:
                _is_generated = self.llm_manager.gen_business(self.overview)
                if _is_generated:
                    self.info_section = _is_generated
            overview_changed = True

        # e.g., when info_section is modifed in the html (then replace with it even not reviewed)
        if _info_section:
            old_values = self.info_section.model_dump(exclude={"updated"})
            new_values = _info_section.model_dump(exclude={"updated"})
            if old_values != new_values:
                self.info_section = _info_section
                info_section_changed = True

        if overview_changed or self.news is None or self.news.needs_refresh():
            print(f"Generating news for {self.key}")
            self.news = self.llm_manager.gen_news(self)
            news_changed = True

        # Build derived segments once, using the final info_section for this update.
        self._get_subitems()

        changed = overview_changed or info_section_changed or news_changed

        if changed or self._update_financials(**kwargs):
            self._get_financials(**kwargs)
            changed = True

        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        name = get_name(key)
        filename = f"{key}_{name}"

        ov = Overview.fetch(key)
        if isection is None:
            _is_generated = cls.llm_manager.gen_business(ov)
            if _is_generated:
                isection = _is_generated
            else: 
                isection = Business()

        profile = Profile(
            key=key,
            filename=filename,
            code=key,
            name=name,
            overview=ov,
            info_section=isection,
        )
        # news is filled after instance creation
        profile.news = cls.llm_manager.gen_news(profile)

        profile._get_subitems()
        # financials is filled after profile creation
        profile._get_financials(**kwargs)

        return profile

    # below overrided
    @classmethod
    def get_item(cls, key, **kwargs):
        code, id = get_id(key)
        profile = super().get_item(code, **kwargs) # cause this is overrided
        if id:
            try:
                return profile.get_subitems()[key]
            except:
                print(f"Segment {key} of {profile.name} is not available. Profile is used instead - re-run after review segments.")
        return profile
