#%%
from build.models.valuechain import ValueChainManager
from build.analysis.sector_analysis import SectorAnalysis

vm = ValueChainManager()

vc = vm.get_item(
    key = "Electronics",
    component_namelist=['Appliances', 'Smart_glass', 'Camera_module', 'PCB', 'MLCC', 'Display', 'Folderable'],
    replace=True,
)

# creation of SA(json, plot, html) for valuechains
# cascading creation of SA for components within
for vc in vm.get_itemlist():
    SectorAnalysis().process_valuechain(vc)