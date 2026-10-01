from abc import ABC, abstractmethod
from pathlib import Path
from pydantic import BaseModel, PrivateAttr
from datetime import datetime, timedelta
from typing import Any, ClassVar
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from build.tools.settings import sanitized_filename, BUILD_DIR
from build.tools.render_html import render_html

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

    # Directory where json files are stored
    DIR: ClassVar[str] # ClassVars is not included in json file, not validated when loading

    key: str # unqiue identifier within the DIR
    filename: str # json filename (key_additional information)
    updated: str = ""

    # below to be defined in each sub-class 
    # info_section: InfoSection 

    financials: dict | None = None
    # PrivateAttr is not included in the json file, not validated when loading
    _financials_analyzer: object | None = PrivateAttr(default=None)
    _sub_items: dict = PrivateAttr(default_factory=dict)

    # this is called when both loaded and created
    def model_post_init(self, context: Any) -> None:
        self.filename = sanitized_filename(self.filename)
        return super().model_post_init(context)

    def get_json_path(self) -> Path:
        return Path(self.DIR) / f"{self.filename}.json"

    def save_to_file(self):
        self.updated = datetime.now().strftime("%Y-%m-%d") 
        jp = self.get_json_path()
        jp.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )
        print(f"{type(self).__name__} is saved: {jp}")

    def get_qualitative_dict(self) -> dict:
        # return a dict, which contain BaseModels to be shown in html
        # single InfoSection is included in the dict
        return {
            type(self.info_section).__name__.lower(): self.info_section,
        }

    def get_news_dir(self) -> Path | None:
        return None

    # Child items are populated by get_item after update inputs are applied.
    def get_subitems(self): 
        return self._sub_items

    def get_subitems_financial_analyzers(self):
        from build.analysis.sector_analysis import SectorAnalysis

        res = []
        for _, item in self._sub_items.items():
            analyzer = item._financials_analyzer
            if analyzer is None and item.financials is not None:
                analyzer = SectorAnalysis.from_financials(item.financials)
            res.append(analyzer)
        return res

    # creation and update of sub_items
    @abstractmethod
    def _get_subitems(self):
        # recursively refresh sub_items and perform cleanup if necessary
        ...

    def _update_financials(self, **kwargs) -> bool:
        if self.financials is None:
            return True

        updated = self.financials["meta"]["updated"]
        updated_at = datetime.fromisoformat(updated)
        if datetime.now() - updated_at >= timedelta(hours=3):
            return True

        # Timestamps are recorded to seconds; a one-second overlap covers ordering
        # at that precision without repeatedly refreshing recent parent models.
        child_refresh_cutoff = updated_at - timedelta(seconds=1)
        return any(
            item.financials
            and datetime.fromisoformat(item.financials["meta"]["updated"]) >= child_refresh_cutoff
            for item in self.get_subitems().values()
        )

    # this has to be called after instance creation so that sub_items to be created beforehand
    @abstractmethod
    def _get_financials(self, **kwargs) -> dict:
        # perform common processes and return financials
        self._financials_analyzer._create_plot(save_path=self.get_json_path().with_suffix('.png'))

        sub_fas = self.get_subitems_financial_analyzers()
        self._financials_analyzer._sub_sector_analyses(sub_sas=sub_fas)

        return self._financials_analyzer.financials

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
        paths = [p for p in Path(cls.DIR).glob("*.json") if p.name.startswith(prefix)]
        if len(paths) > 1:
            paths = [p for p in paths if p.name.startswith(f"{prefix}_")]
        if len(paths) != 1:
            print(f"Cannot load json file with prefix {prefix}...")
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
            print(f"[Load from file] jsonmodel validation failed: {path} | {e}")
            obj = None
        return obj

    # this assumes only one info_section and one financials_section
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
            item.create_html()

        return item

    # batch processing on get_item()
    # python 3.14 + pydantic_ai on windows yield: asyncio ProactorEventLoop / overlapped I/O cleanup errors, etc. 
    @classmethod
    def batch_process(cls, keylist, max_workers=NUM_THREAD_TO_RUN):
        if sys.platform == "win32":
            print("--------------------------------------------------")
            print("Generating items - sequential on Windows")
            print("--------------------------------------------------")
            for key in keylist:
                cls.get_item(key)
            return
        print("--------------------------------------------------")
        print(f"Generating items - max {max_workers} threads")
        print("--------------------------------------------------")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(cls.get_item, keylist))

    @abstractmethod
    def _get_name(self)->str:
        ...

    def _get_html_link(self):
        html_root = Path(BUILD_DIR)
        return self.get_json_path().with_suffix('.html').relative_to(html_root)

    def create_html(self):
        _list = [self] + list(self._sub_items.values())
        financials_names = [
            {
                'name': item._get_name(),
                'link': item._get_html_link(), 
            }
            for item in _list
        ]
        financials_dicts = [
            {
                key: item.financials[key]
                for key in ("meta", "shape", "assess_data", "assess_result")
            }
            for item in _list
        ]
        qual_dict = self.get_qualitative_dict()
        news_dir = self.get_news_dir() 
        output_file = self.get_json_path().with_suffix('.html')

        render_html(type(self).__name__, 
                    self.key, 
                    financials_names, 
                    financials_dicts, 
                    qual_dict, 
                    news_dir, 
                    output_file, 
                    info_section_validator=type(self.info_section))
