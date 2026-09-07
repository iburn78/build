#%% 
import pandas as pd
from build.tools.settings import get_name
from data.util.tools import dprint

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
for key, val in name_dict.items():
    print(key, val)
    cp = cm.get_item(key, namelist=val)
    SectorAnalysis().process_component(cp)

    codelist = cp.get_codelist()
    pm.batch_process(codelist)

#%% 
from build.models.valuechain import ValueChainManager
from build.analysis.sector_analysis import SectorAnalysis

vm = ValueChainManager()
vc = vm.get_item(
    key = "EV_Battery", 
    component_namelist=list(name_dict.keys()),
    replace=True,
)

for vc in vm.get_itemlist(): 
    SectorAnalysis().process_valuechain(vc)


###_ 
# 1) to add marcap
# 2) to add some scaling factor... or only to include department
# 3) EV value chain, study why PER chart is broken - fix and make it robust 
# 4) 에코프로머티(450080) Dart API check, why it is broken, and not collected (2023 listed, maybe CFS issue)
# 5) check on too... (mostly on 에코프로머티, but seems in other too / dataset_generation)
# /Users/andy/projects/build/analysis/sector_analysis.py:984: RuntimeWarning: All-NaN axis encountered
  # scale_factor = np.nanmax(np.abs(opincome))
# /Users/andy/projects/build/analysis/sector_analysis.py:1015: RuntimeWarning: All-NaN axis encountered
  # bottom=min(0, np.nanmin(opincome))
# /Users/andy/projects/build/analysis/sector_analysis.py:1019: RuntimeWarning: All-NaN axis encountered
  # bottom=min(0, np.nanmin(per))
# /Users/andy/projects/build/analysis/sector_analysis.py:984: RuntimeWarning: All-NaN axis encountered
  # scale_factor = np.nanmax(np.abs(opincome))
# /Users/andy/projects/build/analysis/sector_analysis.py:1015: RuntimeWarning: All-NaN axis encountered
  # bottom=min(0, np.nanmin(opincome))
# /Users/andy/projects/build/analysis/sector_analysis.py:1019: RuntimeWarning: All-NaN axis encountered
  # bottom=min(0, np.nanmin(per))
# 4) make link to fnguide and naver
