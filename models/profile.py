import shutil
import hashlib
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Any, ClassVar
from pydantic import BaseModel, Field
from build.models.json_model import (
    JsonModel,
    InfoSection,
    NewsModel,
    LLM_Manager,
)
from build.models.segment import Segment
from build.tools.tools import ListedCompany, get_id, get_name, get_FN_GUIDE_url
from build.models.settings import (
    PROFILES_DIR,
    PROFILE_NEWS_DIR,
    DEFAULT_BIZ_LLM,
    DEFAULT_RESEARCH_LLM,
    COLLECT_LLM_RESEARCH,
    LLM_RESEARCH_REFRESH_THRES,
    OVERVIEW_REFRESH_THRES,
    MAX_SEGMENTS,
    PROFILE_SEARCH_THEME,
)
from build.analysis.sector_analysis import FinancialsData, SectorAnalysis

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
            updated = datetime.now().strftime("%Y-%m-%d %H:%M"),
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
    opmargin: list[float | None] = Field(
        default_factory=list,
        description="Operating margin for each segment as a ratio; null when unavailable"
    )
    trend: list[str] = Field(
        default_factory=list,
        description="Brief outlook or recent direction for each segment, in segment order"
    )
    create_segments: bool = False
    key_products: list[str] = Field(
        default_factory=list,
        description="Products or services for each segment, in segment order; combine multiple items in one comma-separated string"
    )
    competitors: list[str] = Field(
        default_factory=list,
        description="Direct competitors for each segment, in segment order; combine multiple names in one comma-separated string"
    )

    def model_post_init(self, context: Any) -> None:
        if not self.reviewed:
            self.search_theme = PROFILE_SEARCH_THEME
        return super().model_post_init(context)

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
    def __init__(self, biz_mode=DEFAULT_BIZ_LLM, llm_research_mode=DEFAULT_RESEARCH_LLM):
        self.business_agent = self._make_agent(llm_mode=biz_mode, output_type=Business)
        super().__init__(news_type=News, research_mode=llm_research_mode)

    def gen_business(self, overview: Overview, llm_research: str = "") -> Business | None:
#----------------------------------------------------------------------------------------------------
        request_text = f"""
Extract a company profile from the recent business summary below.

{overview.desc}

{llm_research}

Rules:
- For segments, identify 1 to {MAX_SEGMENTS} of the company's core business areas. Do not list products or competitors as segments.
- Return revenue_share as one numeric fraction per segment, in segment order, totaling 1. Estimate from the provided information when exact shares are unavailable.
- Return opmargin as one operating-margin fraction per segment (for example, 0.12 means 12%). Use null when research does not support an estimate; do not use the company-wide margin.
- Return trend as one brief outlook for each segment, in segment order, using concise phrases such as improving, stable, declining, or facing stronger competition.
- Return key_products as one string per segment, in segment order. Put multiple representative products or services in a comma-separated string.
- Return competitors as one string per segment, in segment order. Put multiple direct competitor company names in a comma-separated string.
- Keep segments, revenue_share, opmargin, trend, key_products, and competitors aligned by index and equal in length.
- Keep the answers concise and structured.
- Use Korean terminology when it is standard in Korean business language; otherwise, use English.
"""
#----------------------------------------------------------------------------------------------------
        # return Business instance
        try:
            bs = self.business_agent.run_sync(request_text).output
        except Exception as e:
            print(f"Could not generate business overview {overview.title[:30]}: {e}")
            return None

        # ensure defaults again
        bs.tags = ""
        bs.notes = ""
        bs.create_segments = False
        bs.search_theme = PROFILE_SEARCH_THEME
        bs.updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        bs.reviewed = False

        return bs

    def _get_llm_research_request_text(self, target: JsonModel) -> str:
#----------------------------------------------------------------------------------------------------
        request_text = f"""
한국 상장사 {target.name} 에 대한 아래 질문에 인터넷 검색해서 답변:

- 회사의 가장 중요한 사업부는 어떻게 나눌수 있는가? (3-5개)
- 각 사업부의 최근 매출과 영업이익, 영업이익률 조사
- 각 사업부 매출 및 영업이익이 분기별로 증가세였는지, 하락세였는지?
- 각 사업부별 경쟁사는 어디이고, 경쟁사 중에서서 상장사가 있다면 평균 PER는?
- 각 사업부별 주요 이슈 또는 리스크는?

한국어 Markdown 으로 답변할것
"""
#----------------------------------------------------------------------------------------------------
        return request_text

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
    llm_research_updated: str = ""
    llm_manager: ClassVar[Profile_LLM_Manager] = Profile_LLM_Manager()

    def _get_name(self):
        return self.name

    def get_qualitative_dict(self):
        return {
            "Business": self.info_section,
            "news": self.news,
            "overview": self.overview,
        }

    def llm_research_needs_refresh(self) -> bool:
        path = self.get_llm_research_path()
        if not path.is_file():
            return True

        # Older profiles have no saved research timestamp; use the Markdown
        # file's modification time as their initial timestamp.
        if not self.llm_research_updated:
            self.llm_research_updated = datetime.fromtimestamp(
                path.stat().st_mtime
            ).strftime("%Y-%m-%d %H:%M")

        try:
            updated = datetime.fromisoformat(self.llm_research_updated)
            if updated.tzinfo is not None:
                return True
        except (TypeError, ValueError):
            updated = datetime.fromtimestamp(path.stat().st_mtime)
            self.llm_research_updated = updated.strftime("%Y-%m-%d %H:%M")

        return datetime.now() - updated >= timedelta(days=LLM_RESEARCH_REFRESH_THRES)

    def llm_research_html_needs_refresh(self, research: str) -> bool:
        if not research.strip():
            return False
        expected_hash = hashlib.sha256(research.strip().encode("utf-8")).hexdigest()
        html_path = self.get_json_path().with_suffix(".html")
        if not html_path.is_file():
            return True
        return f'data-research-hash="{expected_hash}"' not in html_path.read_text(encoding="utf-8")

    def get_news_dir(self):
        return PROFILE_NEWS_DIR / self.filename

    def get_search_key(self, sk=''):
        sk = self.name
        return super().get_search_key(sk)

    def _get_subitems(self):
        self._sub_items.clear()
        if self.info_section.reviewed and self.info_section.create_segments:
            # print(f"Creating or updating segments for profile {self.name}")
            for i, segment_name in enumerate(self.info_section.segments):
                id = chr(ord('A')+i) # 0 to A, 1 to B, etc
                key = self.code + f'({id})'

                revenue_share = self.info_section.revenue_share[i]
                opmargin = (
                    self.info_section.opmargin[i]
                    if i < len(self.info_section.opmargin)
                    else None
                )
                trend = (
                    self.info_section.trend[i]
                    if i < len(self.info_section.trend)
                    else ""
                )
                self._sub_items[key] = Segment.get_item(
                    key=key,
                    profile_name=self.name,
                    segment_name=segment_name,
                    revenue_share=revenue_share,
                    opmargin=opmargin,
                    trend=trend,
                )

        # Reconcile even when review or segment creation is disabled, so stale
        # segment files are removed when either setting is turned off.
        self._reconcile_sub_items()

    def _reconcile_sub_items(self):
        # Remove files for obsolete sub-items.
        paths = [p for p in self.DIR.glob("*.json") if p.name.startswith(self.key)]
        base = [self.get_json_path()] + [v.get_json_path() for v in self._sub_items.values()]
        to_remove = [p for p in paths if p not in base]
        # Remove JSON, HTML, PNG, and other generated files.
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
            p for p in PROFILE_NEWS_DIR.iterdir()
            if p.is_dir()
            and p.name.startswith(f"{self.key}(")
            and p.name not in active_news_dirs
        ]
        for p in stale_news_dirs:
            shutil.rmtree(p)

    def _get_financials(self, **kwargs):
        _sa = SectorAnalysis()
        _sa.meta['code'] = self.code
        _sa.meta['name'] = self.name

        fd_list = [FinancialsData(key=self.key)]
        _sa.process(fd_list, 
                    subitems_financials=self._get_subitems_financials(),
                    plot_path=False if kwargs.get("_defer_plot") else self.get_json_path().with_suffix('.png'),
                    defer_plot=kwargs.get("_defer_plot", False))
        self.financials = _sa.financials
        self._subitems_financials_processed = _sa._subitems_financials_processed
        self._pending_financials_analysis = _sa if kwargs.get("_defer_plot") else None

    def _update(self, **kwargs):
        overview_changed = False
        info_section_changed = False
        research_changed = False
        news_changed = False
        _info_section = kwargs.get('info_section')

        # Load or refresh research first so business generation below can use it.
        research = self.get_llm_research()
        research_file_exists = self.get_llm_research_path().is_file()
        research_timestamp_missing = research_file_exists and not self.llm_research_updated
        research_due = (
            COLLECT_LLM_RESEARCH
            and not self.llm_manager.research_disabled()
            and self.llm_research_needs_refresh()
        )
        if research_due:
            if not self.llm_manager.announce_research_start(self.name):
                research_due = False
        if research_due:
            generated_research = self.llm_manager.get_llm_research(self)
            if generated_research.strip():
                self.save_llm_research(generated_research)
                self.llm_research_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
                research = generated_research
                research_changed = True
        elif research and (
            research_timestamp_missing or self.llm_research_html_needs_refresh(research)
        ):
            research_changed = True

        if self.overview.needs_refresh():
            print(f"Updating overview for {self.key}")
            self.overview = Overview.fetch(self.key)
            overview_changed = True

        # Also accept HTML edits, even when the section is not reviewed.
        if _info_section:
            old_values = self.info_section.model_dump(exclude={"updated"})
            new_values = _info_section.model_dump(exclude={"updated"})
            if old_values != new_values:
                self.info_section = _info_section
                info_section_changed = True

        segment_count = len(self.info_section.segments)
        aligned_fields = (
            self.info_section.revenue_share,
            self.info_section.opmargin,
            self.info_section.trend,
            self.info_section.key_products,
            self.info_section.competitors,
        )
        business_needs_refresh = (
            segment_count == 0
            or any(len(values) != segment_count for values in aligned_fields)
        )
        if (
            not self.info_section.reviewed
            and not _info_section
            and (overview_changed or research_changed or business_needs_refresh)
        ):
            generated_business = self.llm_manager.gen_business(self.overview, research)
            if generated_business:
                self.info_section = generated_business
                info_section_changed = True

        if overview_changed or self.news is None or self.news.needs_refresh():
            print(f"Generating news for {self.key}")
            self.news = self.llm_manager.gen_news(self)
            news_changed = True

        # Build derived segments once, using the final info_section for this update.
        self._get_subitems()

        changed = overview_changed or info_section_changed or research_changed or news_changed

        if changed or self._update_financials(**kwargs):
            changed = self._refresh_financials_if_changed(**kwargs) or changed

        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        name = get_name(key)
        filename = f"{key}_{name}"
        ov = Overview.fetch(key)
        profile = Profile(
            key=key,
            filename=filename,
            code=key,
            name=name,
            overview=ov,
            info_section=isection if isection else Business(),
        )
        research = cls.llm_manager.get_llm_research(profile) if COLLECT_LLM_RESEARCH else ""
        if isection is None:
            _is_generated = cls.llm_manager.gen_business(ov, research)
            if _is_generated:
                isection = _is_generated
            else:
                isection = Business()

        profile.info_section = isection
        if research.strip():
            profile.save_llm_research(research)
            profile.llm_research_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Populate news after creating the instance.
        profile.news = cls.llm_manager.gen_news(profile)

        profile._get_subitems()
        # Populate financials after creating the profile.
        profile._get_financials(**kwargs)

        return profile

    # Overridden below.
    @classmethod
    def get_item(cls, key, **kwargs):
        try:
            listed_company = ListedCompany.from_key(key)
        except ValueError:
            listed_company = ListedCompany.from_name(key)

        code, id = get_id(listed_company.key)
        profile = super().get_item(code, **kwargs)
        if id:
            try:
                return profile.get_subitems()[listed_company.key]
            except:
                print(f"Segment {key} for {profile.name} is unavailable. Using the profile; rerun after reviewing the segments.")
        return profile
