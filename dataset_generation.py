#%%
import pandas as pd
from build.tools.settings import get_name
from data.tools.tools import dprint

from build.models.profile import Profile
from build.models.component import Component
from build.models.valuechain import ValueChain
from build.analysis.sector_analysis import SectorAnalysis
from build.tools.analysis_tools import get_id

# profiles may not need to be created before components' creation
# components should be already created for valuechain to be created

# --------------------------------------------------
# Electronics
# --------------------------------------------------
Component.get_item('Memory', namelist = ['하이닉스', '삼성전자'])
Component.get_item('Appliances', namelist = ['삼성전자', 'LG전자'])
Component.get_item('Smart_glass', namelist = ['사피엔반도체'])
Component.get_item('Camera_module', namelist = ['LG이노텍', '삼성전기', '엠씨넥스', '세코닉스'])
Component.get_item('PCB', namelist = ['LG이노텍', '삼성전기', '엠씨넥스', '세코닉스']) # PCB, FPCB
Component.get_item('MLCC', namelist = ['삼성전기', '삼화콘덴서'])
Component.get_item('Display', namelist = ['덕산네오룩스', '이녹스첨단소재', '피엔에이치테크', 'PI첨단소재', 'LX세미콘'])
Component.get_item('Folderable', namelist = ['KH바텍', '세경하이테크', '파인엠텍'])

v1 = ValueChain.get_item(
    key = "Electronics",
    component_keys=['Memory', 'Appliances', 'Smart_glass', 'Camera_module', 'PCB', 'MLCC', 'Display', 'Folderable'],
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
    cp = Component.get_item(key, namelist=val)

v2 = ValueChain.get_item(
    key = "EV_Battery", 
    component_keys=list(name_dict.keys()),
)

# --------------------------------------------------
# Profiles creation / update (jsons files)
# --------------------------------------------------
components = v1.get_subitems() | v2.get_subitems()
endkeys = list(dict.fromkeys(
    key
    for cp in components.values()
    for key in cp.get_endkey_list()
))

profile_codes = list(dict.fromkeys(get_id(key)[0] for key in endkeys))
Profile.batch_process(profile_codes)

# --------------------------------------------------
# Sector Analysis Creation / Cacaded for components
# --------------------------------------------------
# - json financials section, plot, and html
for vc in [v1, v2]:
    SectorAnalysis().process(vc)
