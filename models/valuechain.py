from pydantic import Field
from build.tools.settings import VALUECHAIN_DIR 
from build.models.json_model import JsonModel, InfoSection
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

    def _get_subitems(self):
        for k in self.component_keys:
            self._sub_items[k] = Component.get_item(k)

    def _update(self, **kwargs) -> bool:
        changed = False
        component_keys = kwargs.get("component_keys", [])
        if component_keys:
            if set(self.component_keys) != set(component_keys):
                self.component_keys = component_keys
                changed = True
        return changed

    @classmethod
    def _create_new_item(cls, key, isection: InfoSection | None, **kwargs):
        # give component namelist to create new one
        component_keys = kwargs.get("component_keys", [])
        if not component_keys: 
            raise ValueError(f"ValueChain {key} cannot be initiated without component keys")

        vc = ValueChain(
            key = key,
            filename = key,
            component_keys = component_keys,
            info_section = isection if isection else Landscape(), 
        )

        return vc