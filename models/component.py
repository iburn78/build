from pydantic import BaseModel, Field
from build.tools.settings import df_krx, COMPONENTS_DIR, get_id
from build.models.json_model import JsonModel, InfoSection
from build.models.profile import Profile
from build.models.segment import Segment
from build.analysis.sector_analysis import FinancialsData, SectorAnalysis

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

    def _get_name(self):
        return self.key

    def _get_subitems(self):
        self._sub_items.clear()
        for m in self.members:
            self._sub_items[m.key] = Profile.get_item(m.key)

    def _get_financials(self, **kwargs):
        self._financials_analyzer = SectorAnalysis()
        self._financials_analyzer.meta['name'] = self.key

        fd_list = self._get_fd_list()
        self._financials_analyzer.process(fd_list)

        return super()._get_financials(**kwargs)

    def _get_fd_list(self):
        fd_list = []
        for item in self.get_subitems().values():
            fd_list.append(FinancialsData(
                key = item.key, 
                adjuster = item.info_section if type(item) is Segment else None
            ))
        return fd_list

    def _update(self, **kwargs) -> bool:
        changed = False
        members = Component._build_member_list(self.key, **kwargs)

        # case when members are given
        if members: 
            # set() operation does not work here due to basemodel instances characteristics
            if len(self.members) != len (members) or not all(x in members for x in self.members):
                self.members = members
                changed = True

        _info_section = kwargs.get('info_section')
        if _info_section:
            self.info_section = _info_section
            changed = True

        self._get_subitems()
        financials = self._get_financials(**kwargs)
        if self._financials_changed(financials):
            self.financials = financials
            changed = True

        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        members = cls._build_member_list(key, **kwargs)
        if not members: 
            raise ValueError(f"Component {key} cannot be initiated without members")

        component = Component(
            key = key,
            filename = key,
            members = members,
            info_section = isection if isection else Traits(),
        )
        component._get_subitems()
        # financials is filled after component creation
        component.financials = component._get_financials(**kwargs)

        return component

    @classmethod
    def _build_member_list(cls, key, **kwargs):
        keylist = kwargs.get("keylist") or []
        namelist = kwargs.get("namelist") or []

        if keylist and namelist:
            raise ValueError(f'Both keylist and namelist is given: use only one')

        members = [Member.from_key(k) for k in keylist]
        members += [Member.from_name(n) for n in namelist]

        # checking duplications
        codelist = []
        for m in members: 
            codelist.append(get_id(m.key)[0])
        if len(codelist) != len(set(codelist)):
            raise ValueError(f'Duplication found in component {key} members')

        return members
