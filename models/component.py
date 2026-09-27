from pydantic import BaseModel, Field
from build.tools.settings import df_krx, COMPONENTS_DIR
from build.tools.analysis_tools import get_id
from build.models.json_models import JsonModel, InfoSection
from build.models.profile import Profile

class Member(BaseModel):
    # simple vehicle that carries only key and company name: works both for profile and segment 
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

# member from company name (for segments: append (id))
def cn(name):
    return Member.from_name(name)

# member from key 
def ck(key):
    return Member.from_key(key)

class Traits(InfoSection):
    competition: str = "" # m/s, leader, competitive advatages
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class Component(JsonModel): 
    DIR = COMPONENTS_DIR
    info_section: Traits
    members: list[Member] = Field(default_factory=list)

    def get_endkey_list(self) -> list:
        return list(self._sub_items.keys())

    def _get_subitems_and_cleanup(self):
        for m in self.members:
            code, id = get_id(m.key)
            pr = Profile.get_item(code)
            if id: 
                self._sub_items[m.key] = pr._sub_items[m.key]
            else: 
                self._sub_items[m.key] = pr

    def _update(self, **kwargs) -> bool:
        members = Component._build_member_list(**kwargs)

        ###_ infosection reviewed only when this, not to override always

        # set() operation does not work here for basemodel instances
        if all(x in self.members for x in members) and all(x in members for x in self.members):
            return False
        else: 
            self.members = members
            return True

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        members = cls._build_member_list(**kwargs)

        component = Component(
            key = key,
            filename = key,
            members = members,
            info_section = isection if isection else Traits(),
        )
        return component

    @classmethod
    def _build_member_list(cls, **kwargs):
        keylist = kwargs.get("keylist") or []
        namelist = kwargs.get("namelist") or []

        if len(keylist) != len(set(keylist)) or len(namelist) != len(set(namelist)): 
            raise ValueError(f'keylist or namelist should not contain any duplications: {keylist}{namelist}')

        if keylist and namelist:
            print(f'Both keylist and namelist is given, using keylist only {keylist}')
            namelist = []

        members = [Member.from_key(k) for k in keylist]
        members += [Member.from_name(n) for n in namelist]

        return members

