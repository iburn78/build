#%%
from build.models.valuechain import ValueChainManager

vm = ValueChainManager()

vm.get_item(
    key = "Electronics",
    component_namelist=['Appliances', 'Smart_glass', 'Camera_module', 'PCB', 'MLCC', 'Display', 'Folderable'],
    replace=True,
)
