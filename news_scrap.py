#%% 
from scraper.tools.crawl_news import crawl_news
from scraper.company_profile import CompanyScraper
import os

def generate_news(profile):

    # USE FORMAL KEYWORDS 
    search_set = [profile.key_theme, '실적']  ###_ key theme is too broad... 

    # Dest Dir: code as dir name
    _dest = profile.code

    # under company code as dir name: subdirs are ...
    subdir_set = ['overall', 'performance']

    for k, d in zip(search_set, subdir_set):        
        _request = profile.name + ' ' + k
        _dest_dir = os.path.join(_dest, d)
        crawl_news(_request, max_result=self.crawl_max_results, dest_dir=_dest_dir)

    # If not satisfactory, then may refine search using keywords
    pass

if __name__ == "__main__":
    code = '000660'
    cs = CompanyScraper()
    profile = cs.get_profile(code)
    generate_news(profile)