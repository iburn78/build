#%% 
from pydantic import BaseModel, Field
from dataclasses import dataclass, asdict
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from scraper.tools import get_name, get_business_summary, df_krx
from crawl_news import crawl_news
from datetime import datetime, timedelta
import os, json
from pathlib import Path

cd_ = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(cd_, 'data/profiles')
os.makedirs(PROFILES_DIR, exist_ok=True)

@dataclass
class CompanyProfile:
    code: str
    name: str
    source_date: str
    updated: str

    key_theme: str
    business_segments: list[str]
    key_products: list[str]
    competitors: list[str]
    # reviewed: bool # to be implemented later

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

class CompanyAttributes(BaseModel):
    key_theme: str 

    business_segments: list[str] = Field(
        description="Core business areas of the company (NOT competitors or products)",
        max_length=3
    )

    key_products: list[str] = Field(
        description="Actual products or services offered by the company",
        max_length=3
    )

    competitors: list[str] = Field(
        description="Direct competing companies in the same industry",
        max_length=2
    )

    # valuechain: list[str] # to be designed and implemented later

class CompanyScraper:
    def __init__(self):
        # Basic parameters 
        self.crawl_max_results = 3        

        self.client = AsyncOpenAI(
            base_url='http://localhost:11434/v1',
            api_key='-'
        )

        self.model = OpenAIChatModel(
            model_name='gemma4',
            provider=OpenAIProvider(openai_client=self.client),
        )

        self.agent = Agent(
            model=self.model,
            output_type=CompanyAttributes,
        )

        self._profile_dict = {} 
        self.load_profiles()
    
    def load_profiles(self, threshold_to_renew=120):
        for path in Path(PROFILES_DIR).glob("*.json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            updated = datetime.fromisoformat(data["updated"])

            if datetime.now() - updated < timedelta(days=threshold_to_renew):
                profile = CompanyProfile(**data)
                self._profile_dict[profile.code] = profile
            else: 
                # may revise logic here, as profiles can be manually adjusted and then not renewing them might be better
                print(f"existing profile for {data['code']} is outdated (threshold: {threshold_to_renew} days) - ignored")

    def get_profile(self, code):
        cp = self._profile_dict.get(code)

        if cp is None:
            print(f"creating profile for code {code}")
            info = get_business_summary(code) # scrapping from fnguide

            request_text = f"""
Extract company profile.

Current theme: {info["title"]}

Refer to the recent business summary:
{info["summary"]}

Rules:
- key_theme: summarize "Current Theme" to 3-5 words
- business_segments: extract 1–3 core business areas 
- key_products: extract 1–3 representative products/services 
- competitors: at most 2 competitors (only specific company names) 
- Keep answers concise and structured.
- Use Korean terminology when it is standard in Korea; otherwise use English.
"""

            attrs = self.agent.run_sync(request_text).output

            name = get_name(code)
            source_date = str(info['date'])
            updated = datetime.today().strftime("%Y-%m-%d")

            cp = CompanyProfile(
                code=code,
                name=name,
                source_date = source_date,
                updated = updated,

                key_theme=attrs.key_theme,
                business_segments=attrs.business_segments,
                key_products=attrs.key_products,
                competitors=attrs.competitors,
            )

            # placement / quality checker ---------------------------------------------------------------------------
            # may let LLM to check the quality of output, and if not good, fix or rerun until satisfactory
            # --------------------------------------------------------------------------------------------
            cp.save_to_file()
            self._profile_dict[code] = cp

        return cp
    
    def generate_news(self, code):
        profile = self.get_profile(code)

        # USE FORMAL KEYWORDS 
        search_set = [profile.key_theme, '실적']


        # under company code as dir name: subdirs are ...
        dir_name_set = ['overall', 'performance']

        for k, d in zip(search_set, dir_name_set):        
            _request = profile.name + ' ' + k
            _dest = os.path.join(profile.code, d)
            crawl_news(_request, max_result=self.crawl_max_results, destination=_dest)

        # If not satisfactory, then may refine search using keywords
        pass

if __name__ == "__main__":
    code = '000660'
    cs = CompanyScraper()
    cs.generate_news(code)