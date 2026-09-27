from pydantic import BaseModel, Field
from build.tools.settings import df_krx, COMPONENTS_DIR
from build.tools.analysis_tools import get_id
from build.models.json_model import JsonModel, InfoSection
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

    def _get_subitems(self):
        for m in self.members:
            code, id = get_id(m.key)
            pr = Profile.get_item(code)
            if id: 
                segment = pr._sub_items.get(m.key)
                if segment is None:
                    raise ValueError(
                        f"Segment {m.key} is not enabled in profile {code}; "
                        "review the profile and enable segment creation first"
                    )
                self._sub_items[m.key] = segment
            else: 
                self._sub_items[m.key] = pr

    def _update(self, **kwargs) -> bool:
        changed = False
        members = Component._build_member_list(**kwargs)
        if members:
            # set() operation does not work here due to basemodel instances characteristics
            if len(self.members) != len (members) or not all(x in members for x in self.members):
                self.members = members
                changed = True
        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        members = cls._build_member_list(**kwargs)
        if not members: 
            raise ValueError(f"Component {key} cannot be initiated without members")

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
