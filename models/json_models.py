from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, PrivateAttr
from datetime import datetime
from typing import Any, ClassVar
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from openai import AsyncOpenAI
from build.tools.settings import llm_selector
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from build.tools.settings import sanitized_filename

AGENT_RETRIES = 5 
NUM_THREAD_TO_RUN = 4

class JsonModel(BaseModel, ABC):
    # to provide a basic pydantic structure to subclasses
    # - a json file is maintained per a model instance
    # - data format is validated when loaded

    DIR: ClassVar[str] # ClassVars is not included in json file, not validate when loaded
    name: str # used as the json filename (except for a company profile: code_name)
    updated: str = ""
    _json_path: Path | None = PrivateAttr(default=None)

    def model_post_init(self, context: Any) -> None:
        self.name = sanitized_filename(self.name)
        return super().model_post_init(context)

    def save_to_file(self, prefix = None):
        filename = self.name
        if prefix: filename = prefix+'_'+filename

        path = Path(self.DIR) / f"{filename}.json"
        path.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )
        self._json_path = path

    @classmethod
    def load_from_file(cls, path: str | Path):
        path = Path(path)
        # default: extra = "ignore"
        obj = cls.model_validate_json(
            path.read_text(encoding="utf-8")
        )
        obj._json_path = path
        return obj

    # search within cls.DIR for a unique file starts with prefix...
    @classmethod
    def load_from_prefix(cls, prefix: str): 
        paths = list(Path(cls.DIR).glob(f"{prefix}*.json"))
        if len(paths) != 1:
            print(f"cannot load json file with prefix {prefix}...")
            return None 
        return cls.load_from_file(paths[0])

    def get_json_path(self) -> Path:
        if not self._json_path: 
            print("Instance doesn't have json file...") 
            return None
        return self._json_path

    def get_html_path(self) -> Path:
        return self.get_json_path().with_suffix('.html')

    # key for the json_model dict
    def key(self) -> str:
        return self.name

    # returns all instances in dict {key: json_model dict}
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

class InfoSection(BaseModel):
    # to provide human-review-needed information to JsonModels
    # - if reviewed == True, information survives through updates or (automatic) creations if filename matches
    # - if needed, AI agent will be provided
    reviewed: bool = False

class JsonModelManager(ABC): 
    # to load all JsonModel instances and to manage (get, update, create, etc)
    MODEL: type[JsonModel]

    def __init__(self):
        self._items = self.MODEL.load_all_validated()

    @abstractmethod
    def _create_new_item(self, key, existing_json: dict | None = None, **kwargs) -> JsonModel:
        # Create a valid MODEL with info from existing json if any
        ...

    def _update(self, item) -> bool:
        # Perform update if content needs refresh
        # and return True if item content changed
        return False

    # override if needed
    def _validate_key(self, key):
        if key != sanitized_filename(key): 
            raise ValueError(f"Invalid key: {key}")

    def get_itemlist(self) -> list[JsonModel]:
        return list(self._items.values())

    # main function to get an item from loaded
    # - if update needed, this will triger update 
    # - if reviewed info_section exists, this will load it
    # - if financials_section exists, this will load it
    def get_item(self, key, replace=False, **kwargs):
        self._validate_key(key)
        item = self._items.get(key)

        # Case 1: if valid json is already loaded, then update and return
        if item and not replace:
            changed = self._update(item)

        # Case 2: json exists but wasn't loaded as valid model, which may contain info from other sources
        else: 
            _files = list(Path(self.MODEL.DIR).glob(f"{key}*.json"))
            if len(_files) > 1:
                raise ValueError(f"Expected one JSON for {key}, found {len(_files)}")

            existing_json = None
            if _files:
                print(f"Importing existing json for {key}")
                existing_json = json.loads(_files[0].read_text(encoding="utf-8"))

            print(f"{"Replacing" if replace else "Creating"} new json for {key}")
            item = self._create_new_item(key, existing_json, **kwargs)
            changed = True

        if changed: 
            item.updated = datetime.now().strftime("%Y-%m-%d") 
            self._items[key] = item
            item.save_to_file()

        return item

    def _extract_from_json(self, key, existing_json = None, info_section_key="", validation_class = InfoSection):
        info_section_instance = None
        financials_section_data = None

        if existing_json:
            # RETRIEVING 1)
            info_section = existing_json.get(info_section_key) 
            if info_section and info_section.get('reviewed'): 
                try: 
                    info_section_instance = validation_class.model_validate(info_section) 
                except Exception as e:
                    print(f'Invalid info section in existing json for {key} - ignored: {e}')

            # RETRIEVING 2)
            financials_section_data = existing_json.get('financials')

        return info_section_instance, financials_section_data

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
