#%% 
# add scaling factor... or only to include department / companies to be split to disjoint virtual companies
# segment to be included in component 
# how segment to be constructed
# may add update button
# 
# Analysis first, and then think what to do

from build.models.profile import Profile
from build.models.component import Component
# from build.analysis.sector_analysis import SectorAnalysis

code = '005930'
pr = Profile.get_item(code, update=True)
cp = Component.get_item('Memory', namelist = ['하이닉스', '삼성전자'])

# SectorAnalysis().process(pr)
# SectorAnalysis().process(cp)