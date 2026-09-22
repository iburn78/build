from pydantic import Field
from build.tools.settings import VALUECHAIN_DIR 
from build.models.json_models import JsonModel, InfoSection
from build.models.component import Component
from pathlib import Path

class Landscape(InfoSection):
    dynamics: str = "" # leading component, margin concentration, buyer-seller power dynamics
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR
    info_section_name = 'landscape'
    info_section_class = Landscape
    component_keys: list[str] # only component names

    ###_ NEED REVISE: NAME AND DUPLICATION, both 005030 and 005030(A) should not be included
    def get_endkey_list(self):
        endkey_list = []
        for ck, cv in self._sub_items:
            for k, v in cv._sub_items:
                endkey_list.append(k)
        return endkey_list

    def assign_sub_items_keys(self):
        for k in self.component_keys:
            self._sub_items[k] = Component.get_item(k)

    def get_qualitative_dict(self):
        return {
            self.info_section_name: self.info_section,
        }

    def get_news_dir(self) -> Path | None:
        return None

    def update(self) -> bool:
        return False

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, fsection: dict | None, **kwargs):
        # give component namelist to create new one
        component_namelist = kwargs.get("component_namelist", [])

        vc = ValueChain(
            key = key,
            filename = key,
            component_keys = component_namelist,
            info_section= = isection if isection else Landscape(), 
            financials = fsection,
        )

        if fsection:
            # key-level confirmation
            if set(vc.get_endkey_list()) == set((fsection.get('meta', {})).get('key', [])):
                vc.financials = fsection
            else: 
                print(f'VC_Manager: component list mismatching for {key} in financial section: discarding existing financial section')

        return vc