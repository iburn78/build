from pydantic import BaseModel, Field
from build.tools.analysis_tools import df_krx, COMPONENTS_DIR
from build.models.json_models import JsonModel, JsonModelManager, InfoSection

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

class Traits(InfoSection):
    competition: str = "" # m/s, leader, competitive advatages
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class Component(JsonModel): 
    DIR = COMPONENTS_DIR
    companies: list[Company] 
    traits: Traits | None = Field(default_factory=Traits)
    financials: dict | None = None

    def get_codelist(self):
        codelist = []
        for c in self.companies:
            codelist.append(c.code)
        return codelist

class ComponentManager(JsonModelManager):
    MODEL = Component

    # to create an component
    # use .get_item with codelist or namelist given
    # to completely overwrite, delete existing json file
    def _create_new_item(self, key, existing_json: dict | None = None, **kwargs) -> Component:
        ts, fs = self._extract_from_json(key, existing_json, 'traits', Traits)

        codelist = kwargs.get("codelist") or []
        namelist = kwargs.get("namelist") or []

        if len(codelist) != len(set(codelist)) or len(namelist) != len(set(namelist)): 
            raise ValueError(f'codelist or namelist should not contain any duplications: {codelist}{namelist}')

        if codelist and namelist:
            print(f'both codelist and namelist is given, using codelist only {codelist}')
            namelist = []

        companies = [Company.from_code(code) for code in codelist]
        companies += [Company.from_name(name) for name in namelist]

        component = Component(
            name = key,
            companies = companies,
            traits = ts,
            financials = None,
        )

        if fs:
            if set(component.get_codelist()) == set((fs.get('meta') or {}).get('codelist')):
                component.financials = fs
            else: 
                print(f'Component_Manager: codelist mismatching for {key} in financial section: discarding existing financial section')

        return component

