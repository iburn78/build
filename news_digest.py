#%%
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from scraper.tools.tools import COMPANYS_DIR, llm_selector
import os
from pathlib import Path

class CompanyRecentDevs(BaseModel):
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

    overall: str = Field(
        description="Single concise synthesis of all articles.",
        max_length=500,
    )

class NewsDigester:
    def __init__(self, mode='local'):
        # Basic parameters 
        self.retires = 3
        u, k, m = llm_selector(mode)

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
            output_type=CompanyRecentDevs,
            retries=self.retires,
        )

    def get_llm_response(self, code):
        news_collection = self._get_news_collection(code)

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

        res = self.agent.run_sync(request_text).output
        return res
    
    def _get_news_collection(self, code):
        _dest = Path(os.path.join(COMPANYS_DIR, code, 'overall'))

        combined = "\n".join(
            md_file.read_text(encoding="utf-8")
            for md_file in sorted(_dest.glob("*.md"))
        )

        return combined

if __name__=="__main__": 
    code = '000660'
    # nd = NewsDigester(mode='openai')
    nd = NewsDigester(mode='ollama')
    res = nd.get_llm_response(code)
    print(res)