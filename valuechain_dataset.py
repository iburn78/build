#%%
from tools.models import ValueChain, CV_Manager
cvm = CV_Manager()

vc = ValueChain(
    name='Electronics',
    components=['Appliances', 'Smart Glass', 'Camera Module', 'PCB', 'MLCC', 'Display', 'Folderable'],
).to_cvm(cvm)

print(cvm.get_component('Appliances'))
