from pydantic import BaseModel, Field
from build.tools.settings import df_krx, COMPONENTS_DIR
from build.tools.analysis_tools import get_id
from build.models.json_models import JsonModel, InfoSection
from pathlib import Path

# for segments: code(A), name(A), etc...
class Company(BaseModel):
    # simple vehicle that carries only key and name 
    key: str 
    name: str

    @classmethod
    def from_name(cls, name, df_krx=df_krx):
        def _get_code_name(name, df_krx=df_krx):
            # 1. exact match first
            matched = df_krx[df_krx["Name"] == name]
            if len(matched) == 1:
                return str(matched.index[0]), matched.iloc[0]["Name"] 

            # 2. fallback to contains
            matched = df_krx[df_krx["Name"].str.contains(
                name,
                case=False,
                na=False
            )]

            if len(matched) == 1:
                return str(matched.index[0]), matched.iloc[0]["Name"] 

            if len(matched) == 0:
                raise ValueError(
                    f"No company found matching name: '{name}'"
                )

            raise ValueError(
                f"Ambiguous company name '{name}': "
                f"{matched['Name'].tolist()}"
            )

        _name, id = get_id(name)
        code, company_name = _get_code_name(_name)
        key = f"{code}({id})" if id else code
        return cls(
            key = key,
            name = company_name
        )

    @classmethod
    def from_key(cls, key, df_krx=df_krx):
        code, id = get_id(key)
         
        if code not in df_krx.index:
            raise ValueError(f"Invalid code: {code}")

        return cls(
            key = f"{code}({id})" if id else code,
            name=str(df_krx.loc[code, "Name"])
        )

# company from name
def cn(name):
    return Company.from_name(name)

# company from code
def ck(code):
    return Company.from_key(code)

class Traits(InfoSection):
    competition: str = "" # m/s, leader, competitive advatages
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class Component(JsonModel): 
    DIR = COMPONENTS_DIR
    info_section_name = 'traits'
    info_section_class = Traits
    companies: list = Field(default_factory=list)

    def assign_sub_items_keys(self):
        ###_ need implementation
        for c in self.companies:
            self._sub_items[c.key] = None # GET_ITEM 

    def get_qualitative_dict(self) -> dict:
        return {
            self.info_section_name: self.info_section,
        }

    def get_news_dir(self) -> Path | None:
        return None

    def update(self) -> bool:
        return False

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, fsection: dict | None, **kwargs):
        keylist = kwargs.get("keylist") or []
        namelist = kwargs.get("namelist") or []

        if len(keylist) != len(set(keylist)) or len(namelist) != len(set(namelist)): 
            raise ValueError(f'keylist or namelist should not contain any duplications: {keylist}{namelist}')

        if keylist and namelist:
            print(f'both keylist and namelist is given, using keylist only {keylist}')
            namelist = []

        companies = [Company.from_key(k) for k in keylist]
        companies += [Company.from_name(n) for n in namelist]

        component = Component(
            key = key,
            filename = key,
            companies = companies,
            info_section = isection if isection else Traits(),
            financials = fsection,
        )

        if fsection:
            if set(component.get_endkey_list()) == set((fsection.get('meta') or {}).get('key', [])):
                component.financials = fsection
            else: 
                print(f'Component_Manager: keylist mismatching for {key} in financial section: discarding existing financial section')

        return component

