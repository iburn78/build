
from build.models.profile import ProfileManager
from build.analysis.sector_analysis import SectorAnalysis

code = '005930'
pm = ProfileManager()
cp = pm.get_item(code)

SectorAnalysis().process_profile(cp)
