from pydantic import BaseModel 
from scraper.tools.tools import COMPONENTS_DIR, VALUECHAIN_DIR, sanitized_name
from pathlib import Path

class Component(BaseModel): 
    name: str = "" 
    domestic: list[str] # codes
    overseas: list[str] ###_ needs clarification: what, how, and why
    updated: str = ""
    note: str = "" 

    def save_to_file(self): 
        path = Path() / f"{sanitized_name(self.name)}.json"

        path.write_text(
            self.model_dump_json(
                indent=4,
                exclude_none=True,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path):
        path = Path(path)
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

class ValueChain(BaseModel): 
    name: str = "" 
    components: dict[str, Component] 
    updated: str = ""
    note: str = "" 

    def save_to_file(self): 
        path = Path() / f"{sanitized_name(self.name)}.json"

        path.write_text(
            self.model_dump_json(
                indent=4,
                exclude_none=True,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path):
        path = Path(path)
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

if __name__ == "__main__":
    ###_ how to populate data
    p1 = Component(name='p1', companies=['a', 'b']) 
    p2 = Component(name='p2', companies=['a', 'c']) 
    vc1 = ValueChain(name='aero', updated='-', components={p1.name: p1, p2.name: p2}) 
    print(vc1.model_dump_json(indent=2))



