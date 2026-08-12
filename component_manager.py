from pydantic import BaseModel, Field
from scraper.tools.tools import df_krx, COMPONENTS_DIR
from scraper.tools.json_models import JsonModel, JsonModelManager

class Company(BaseModel):
    # simple vehicle that carries only name and code
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

# company from name
def cn(name):
    return Company.from_name(name)

# company from code
def cc(code):
    return Company.from_code(code)

###_ to be implemented
class Traits(BaseModel):
    competition: str = "" # m/s, leader, competitive advatages
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class Component(JsonModel): 
    DIR = COMPONENTS_DIR
    companies: list[Company] # listed domestic
    traits: Traits = Field(default_factory=Traits)
    financials: dict | None = None

    ###_ change... 
    def to_cvm(self, cvm): # CV_Manager
        cvm.add_component(self)

    def get_codelist(self):
        codelist = []
        for c in self.companies:
            codelist.append(c.code)
        return codelist

###_
class ComponentManager(JsonModelManager):
    pass