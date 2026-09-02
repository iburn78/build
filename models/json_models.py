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
        try:
            # default: extra = "ignore"
            obj = cls.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            obj._json_path = path
        except Exception as e:
            print(f"jsonmodel validation failed: {path} | {e}")
            obj = None
        return obj

    # search within cls.DIR for a unique file starts with prefix...
    @classmethod
    def get_json_filename_from_prefix(cls, prefix: str): 
        paths = list(Path(cls.DIR).glob(f"{prefix}*.json"))
        if len(paths) != 1:
            print(f"cannot load json file with prefix {prefix}...")
            return None 
        return paths[0]

    @classmethod
    def load_from_prefix(cls, prefix: str): 
        json_filename = cls.get_json_filename_from_prefix(prefix)
        if json_filename is not None:
            return cls.load_from_file(json_filename)
        else: 
            return None

    def get_json_path(self) -> Path:
        if not self._json_path: 
            print("Instance doesn't have json file...") 
            return None
        return self._json_path

    # key for the json_model dict
    def key(self) -> str:
        return self.name

    @abstractmethod
    def get_qualitative_dict(self):
        # return a dict, which may contain BaseModels
        pass

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
    MODEL: type[JsonModel]

    def __init__(self):
        self._items = {} # {obj.key(): obj, ...}

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
    def get_item(self, key, **kwargs):
        self._validate_key(key)
        json_filename = self.MODEL.get_json_filename_from_prefix(key)

        if json_filename is not None:
            item = self.MODEL.load_from_file(json_filename)

            if item is not None:
                changed = self._update(item)
            else: 
                try: 
                    existing_json = json.loads(json_filename.read_text(encoding="utf-8"))
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
            
        if changed: 
            item.updated = datetime.now().strftime("%Y-%m-%d") 
            item.save_to_file()

        self._items[item.key()] = item
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
