from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel
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
from build.tools.settings import sanitized_filename, NEWS_DIR

AGENT_RETRIES = 5 
NUM_THREAD_TO_RUN = 4

class JsonModel(BaseModel, ABC):
    # to provide a basic pydantic structure to subclasses
    # - a json file is maintained per a model instance
    # - data format is validated when loaded

    DIR: ClassVar[str] # ClassVars is not included in json file, not validate when loaded
    key: str # unqiue identifier
    filename: str # json filename (key + additional information)
    updated: str = ""

    def model_post_init(self, context: Any) -> None:
        self.filename = sanitized_filename(self.filename)
        return super().model_post_init(context)

    def get_json_path(self) -> Path:
        return Path(self.DIR) / f"{self.filename}.json"

    def save_to_file(self):
        jp = self.get_json_path()
        print(f"{type(self).__name__} is saved: {jp}")
        jp.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path) -> JsonModel:
        path = Path(path)
        try:
            # default: extra = "ignore"
            obj = cls.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception as e:
            print(f"[load from file] jsonmodel validation failed: {path} | {e}")
            obj = None
        return obj

    @classmethod
    def get_json_path_from_prefix(cls, prefix: str): 
        prefix = sanitized_filename(prefix)
        paths = [p for p in Path(cls.DIR).glob("*.json") if p.name.startswith(prefix)]
        if len(paths) != 1:
            print(f"cannot load json file with prefix {prefix}...")
            return None 
        return paths[0]

    @classmethod
    def load_from_prefix(cls, prefix: str): 
        json_path = cls.get_json_path_from_prefix(prefix)
        if json_path is not None:
            return cls.load_from_file(json_path)
        else: 
            return None

    @abstractmethod
    def get_endkey_list(self):
        return []

    @abstractmethod
    def get_qualitative_dict(self):
        # return a dict, which may contain BaseModels
        return {}

    def get_news_dir(self):
        paths = [
            p for p in Path(NEWS_DIR).glob("*")
            if p.is_dir() and (p.name == self.key or p.name.startswith(f"{self.key}_"))
        ]
        if len(paths) != 1:
            print(f"cannot find unique news dir with {self.key}...")
            return None 
        return paths[0]

    # returns all instances in dict {key: instance}
    @classmethod
    def load_all_validated(cls) -> dict[str, "JsonModel"]:
        objects_dict = {}

        for path in Path(cls.DIR).glob("*.json"):
            try:
                obj = cls.load_from_file(path)
                objects_dict[obj.key] = obj
            except Exception as e:
                print(f"Skipping {path}: {e}")

        return objects_dict

class InfoSection(BaseModel):
    # to provide human-review-needed information to JsonModels
    # - if reviewed == True, information survives through updates or (automatic) creations if filename matches
    # - if needed, AI agent will be provided
    reviewed: bool = False
    updated: str | None = None

def update_info_section(obj: JsonModel, section_name: str, values: dict):
    section = getattr(obj, section_name)

    if not isinstance(section, InfoSection):
        raise ValueError(
            f"{section_name} is not an InfoSection"
        )

    # Pydantic validation
    updated_section = type(section).model_validate(values)

    # Automatic edit timestamp
    updated_section.updated = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    setattr(obj, section_name, updated_section)

    obj.save_to_file()

    return updated_section


class JsonModelManager(ABC): 
    MODEL: type[JsonModel] # class not an instance

    def __init__(self):
        self._items = {} # {obj.key: obj, ...}

    @abstractmethod
    def _create_new_item(self, key, existing_json: dict | None = None, **kwargs) -> JsonModel:
        # Create a valid MODEL with info from existing json if any
        ...

    def _update(self, item) -> bool:
        # Perform update if content needs refresh
        # and return True if item content changed
        return False

    def get_itemlist(self) -> list[JsonModel]:
        return list(self._items.values())

    # main function to get an item from loaded
    # - if update needed, this will triger update 
    # - if reviewed info_section exists, this will load it
    # - if financials_section exists, this will load it
    def get_item(self, key, update=False, **kwargs):
        json_path = self.MODEL.get_json_path_from_prefix(key)

        if json_path is not None:
            item = self.MODEL.load_from_file(json_path)

            if item is not None:
                changed = self._update(item)
            else: 
                try: 
                    existing_json = json.loads(json_path.read_text(encoding="utf-8"))
                    print(f"Importing existing json for {key}")
                except:
                    existing_json = None
                    print(f"Overwriting existing json for {key}")

                item = self._create_new_item(key, existing_json, **kwargs)
                changed = True

        else:
            print(f"Creating new json for {key}")
            item = self._create_new_item(key, None, **kwargs)
            changed = True
            
        if update or changed: 
            item.updated = datetime.now().strftime("%Y-%m-%d") 
            item.save_to_file()

        self._items[item.key] = item
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
