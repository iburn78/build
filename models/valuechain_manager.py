from pydantic import Field
from scraper.tools.tools import VALUECHAIN_DIR 
from scraper.models.json_models import JsonModel, JsonModelManager, InfoSection
from scraper.models.component_manager import Component, ComponentManager

class Landscape(InfoSection):
    dynamics: str = "" # leading component, margin concentration, buyer-seller power dynamics
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR
    components: list[str]
    landscape: Landscape | None = Field(default_factory=Landscape)
    financials: dict | None = None

    def get_component_names(self):
        components = []
        for c in self.components:
            components.append(c.name)
        return components

    def get_codelist_set(self):
        codelist_set = set()
        for c in self.components:
            codelist_set.update(c.get_codelist())
        return codelist_set

class ValueChainManager(JsonModelManager):
    MODEL = ValueChain

    def __init__(self):
        self.component_manager = ComponentManager()
        super().__init__()

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
            components = component_namelist,
            landscape = ls,
            financials = None,
        )

        if fs:
            # codelevel confirmation
            if vc.get_codelist_set == set((fs.get('meta') or {}).get('codelist')):
                vc.financials = fs
            else: 
                print(f'VC_Manager: component list mismatching for {key} in financial section: discarding existing financial section')

        return vc