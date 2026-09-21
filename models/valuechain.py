from pydantic import Field
from build.tools.settings import VALUECHAIN_DIR 
from build.models.json_models import JsonModel, JsonModelManager, InfoSection
from build.models.component import Component, ComponentManager

class Landscape(InfoSection):
    dynamics: str = "" # leading component, margin concentration, buyer-seller power dynamics
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR
    component_names: list[str] # only component names
    landscape: Landscape | None = Field(default_factory=Landscape)
    financials: dict | None = None

    def get_components(self):
        components = []
        for component_name in self.component_names:
            components.append(Component.load_from_prefix(component_name))
        return components

    ###_ NEED REVISE: NAME AND DUPLICATION, both 005030 and 005030(A) should not be included
    def get_endkey_list(self):
        components = self.get_components()
        keylist = set()
        for c in components:
            keylist.update(c.get_endkey_list())
        return list(keylist)

    def get_qualitative_dict(self):
        return {
            'components': self.component_names,
            'landscape': self.landscape,
        }

class ValueChainManager(JsonModelManager):
    MODEL = ValueChain

    # def __init__(self):
    #     self.cm = ComponentManager()
    #     super().__init__()

    ###_ need implementation
    def _update(self, item) -> bool:
        ###_ auto-create content and info_section (if not reviewed)
        ###_ should check memebers are identical at least
        return True

    def _create_new_item(self, key, existing_json: dict | None = None, **kwargs) -> ValueChain:
        ls, fs = self._extract_from_json(key, existing_json, 'landscape', Landscape)

        # give component namelist to create new one
        component_namelist = kwargs.get("component_namelist") or []

        # Option 1) get (or create) all components
        # components = [self.cm.get_item(cn) for cn in component_namelist]

        # Option 2) proceed only if all components already exists (this case: all components should be pre-loaded)
        # if any(c not in self.cm._items for c in component_namelist):
        #     raise ValueError(f"VC_Manager: for {key} given components not already created")

        vc = ValueChain(
            key = key,
            filename = key,
            component_names = component_namelist,
            landscape = ls,
            financials = None,
        )

        if fs:
            # key-level confirmation
            if set(vc.get_endkey_list()) == set((fs.get('meta', {})).get('key', [])):
                vc.financials = fs
            else: 
                print(f'VC_Manager: component list mismatching for {key} in financial section: discarding existing financial section')

        return vc