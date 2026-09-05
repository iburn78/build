#%%
from build.models.valuechain import ValueChainManager
from build.analysis.sector_analysis import SectorAnalysis

vm = ValueChainManager()

# components should be already created
vc = vm.get_item(
    key = "Electronics",
    component_namelist=['Memory', 'Appliances', 'Smart_glass', 'Camera_module', 'PCB', 'MLCC', 'Display', 'Folderable'],
    replace=True,
)

vc = vm.get_item(
    key = "EV_Battery",
    component_namelist=[],
    replace=True,
)

# creation of SA(json, plot, html) for valuechains
# cascading creation of SA for components within 
for vc in vm.get_itemlist(): 
    SectorAnalysis().process_valuechain(vc)