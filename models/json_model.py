from __future__ import annotations
from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, PrivateAttr, Field
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai import Agent, WebSearchTool
from pydantic_ai.usage import UsageLimits
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.settings import ModelSettings
from openai import AsyncOpenAI
from datetime import datetime, timedelta
from typing import Any, ClassVar
import json
import sys
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor
from build.tools.tools import sanitized_filename
from build.models.settings import (
    BUILD_DIR,
    COLLECT_NEWS,
    DEFAULT_NEWS_LLM,
    DEFAULT_RESEARCH_LLM,
    llm_selector,
    FINANCIALS_UPDATE_PERIOD_HR,
    NUM_THREAD_TO_RUN,
    NEWS_REFRESH_THRES, 
    NUM_TO_CRAWL, 
    NUM_TO_FEED_LLM,
    AGENT_RETRIES,
    SEARCH_CONTEXT_SIZE,
    USAGE_REQUEST_LIMIT,
    COLLECT_LLM_RESEARCH,
    LLM_RESEARCH_REFRESH_THRES,
    OLLAMA_WEB_SEARCH_MAX_ATTEMPTS,
    OLLAMA_WEB_SEARCH_RESULT_CONTENT_CHARS,
)
from build.tools.render_html import render_html
from build.tools.crawl_news import crawl_news

class InfoSection(BaseModel):
    # Stores information for human review.
    # Reviewed information is preserved when the JSON path matches.
    # An AI agent can generate this information when needed.
    reviewed: bool = False
    updated: str | None = None
    search_theme: list[str] = Field(default_factory=list)

    # Shared classification and notes fields.
    tags: str = ""
    notes: str = ""

class NewsModel(BaseModel):
    updated: str = ""

    def needs_refresh(self):
        if not self.updated:
            return True
        try:
            updated_at = datetime.fromisoformat(self.updated)
            if updated_at.tzinfo is not None:
                return True
            return datetime.now() - updated_at >= timedelta(days=NEWS_REFRESH_THRES)
        except (TypeError, ValueError):
            return True

class LLM_Manager(ABC):
    def __init__(self, news_type, news_mode=DEFAULT_NEWS_LLM, research_mode=DEFAULT_RESEARCH_LLM):
        self.news_agent = self._make_agent(llm_mode=news_mode, output_type=news_type)
        self.research_agent = self._make_agent(
            llm_mode=research_mode, output_type=str, web_search=True
        )

    def _make_agent(self, llm_mode, output_type, web_search=False):
        u, k, m = llm_selector(llm_mode)
        client = AsyncOpenAI(base_url=u, api_key=k)
        provider = OpenAIProvider(openai_client=client)

        if web_search and llm_mode not in {"openai", "ollama"}:
            raise ValueError(f"Web search is not configured for the LLM mode: {llm_mode}")

        model = OpenAIChatModel(model_name=m, provider=provider)
        capabilities = None
        model_settings: ModelSettings | None = None

        if web_search and llm_mode == "openai":
            model = OpenAIResponsesModel(model_name=m, provider=provider)
            capabilities = [NativeTool(WebSearchTool(search_context_size=SEARCH_CONTEXT_SIZE))]
            model_settings = {"tool_choice": "auto"}

        agent = Agent(
            model=model,
            output_type=output_type,
            retries=AGENT_RETRIES,
            capabilities=capabilities,
            model_settings=model_settings,
        )

        if web_search and llm_mode == "ollama":
            self._register_ollama_web_search(agent, k)

        return agent

    @staticmethod
    def _register_ollama_web_search(agent, api_key):
        """Register Ollama's hosted web-search API as an agent tool."""
        @agent.tool_plain(name="web_search")
        def web_search_tool(query: str, max_results: int = 5) -> str:
            """Search the web for current information relevant to the query."""
            if not api_key or api_key == "-":
                raise RuntimeError("An Ollama API key is required for web search")

            import requests

            for attempt in range(OLLAMA_WEB_SEARCH_MAX_ATTEMPTS):
                response = requests.post(
                    "https://ollama.com/api/web_search",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "query": query,
                        "max_results": max(1, min(max_results, 10)),
                    },
                    timeout=30,
                )
                if response.status_code != 429:
                    break
                if attempt == OLLAMA_WEB_SEARCH_MAX_ATTEMPTS - 1:
                    response.raise_for_status()

                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2 ** (attempt + 1)
                except ValueError:
                    delay = 2 ** (attempt + 1)
                time.sleep(min(delay, 60) + random.uniform(0, 0.5))

            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                return "No web search results found."

            return "\n\n".join(
                f"{item.get('title', 'Untitled')}\n{item.get('url', '')}\n"
                f"{str(item.get('content', ''))[:OLLAMA_WEB_SEARCH_RESULT_CONTENT_CHARS]}"
                for item in results
            )

    def gen_news(self, target: "JsonModel"):
        if not COLLECT_NEWS:
            return target.news

        print(f"Collecting news for {target.key}")
        news_collection = target.scrape_news()
        if not news_collection.strip():
            return None
        request_text = self._get_news_request_text(target, news_collection)
        try:
            res = self.news_agent.run_sync(request_text).output
        except Exception as e:
            print(f"News generation failed for {target.key}: {e}")
            return None

        res.updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        return res

    @abstractmethod
    def _get_news_request_text(self, target: "JsonModel", news_collection: str) -> str:
        ...

    @abstractmethod
    def _get_llm_research_request_text(self, target: "JsonModel") -> str:
        ...

    def get_llm_research(self, target: "JsonModel") -> str:
        request_text = self._get_llm_research_request_text(target)
        try:
            return self.research_agent.run_sync(
                request_text,
                usage_limits=UsageLimits(request_limit=USAGE_REQUEST_LIMIT),
            ).output
        except Exception as e:
            print(f"LLM research failed for {type(target).__name__} {target.key}: {e}")
            return ""

class JsonModel(BaseModel, ABC):
    # Base Pydantic model for subclasses.
    # Each instance has a JSON file that is validated when loaded.

    # Directory where json files are stored
    DIR: ClassVar[Path] # ClassVars is not included in json file, not validated when loading

    key: str # unqiue identifier within the DIR: generic string (e.g., comma, _, space, etc, allowed)
    filename: str # json filename (key_additional information)
    updated: str = ""
    llm_research_updated: str = ""

    # Define these fields in each subclass.
    # info_section: InfoSection 
    # news: NewsModel

    financials: dict | None = None
    # PrivateAttr is not included in the json file, not validated when loading
    _sub_items: dict = PrivateAttr(default_factory=dict)
    _subitems_financials_processed: list = PrivateAttr(default_factory=list)

    # Called after loading or creating an instance.
    def model_post_init(self, context: Any) -> None:
        self.filename = sanitized_filename(self.filename)
        return super().model_post_init(context)

    def get_json_path(self) -> Path:
        return self.DIR / f"{self.filename}.json"

    def get_llm_research_path(self) -> Path:
        return self.get_json_path().with_suffix(".md")

    def get_llm_research(self) -> str:
        path = self.get_llm_research_path()
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def save_llm_research(self, research: str | None = None) -> None:
        path = self.get_llm_research_path()
        if research and research.strip():
            path.write_text(research.strip() + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)

    def llm_research_needs_refresh(self) -> bool:
        path = self.get_llm_research_path()
        if not path.is_file():
            return True
        if not self.llm_research_updated:
            self.llm_research_updated = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        try:
            updated = datetime.fromisoformat(self.llm_research_updated)
            if updated.tzinfo is not None:
                return True
        except (TypeError, ValueError):
            updated = datetime.fromtimestamp(path.stat().st_mtime)
            self.llm_research_updated = updated.strftime("%Y-%m-%d %H:%M")
        return datetime.now() - updated >= timedelta(days=LLM_RESEARCH_REFRESH_THRES)

    def _refresh_llm_research(self) -> bool:
        if not COLLECT_LLM_RESEARCH:
            return False
        research = self.get_llm_research()
        timestamp_missing = not self.llm_research_updated
        needs_html = bool(research.strip()) and self.llm_research_html_needs_refresh(research)
        if not self.llm_research_needs_refresh():
            return needs_html or timestamp_missing
        print(f"Starting LLM research for {type(self).__name__} {self.key}")
        generated = self.llm_manager.get_llm_research(self)
        if not generated.strip():
            return needs_html
        self.save_llm_research(generated)
        self.llm_research_updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        return True

    def llm_research_html_needs_refresh(self, research: str) -> bool:
        import hashlib
        expected_hash = hashlib.sha256(research.strip().encode("utf-8")).hexdigest()
        html_path = self.get_json_path().with_suffix(".html")
        if not html_path.is_file():
            return True
        return f'data-research-hash="{expected_hash}"' not in html_path.read_text(encoding="utf-8")

    def save_to_file(self):
        self.updated = datetime.now().strftime("%Y-%m-%d %H:%M")
        jp = self.get_json_path()
        jp.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )
        print(f"Saved {type(self).__name__}: {jp}")

    def get_qualitative_dict(self) -> dict:
        # Return a dictionary for HTML rendering, including the InfoSection.
        s = type(self.info_section).__name__
        formatted = re.sub(r'(?<!^)([A-Z])', r'_\1', s).lower()
        return {
            formatted: self.info_section,
            "news": self.news,
        }

    def get_roma_codes(self) -> list[str]:
        """Return company keys used by ROMA; specialized models may override."""
        if hasattr(self, "profile_code"):
            return [self.profile_code]
        if hasattr(self, "code"):
            return [self.code]
        if hasattr(self, "listed_companies"):
            return [
                re.sub(r"\([A-Za-z]\)$", "", company.key)
                for company in self.listed_companies
            ]
        return []

    def get_roma_plot_items(self):
        """Return keys or prepared ROMA data entries for this model."""
        return self.get_roma_codes()

    @abstractmethod
    def get_news_dir(self) -> Path:
        ...

    @abstractmethod
    def get_search_key(self, sk) -> str:
        # \w preserves letters, numbers, and underscores, \s preserves whitespace.
        # replaces underscores and collapses multiple spaces into one.
        sk = re.sub(r'[^\w\s]', ' ', sk)
        sk = re.sub(r'[_\s]+', ' ', sk).strip()
        return sk

    def scrape_news(self):
        for theme in self.info_section.search_theme:
            crawl_news(
                f"{self.get_search_key()} {theme}",
                dest_dir=self.get_news_dir(),
                max_result=NUM_TO_CRAWL,
            )
        return self._get_news_collection()

    def _get_news_collection(self):
        news_dir = self.get_news_dir()
        if not news_dir.exists():
            return ""
        return "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(news_dir.glob("*.md"), reverse=True)[:NUM_TO_FEED_LLM]
        )

    # Child items are populated by get_item after update inputs are applied.
    def get_subitems(self): 
        return self._sub_items

    # Create or update child items.
    @abstractmethod
    def _get_subitems(self):
        # recursively refresh sub_items and perform cleanup if necessary
        ...

    def _update_financials(self, **kwargs) -> bool:
        if self.financials is None:
            return True

        updated = self.financials["meta"]["updated"]
        updated_at = datetime.fromisoformat(updated)
        if datetime.now() - updated_at > timedelta(hours=FINANCIALS_UPDATE_PERIOD_HR):
            return True

        return any(
            item.financials
            and datetime.fromisoformat(item.financials["meta"]["updated"]) > updated_at
            for item in self.get_subitems().values()
        )

    def _get_subitems_financials(self):
        res = []
        for k, v in self._sub_items.items():
            res.append(v.financials)
        return res

    @abstractmethod
    def _get_financials(self, **kwargs):
        ...

    @abstractmethod
    def _update(self, **kwargs) -> bool:
        # perform update in self if content needs refresh
        # Return True if the item changed; get_item handles saving.
        ...

    @classmethod
    @abstractmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs) -> JsonModel:
        # Create a valid model, reusing existing JSON data when available.
        # get_item handles saving.
        ...

    @classmethod
    def _get_json_path_from_prefix(cls, prefix: str) -> Path | None: 
        prefix = sanitized_filename(prefix).lower()
        paths = list(cls.DIR.glob("*.json"))

        # Prefer an exact key match before considering longer keys with this
        # prefix (for example, "메모리" must resolve before "메모리_기판").
        exact_matches = [p for p in paths if p.stem.lower() == prefix]
        if len(exact_matches) == 1:
            return exact_matches[0]

        prefix_matches = [
            p for p in paths
            if p.stem.lower().startswith(f"{prefix}_")
        ]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        if len(prefix_matches) > 1 or len(exact_matches) > 1:
            print(f"Could not resolve JSON file for prefix: {prefix}")
        return None

    # Do not call directly; child items are not populated.
    @classmethod
    def _load_from_path(cls, path: str | Path) -> JsonModel | None:
        path = Path(path)
        try:
            # default: extra = "ignore"
            obj = cls.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as e:
            print(f"JSON model validation failed for {path}: {e}")
            obj = None
        return obj

    # Assumes there is one info section and one financials section.
    @classmethod
    def _extract_from_json(cls, existing_json = None):
        info_section_instance = None

        if existing_json:
            info_section = existing_json.get(cls.info_section.__name__.lower())
            if info_section and info_section.get('reviewed'): 
                try: 
                    info_section_instance = cls.info_section.model_validate(info_section) 
                except Exception as e:
                    pass

        return info_section_instance

    # Get an item, updating it when needed and loading reviewed information
    # and financials when available.
    @classmethod
    def get_item(cls, key, **kwargs):
        json_path = cls._get_json_path_from_prefix(key)
        created = False

        if json_path:
            item = cls._load_from_path(json_path)

            if item:
                print(f"{cls.__name__} JSON loaded: {json_path}")
                changed = item._update(**kwargs)
                if changed:
                    print(f"Updated existing JSON for {key}")
            else: 
                # Recover reusable data from JSON that failed validation.
                print(f"Replacing invalid JSON for {key}")
                try: 
                    existing_json = json.loads(json_path.read_text(encoding="utf-8"))
                    isection = cls._extract_from_json(existing_json)
                except:
                    isection = None

                item = cls._create_new_item(key, isection, **kwargs)
                changed = True
                created = True

        else:
            print(f"Creating new json for {key}")
            item = cls._create_new_item(key, None, **kwargs)
            changed = True
            created = True

        if created:
            item._refresh_llm_research()
            
        if changed: 
            item.save_to_file()
            item.create_html()

        return item

    # batch processing on get_item()
    # python 3.14 + pydantic_ai on windows yield: asyncio ProactorEventLoop / overlapped I/O cleanup errors, etc. 
    @classmethod
    def batch_process(cls, keylist, max_workers=NUM_THREAD_TO_RUN):
        if sys.platform == "win32":
            print("--------------------------------------------------")
            print("Generating items sequentially on Windows")
            print("--------------------------------------------------")
            for key in keylist:
                cls.get_item(key)
            return
        print("--------------------------------------------------")
        print(f"Generating items with up to {max_workers} threads")
        print("--------------------------------------------------")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(cls.get_item, keylist))

    @abstractmethod
    def _get_name(self)->str:
        ...

    def _get_html_link(self):
        html_root = BUILD_DIR
        return self.get_json_path().with_suffix('.html').relative_to(html_root)

    def create_html(self):
        _list = [self] + list(self._sub_items.values())
        financials_names = [
            {
                'name': item._get_name(),
                'link': item._get_html_link(), 
                'segment_name': getattr(item, 'segment_name', None),
            }
            for item in _list
        ]
        financials_dicts = [self.financials] + self._subitems_financials_processed
        qual_dict = self.get_qualitative_dict()
        research_getter = getattr(self, "get_llm_research", None)
        llm_research = research_getter() if callable(research_getter) else ""
        roma_plot_items = self.get_roma_plot_items()
        news_dir = self.get_news_dir() 
        output_file = self.get_json_path().with_suffix('.html')

        render_html(type(self).__name__, 
                    self.key, 
                    financials_names, 
                    financials_dicts, 
                    qual_dict, 
                    news_dir, 
                    output_file, 
                    info_section_validator=type(self.info_section),
                    llm_research=llm_research,
                    llm_research_updated=getattr(self, "llm_research_updated", ""),
                    show_research_delete=callable(research_getter),
                    roma_codes=roma_plot_items)
