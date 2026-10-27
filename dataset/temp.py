#%%

from build.models.profile import Profile
from build.analysis.sector_analysis import FinancialsData

a = Profile.get_item('파인엠텍')

print(a.financials)

b = FinancialsData(key='441270')
print(b.ma_data)