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
