#%%
import pandas as pd
from build.tools.settings import get_name
from data.tools.tools import dprint

from build.models.profile import ProfileManager
from build.models.component import ComponentManager
from build.models.valuechain import ValueChainManager
from build.analysis.sector_analysis import SectorAnalysis

# profiles may not need to be created before components' creation
# components should be already created for valuechain to be created

pm = ProfileManager()
cm = ComponentManager()
vm = ValueChainManager()

# --------------------------------------------------
# Electronics
# --------------------------------------------------
cm.get_item('Memory', namelist = ['하이닉스', '삼성전자'])
cm.get_item('Appliances', namelist = ['삼성전자', 'LG전자'])
cm.get_item('Smart_glass', namelist = ['사피엔'])
cm.get_item('Camera_module', namelist = ['LG이노텍', '삼성전기', '엠씨넥스', '세코닉스'])
cm.get_item('PCB', namelist = ['LG이노텍', '삼성전기', '엠씨넥스', '세코닉스']) # PCB, FPCB
cm.get_item('MLCC', namelist = ['삼성전기', '삼화콘덴서'])
cm.get_item('Display', namelist = ['덕산네오룩스', '이녹스첨단소재', '피엔에이치테크', 'PI첨단소재', 'LX세미콘'])
cm.get_item('Folderable', namelist = ['KH바텍', '세경하이테크', '파인엠텍'])

vc = vm.get_item(
    key = "Electronics",
    component_namelist=['Memory', 'Appliances', 'Smart_glass', 'Camera_module', 'PCB', 'MLCC', 'Display', 'Folderable'],
    replace=True,
)

# --------------------------------------------------
# EV_Battery
# --------------------------------------------------
ev = pd.read_excel('analysis/refs/이차전지_밸류체인_Excel.xlsx')
kr_ev = ev.loc[ev['티커'].str.contains('KS', na=False)]
name_dict = {category: [get_name(ticker.replace(" KS", "")) for ticker in tickers] 
             for category, tickers in kr_ev.groupby("소분류")["티커"].apply(list).items()}
# dprint(name_dict)

for key, val in name_dict.items():
    cp = cm.get_item(key, namelist=val)

vc = vm.get_item(
    key = "EV_Battery", 
    component_namelist=list(name_dict.keys()),
    replace=True,
)

# --------------------------------------------------
# Profiles creation / update (jsons files)
# --------------------------------------------------
for cp in cm.get_itemlist(): 
    print(cp.name, cp.get_codelist())
    pm.batch_process(cp.get_codelist())

# --------------------------------------------------
# Sector Analysis Creation / Cacaded for components
# --------------------------------------------------
# - json financials section, plot, and html
for vc in vm.get_itemlist(): 
    SectorAnalysis().process(vc)