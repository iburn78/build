#%% 
# add scaling factor... or only to include department / companies to be split to disjoint virtual companies
# segment to be included in component 
# how segment to be constructed
# may add update button
# 
# Analysis first, and then think what to do

from build.models.profile import ProfileManager
from build.analysis.sector_analysis import SectorAnalysis
from build.models.component import ComponentManager

pm = ProfileManager()
code = '005930'
pr = pm.get_item(code, update=True)

SectorAnalysis().process(pr)



cm = ComponentManager()

cm.get_item('Memory', namelist = ['하이닉스', '삼성전자'])