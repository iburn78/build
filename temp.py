#%% 
from build.models.profile import Profile, ProfileManager
from build.analysis.sector_analysis import SectorAnalysis

code = '450080'
# pm = ProfileManager()
# pm.get_item(code)
# print(pm)

# sa = SectorAnalysis().get_from_code(code)
sa = SectorAnalysis().get_from_component_name('전구체', fill=True)
print(sa.fr_data)