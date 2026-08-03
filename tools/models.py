from pathlib import Path
from pydantic import BaseModel 
from datetime import datetime
from typing import Any, ClassVar
from scraper.tools.tools import sanitized_name, df_krx, COMPONENTS_DIR, VALUECHAIN_DIR

class JsonModel(BaseModel):
    DIR: ClassVar[str] = "" # overridden by subclasses, and json does not include ClassVars / not validate either
    name: str
    updated: str = ""

    def model_post_init(self, context: Any) -> None:
        self.updated = datetime.now().strftime("%Y-%m-%d")
        return super().model_post_init(context)

    def filename(self) -> str:
        return sanitized_name(self.name)

    def save_to_file(self):
        path = Path(self.DIR) / f"{self.filename()}.json"
        path.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path):
        return cls.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )

    def key(self) -> str:
        return self.name

    @classmethod
    def load_all(cls): # dict[str, JsonModel]
        objects_dict = {}

        for path in Path(cls.DIR).glob("*.json"):
            try:
                obj = cls.load_from_file(path)
                objects_dict[obj.key()] = obj
            except Exception as e:
                print(f"Skipping {path}: {e}")

        return objects_dict

class Company(BaseModel):
    name: str
    code: str

    @classmethod
    def from_name(cls, name, df_krx=df_krx):
        # 1. exact match first
        matched = df_krx[df_krx["Name"] == name]

        if len(matched) == 1:
            return cls(
                name=matched.iloc[0]["Name"],
                code=str(matched.index[0])
            )

        # 2. fallback to contains
        matched = df_krx[df_krx["Name"].str.contains(
            name,
            case=False,
            na=False
        )]

        if len(matched) == 1:
            return cls(
                name=matched.iloc[0]["Name"],
                code=str(matched.index[0])
            )

        if len(matched) == 0:
            raise ValueError(
                f"No company found matching name: '{name}'"
            )

        raise ValueError(
            f"Ambiguous company name '{name}': "
            f"{matched['Name'].tolist()}"
        )

    @classmethod
    def from_code(cls, code, df_krx=df_krx):
        if code not in df_krx.index:
            raise ValueError(f"Invalid code: {code}")

        return cls(
            name=str(df_krx.loc[code, "Name"]),
            code=str(code)
        )

def cn(name):
    return Company.from_name(name)

def cc(code):
    return Company.from_code(code)

class Component(JsonModel): 
    DIR = COMPONENTS_DIR
    companies: list[Company] # listed domestic
    note: str = ""

    def to_cvm(self, cvm: CV_Manager):
        cvm.add_component(self)

    def get_codelist(self):
        codelist = []
        for c in self.companies:
            codelist.append(c.code)
        return codelist

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR
    components: list
    note: str = ""

    def to_cvm(self, cvm: CV_Manager):
        cvm.add_valuechain(self)

# Component and ValueChain
class CV_Manager: 
    def __init__(self):
        self._components = Component.load_all()
        self._valuechains = ValueChain.load_all()

    def add_component(self, cp):
        self._components[cp.name] = cp
        cp.save_to_file()

    def get_component(self, name) -> Component:
        res = self._components.get(name)
        if res: 
            return res
        else:
            raise ValueError(f"no component exists: {name}")

    def add_valuechain(self, vc):
        # check if components are already defined
        for c in vc.components:
            if c not in self._components.keys():
                raise ValueError(f"For valuechain '{vc.name}', component '{c}' is not defined in cvm (not found)")
        self._valuechains[vc.name] = vc
        vc.save_to_file()