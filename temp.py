#%% 
# add scaling factor... or only to include department / companies to be split to disjoint virtual companies
# may add update button
# Analysis first, and then think what to do

from build.models.profile import ProfileManager, Profile, Segment
from build.analysis.sector_analysis import SectorAnalysis
pm = ProfileManager()

code = '005930'
pr = pm.get_item(code)
sg = Segment.load_from_prefix('005930(A)')
print(sg)

SectorAnalysis().process(pr)
# SectorAnalysis().process(sg)
SectorAnalysis().process(sg)