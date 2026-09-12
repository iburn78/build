#%% 
import pandas as pd
from build.tools.settings import get_name
from data.tools.tools import dprint

ev = pd.read_excel('analysis/refs/이차전지_밸류체인_Excel.xlsx')
kr_ev = ev.loc[ev['티커'].str.contains('KS', na=False)]
name_dict = {
    category: [
        get_name(ticker.replace(" KS", ""))
        for ticker in tickers
    ]
    for category, tickers in kr_ev.groupby("소분류")["티커"].apply(list).items()
}
dprint(name_dict)

#%% 
from build.models.component import ComponentManager
from build.models.profile import ProfileManager
from build.analysis.sector_analysis import SectorAnalysis

cm = ComponentManager()
pm = ProfileManager()
# for key, val in name_dict.items():
#     print(key, val)
#     cp = cm.get_item(key, namelist=val)
#     SectorAnalysis().process_component(cp)

#     codelist = cp.get_codelist()
#     pm.batch_process(codelist)

a = pm.get_item('402340')
print(a)

#%% 
from build.models.valuechain import ValueChainManager
from build.analysis.sector_analysis import SectorAnalysis

vm = ValueChainManager()
# vc = vm.get_item(
#     key = "EV_Battery", 
#     component_namelist=list(name_dict.keys()),
#     replace=True,
# )

# for vc in vm.get_itemlist(): 
#     SectorAnalysis().process_valuechain(vc, fill=True)

###_ 


# 1) study why 세코닉스 no news (due to freshness threshold? no news ---)
# 2) to add some scaling factor... or only to include department
# 3) EV value chain, study why PER chart is broken - fix and make it robust 
# 4) 에코프로머티(450080) Dart API check, why it is broken, and not collected (2023 listed, maybe CFS issue)
# - may improve handling of CFS and OFS -> if OFS to CFS then include it / or leave it as is... 

# notice fill role, and 
# study why 에코프로머티 below chart is still empty when fill
# maybe add_dfs is not the right place to fill? 

# - https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/refs/heads/master/data/listing/krx/2026-09-08.csv

# may add update button
# think how linux machine is running and may change.
# Analysis first, and then think what to do