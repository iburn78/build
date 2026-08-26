from pydantic import Field
from build.tools.tools import VALUECHAIN_DIR 
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

    def get_codelist(self):
        components = self.get_components()
        codelist = set()
        for c in components:
            codelist.update(c.get_codelist())
        return list(codelist)

class ValueChainManager(JsonModelManager):
    MODEL = ValueChain

    def __init__(self):
        self.component_manager = ComponentManager()
        super().__init__()

    # ValueChain handlers defined here, as ComponentManager is necessary
    def get_components(self, vc: ValueChain):
        components = []
        for cn in vc.component_names:
            cp = self.component_manager.get_item(cn)
            components.append(cp)
        return components

    def get_codelist(self, vc: ValueChain):
        codelist = set()
        for cn in vc.component_names:
            codelist.update(self.component_manager.get_item(cn).get_codelist())
        return list(codelist)

    def _create_new_item(self, key, existing_json: dict | None = None, **kwargs) -> ValueChain:
        ls, fs = self._extract_from_json(key, existing_json, 'landscape', Landscape)

        # give component namelist to create new one
        component_namelist = kwargs.get("component_namelist") or []

        # Option 1) get (or create) all components
        # components = [self.component_manager.get_item(cn) for cn in component_namelist]

        # Option 2) proceed only if all components already exists
        if any(c not in self.component_manager._items for c in component_namelist):
            raise ValueError(f"VC_Manager: for {key} given components not already created")

        vc = ValueChain(
            name = key,
            component_names = component_namelist,
            landscape = ls,
            financials = None,
        )

        if fs:
            # codelevel confirmation
            if set(self.get_codelist(vc)) == set((fs.get('meta') or {}).get('codelist')):
                vc.financials = fs
            else: 
                print(f'VC_Manager: component list mismatching for {key} in financial section: discarding existing financial section')

        return vc