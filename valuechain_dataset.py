#%%
from scraper.models.valuechain_manager import ValueChainManager

vcm = ValueChainManager()

vcm.get_item(
    key = "Electronics",
    component_namelist=['Appliances', 'Smart_glass', 'Camera_module', 'PCB', 'MLCC', 'Display', 'Folderable'],
    replace=True,
)
