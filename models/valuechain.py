from pydantic import Field
from build.tools.settings import VALUECHAIN_DIR
from build.models.json_model import JsonModel, InfoSection
from build.models.component import Component
from build.analysis.sector_analysis import FinancialsData, SectorAnalysis
from pathlib import Path

class Landscape(InfoSection):
    dynamics: str = "" # leading component, margin concentration, buyer-seller power dynamics
    key_drivers: str = "" # what drives the growth and determines who wins, technology innovation, demand growth, etc
    notes: str = "" 

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR
    info_section: Landscape
    component_keys: list[str] # only component names

    def _get_name(self):
        return self.key

    def _get_subitems(self):
        self._sub_items.clear()
        for k in self.component_keys:
            self._sub_items[k] = Component.get_item(k)

    def _get_financials(self, **kwargs):
        self._financials_analyzer = SectorAnalysis()
        self._financials_analyzer.meta['name'] = self.key

        fd_list = []
        for cp in self.get_subitems().values():
            fd_list += cp._get_fd_list()
        fd_list = FinancialsData.dedupe_fds(fd_list)
        self._financials_analyzer.process(fd_list)

        return super()._get_financials(**kwargs)

    def _update(self, **kwargs) -> bool:
        changed = False
        component_keys = kwargs.get("component_keys", [])

        # case when component_keys are given
        if component_keys:
            if set(self.component_keys) != set(component_keys):
                self.component_keys = component_keys
                changed = True

        _info_section = kwargs.get('info_section')
        if _info_section:
            self.info_section = _info_section
            changed = True

        self._get_subitems()
        financials = self._get_financials(**kwargs)
        if self.financials != financials:
            self.financials = financials
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
        vc._get_subitems()
        # financials is filled after valuechain creation
        vc.financials = vc._get_financials(**kwargs)

        return vc
