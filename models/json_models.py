from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, PrivateAttr
from datetime import datetime
from typing import Any, ClassVar
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from build.tools.settings import sanitized_filename

NUM_THREAD_TO_RUN = 4

class InfoSection(BaseModel):
    # to provide human-review-needed information to JsonModels
    # - if reviewed is True, information survives through updates or (automatic) creations if json path matches
    # - if needed, AI agent can be used
    reviewed: bool = False
    updated: str | None = None

class JsonModel(BaseModel, ABC):
    # to provide a basic pydantic structure to subclasses
    # - a json file is maintained per a model instance
    # - data format is validated when loaded

    DIR: ClassVar[str] # ClassVars is not included in json file, not validated when loading
    info_section_class: ClassVar[type[InfoSection]]

    key: str # unqiue identifier
    filename: str # json filename (key_additional information)
    updated: str = ""

    info_section: InfoSection   
    financials: dict | None = None

    # PrivateAttr is not included in json file, not validated when loading
    _sub_items_info: dict = PrivateAttr(default_factory=dict)
    _sub_items: dict = PrivateAttr(default_factory=dict)

    # this is called when both loaded and created
    def model_post_init(self, context: Any) -> None:
        self.filename = sanitized_filename(self.filename)
        self._build_sub_items_info()
        return super().model_post_init(context)

    def get_json_path(self) -> Path:
        return Path(self.DIR) / f"{self.filename}.json"

    def save_to_file(self):
        self.updated = datetime.now().strftime("%Y-%m-%d") 
        jp = self.get_json_path()
        print(f"{type(self).__name__} is saved: {jp}")
        jp.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )

    # endkey: keys for profiles and segments (i.e., each endkey contains standalone financials data), excluding self.key
    def get_endkey_list(self) -> list:
        if self._sub_items.keys():
            return list(self._sub_items.keys())
        return []
    
    def get_qualitative_dict(self) -> dict:
        # return a dict, which contain BaseModels to be shown in html
        # single InfoSection is included in the dict
        return {
            self.info_section_class.__name__.lower(): self.info_section,
        }

    def _build_sub_items_info(self):
        pass

    def _cleanup_sub_items(self):
        pass

    def get_news_dir(self) -> Path | None:
        return None

    @abstractmethod
    def _update(self, **kwargs) -> bool:
        # perform update in self if content needs refresh
        # and return True if item content changed
        # save is handled in get_item
        ...

    @classmethod
    @abstractmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs) -> JsonModel:
        # create a valid MODEL with info from existing json if any
        # save is handled in get_item
        ...

    @classmethod
    def _get_json_path_from_prefix(cls, prefix: str) -> Path | None: 
        prefix = sanitized_filename(prefix)
        paths = [p for p in Path(cls.DIR).glob("*.json") if p.name.split('_')[0] == prefix]
        if len(paths) != 1:
            print(f"cannot load json file with prefix {prefix}...")
            return None 
        return paths[0]

    # should not be used as standalone as sub_items are not populated
    @classmethod
    def _load_from_path(cls, path: str | Path) -> JsonModel | None:
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

    # this assumes only one info_section and one financials_section
    @classmethod
    def _extract_from_json(cls, existing_json = None):
        info_section_instance = None

        if existing_json:
            info_section = existing_json.get(cls.info_section_class.__name__.lower())
            if info_section and info_section.get('reviewed'): 
                try: 
                    info_section_instance = cls.info_section_class.model_validate(info_section) 
                except Exception as e:
                    pass

        return info_section_instance

    # main function to get an item 
    # - if update needed, this will triger update 
    # - if reviewed info_section exists, this will load it
    # - if financials_section exists, this will load it
    @classmethod
    def get_item(cls, key, **kwargs):
        json_path = cls._get_json_path_from_prefix(key)

        if json_path:
            item = cls._load_from_path(json_path)

            if item:
                changed = item._update(**kwargs)
                if changed:
                    print(f"Updating existing json for {key}")
            else: 
                # below handles when a valid json_path exists but failed to validate, retrieving partial info therein
                print(f"Overwriting existing json for {key}")
                try: 
                    existing_json = json.loads(json_path.read_text(encoding="utf-8"))
                    isection = cls._extract_from_json(existing_json)
                except:
                    isection = None

                item = cls._create_new_item(key, isection, **kwargs)
                changed = True

        else:
            print(f"Creating new json for {key}")
            item = cls._create_new_item(key, None, **kwargs)
            changed = True
            
        if changed: 
            item.save_to_file()

        # recursively refresh sub_items and perform cleanup if necessary
        for key, info in item._sub_items_info:
            kwargs = info if info else {}
            item._sub_items[key] = cls.get_item(key, **kwargs)
        item._cleanup_sub_items()

        return item

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
