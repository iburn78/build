#%% 
from pydantic import BaseModel, Field
from dataclasses import dataclass, asdict
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from scraper.tools.tools import get_name, get_business_summary
from scraper.tools.crawl_news import crawl_news
from scraper.tools.tools import PROFILES_DIR, llm_selector
from datetime import datetime, timedelta
import os, json
from pathlib import Path

BIZ_SUMMARY_REFRESH_PERIOD = 60 # days
MAX_BUSINESS_AREAS = 3
MAX_PRODUCTS = 3
MAX_COMPETITORS = 3

@dataclass
class CompanyProfile:
    code: str
    name: str

    # crawled from fnguide
    key_theme: str
    business_summary: str
    updated: str  # date for key_theme and business_summary

    # LLM generated with pydantic
    business_segments: list[str]
    key_products: list[str]
    competitors: list[str]
    reviewed: bool = False # if true, do not regenerate LLM part

    def save_to_file(self):
        """Save profile as {code}.json."""
        path = os.path.join(PROFILES_DIR, f"{self.code}.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                asdict(self),
                f,
                ensure_ascii=False,
                indent=2,
            )
    
    def needs_refresh(self):
        updated = datetime.fromisoformat(self.updated)
        return datetime.now() - updated > timedelta(days=BIZ_SUMMARY_REFRESH_PERIOD)


class CompanyAttributes(BaseModel):
    business_segments: list[str] = Field(
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

class CompanyScraper:
    def __init__(self, mode='local'):
        # Basic parameters 
        self.crawl_max_results = 3
        self.retires = 3
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
            output_type=CompanyAttributes,
            retries=self.retires,
        )

        self._profile_dict = {} 
        self.load_profiles()
    
    def load_profiles(self):
        for path in Path(PROFILES_DIR).glob("*.json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = CompanyProfile(**data)
            self._profile_dict[profile.code] = profile

    def get_profile(self, code):
        cp: CompanyProfile | None = self._profile_dict.get(code)

        if cp is None:
            print(f'creating new profile for {code}')
            info = get_business_summary(code) 
            attrs = self._get_llm_part(info)

            cp = CompanyProfile(
                code=code,
                name=get_name(code),

                key_theme=str(info['title']),
                business_summary=str(info['summary']),
                updated = str(info['date']),

                business_segments=attrs.business_segments,
                key_products=attrs.key_products,
                competitors=attrs.competitors,
                reviewed=False,
            )
            
        elif cp.needs_refresh():
            print(f'updating profile for {code}')
            info = get_business_summary(code) 
            cp.key_theme=str(info['title'])
            cp.business_summary=str(info['summary'])
            cp.updated = str(info['date'])
            if not cp.reviewed:
                attrs = self._get_llm_part(info)
                cp.business_segments=attrs.business_segments
                cp.key_products=attrs.key_products
                cp.competitors=attrs.competitors

        cp.save_to_file()
        self._profile_dict[code] = cp

        return cp
    
    def _get_llm_part(self, info):

#----------------------------------------------------------------------------------------------------
            request_text = f"""
Extract a company profile from the recent business summary below.

{info['summary']}

Rules:
- business_segments: extract 1 to {MAX_BUSINESS_AREAS} core business areas.
- key_products: extract 1 to {MAX_PRODUCTS} representative products or services.
- competitors: list up to {MAX_COMPETITORS} direct competitors. Use company names only.
- Keep answers concise and structured.
- Use Korean terminology when it is standard in Korean business language; otherwise use English.
"""
#----------------------------------------------------------------------------------------------------

            attrs = self.agent.run_sync(request_text).output
            return attrs

    def generate_news(self, code):
        profile = self.get_profile(code)

        # USE FORMAL KEYWORDS 
        search_set = [profile.key_theme, '실적']

        # Dest Dir: code as dir name
        _dest = profile.code

        # under company code as dir name: subdirs are ...
        subdir_set = ['overall', 'performance']

        for k, d in zip(search_set, subdir_set):        
            _request = profile.name + ' ' + k
            _dest_dir = os.path.join(_dest, d)
            crawl_news(_request, max_result=self.crawl_max_results, dest_dir=_dest_dir)

        # If not satisfactory, then may refine search using keywords
        pass

if __name__ == "__main__":
    code = '000660'
    cs = CompanyScraper()
    cs.generate_news(code)