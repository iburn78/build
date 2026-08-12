from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, ClassVar
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from scraper.tools.tools import llm_selector
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from scraper.tools.tools import sanitized_filename
AGENT_RETRIES = 3 
NUM_THREAD_TO_RUN = 4

class JsonModel(BaseModel, ABC):
    DIR: ClassVar[str] = "" # overridden by subclasses, and json does not include ClassVars / not validate either
    name: str
    updated: str = ""

    def model_post_init(self, context: Any) -> None:
        self.updated = datetime.now().strftime("%Y-%m-%d") # note this is updated even the content is not revised
        super().model_post_init(context)

    def save_to_file(self, prefix = None):
        filename = sanitized_filename(self.name)
        if prefix:
            filename = prefix+'_'+filename
        path = Path(self.DIR) / f"{filename}.json"
        path.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path):
        # default: extra = "ignore"
        return cls.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )

    def key(self) -> str:
        return self.name

    @classmethod
    def load_all_validated(cls) -> dict[str, "JsonModel"]:
        objects_dict = {}

        for path in Path(cls.DIR).glob("*.json"):
            try:
                obj = cls.load_from_file(path)
                objects_dict[obj.key()] = obj
            except Exception as e:
                print(f"Skipping {path}: {e}")

        return objects_dict


class JsonModelManager(ABC): 
    MODEL: type[JsonModel]

    def __init__(self):
        self._items = self.MODEL.load_all_validated()

    @abstractmethod
    def _create_new_item(self, key, existing_json: dict | None = None) -> JsonModel:
        # Create a valid MODEL with info from existing json if any
        ...

    @abstractmethod
    def _update(self, item) -> bool:
        # Return True if item content changed
        ...

    # override if needed
    def _validate_key(self, key):
        if key != sanitized_filename(key): 
            raise ValueError(f"Invalid key: {key}")

    def get_item(self, key):
        self._validate_key(key)
        item = self._items.get(key)

        # Case 1: if valid json is already loaded, then update and return
        if item is not None:
            changed = self._update(item)

        else: 
            _files = list(Path(self.MODEL.DIR).glob(f"{key}*.json"))
            if len(_files) > 1:
                raise ValueError(f"Expected one JSON for {key}, found {len(_files)}")

            # Case 2: json exists but wasn't loaded as valid model, which may contain info from other sources
            existing_json = None
            if _files:
                print(f"Importing existing json for {key}")
                existing_json = json.loads(_files[0].read_text(encoding="utf-8"))

            print(f"Creating new json for {key}")
            item = self._create_new_item(key, existing_json)
            changed = True

        if changed: 
            self._items[key] = item
            item.save_to_file()

        return item

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

    # batch processing on get_item()
    # python 3.14 + pydantic_ai on windows yield: asyncio ProactorEventLoop / overlapped I/O cleanup errors, etc. 
    def batch_process(self, keylist, max_workers=NUM_THREAD_TO_RUN):
        if sys.platform == "win32":
            print("--------------------------------------------------")
            print("Generating items - sequential on Windows")
            print("--------------------------------------------------")
            for key in keylist:
                self.get_item(key)
            return
        print("--------------------------------------------------")
        print(f"Generating items - max {max_workers} threads")
        print("--------------------------------------------------")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(self.get_item, keylist))



###_ move this ... 
# Component and ValueChain
class CV_Manager: 
    def __init__(self):
        self._components = Component.load_all_validated()
        self._valuechains = ValueChain.load_all_validated()

    def add_component(self, cp):
        ###_ this is just replacement, if exists then append necessary
        self._components[cp.name] = cp
        cp.save_to_file()

    def get_component(self, name) -> Component:
        ###_ this is just replacement, if exists then append necessary
        res = self._components.get(name)
        if res: 
            return res
        else:
            raise ValueError(f"no component exists: {name}")

    def add_valuechain(self, vc):
        # check if components are already defined
        ###_ check this too
        for c in vc.components:
            if c not in self._components.keys():
                raise ValueError(f"For valuechain '{vc.name}', component '{c}' is not defined in cvm (not found)")
        self._valuechains[vc.name] = vc
        vc.save_to_file()