#%%
from scraper.tools.json_models import CV_Manager
from scraper.valuechain_manager import ValueChain

cvm = CV_Manager()

vc = ValueChain(
    name='Electronics',
    components=['Appliances', 'Smart Glass', 'Camera Module', 'PCB', 'MLCC', 'Display', 'Folderable'],
).to_cvm(cvm)

print(cvm.get_component('Appliances'))
