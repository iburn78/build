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
    info_section: Landscape
    component_keys: list[str] # only component names

    def get_endkey_list(self) -> list:
        endkey_list = set()
        for k, v in self._sub_items:
            endkey_list.update(set(v._sub_items.keys()))
        return list(endkey_list)

    def _get_subitems_and_cleanup(self):
        for k in self.component_keys:
            self._sub_items[k] = Component.get_item(k)

    def _update(self, **kwargs) -> bool:
        component_keys = kwargs.get("component_keys", [])
        if set(self.component_keys) == set(component_keys):
            return False
        else: 
            self.component_keys = component_keys
            return True

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        # give component namelist to create new one
        component_keys = kwargs.get("component_keys", [])

        vc = ValueChain(
            key = key,
            filename = key,
            component_keys = component_keys,
            info_section = isection if isection else Landscape(), 
        )

        return vc