import os
import json
from pathlib import Path

#------------------------------------------------------------------
# Project parameters:
#------------------------------------------------------------------

# LLMs: local, ollama, openai
DEFAULT_BIZ_LLM = 'ollama' 
DEFAULT_RESEARCH_LLM = 'ollama'
DEFAULT_NEWS_LLM = 'ollama'
AGENT_RETRIES = 5

# financials
FINANCIALS_UPDATE_PERIOD_HR = 1 # Hours

# news
NEWS_REFRESH_THRES = 3 # days
NUM_TO_CRAWL = 3 # number of articles to crawl for each keyword
NUM_TO_FEED_LLM = 10 # number of articles to provide to LLM
os.environ["BUILD_COLLECT_NEWS"] = "1" # True: 1, False: 0

# research
LLM_RESEARCH_REFRESH_THRES = 20 # days
SEARCH_CONTEXT_SIZE = "medium"
USAGE_REQUEST_LIMIT = 4
OLLAMA_WEB_SEARCH_MAX_ATTEMPTS = 4
os.environ["BUILD_LLM_RESEARCH"] = "1" # True: 1, False: 0

# parallel running
NUM_THREAD_TO_RUN = 8

#------------------------------------------------------------------
# Model parameters:
#------------------------------------------------------------------

# profile
OVERVIEW_REFRESH_THRES = 30 # days
MAX_SEGMENTS = 5
PROFILE_SEARCH_THEME = ['실적', '전망']

# segment
SEGMENT_SEARCH_THEME = ['사업부 실적', '전망']

# component
COMPONENT_SEARCH_THEME = ['섹터 전망']

# valuechian
VALUECHAIN_SEARCH_THEME = ['산업 전망', '밸류체인']

#------------------------------------------------------------------
# Display dict in html
#------------------------------------------------------------------

COLLAPSED_PATHS = {
    'meta', 
    'assess_data.alpha_beta.from_start_date', 
    'shape.financials'
}
NO_CHART_KEYS = {
    'key',
    'unit',
    'code',
    '-m_rank', 
    '-r_rank',
    '-o_rank',
}

#------------------------------------------------------------------
# Project settings:
#------------------------------------------------------------------
THIS_PROJECT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = THIS_PROJECT.parent
BASE_DATA_DIR = PROJECTS_DIR / "data"
BUILD_DIR = BASE_DATA_DIR / "build"
GENERAL_DIR = BUILD_DIR / "general" # to be created when needed
NEWS_DIR = BUILD_DIR / "news"
PROFILE_NEWS_DIR = NEWS_DIR / "profiles"
COMPONENT_NEWS_DIR = NEWS_DIR / "components"
VALUECHAIN_NEWS_DIR = NEWS_DIR / "valuechains"
PROFILES_DIR = BUILD_DIR / "profiles"
COMPONENTS_DIR = BUILD_DIR / "components"
VALUECHAINS_DIR = BUILD_DIR / "valuechains"

for directory in (
    GENERAL_DIR,
    PROFILE_NEWS_DIR,
    COMPONENT_NEWS_DIR,
    VALUECHAIN_NEWS_DIR,
    PROFILES_DIR,
    COMPONENTS_DIR,
    VALUECHAINS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

# may need to turn on local llm server (i.e., ollama: >> ollama serve)
OPENAI_CONF = PROJECTS_DIR / "config" / "openai_api.json"
with open(OPENAI_CONF, 'r') as json_file:
    config = json.load(json_file)
OPENAI_API_KEY = config['openai_api_key']
OLLAMA_API_KEY = config['ollama_api_key']

# Set BUILD_COLLECT_NEWS=0 to skip news crawling and summarization during builds.
COLLECT_NEWS = os.getenv("BUILD_COLLECT_NEWS", "1").strip().lower() not in {
    "0", "false", "no", "off", "False"
}

# Set BUILD_LLM_RESEARCH=0 to skip LLM research during builds.
COLLECT_LLM_RESEARCH = os.getenv("BUILD_LLM_RESEARCH", "1").strip().lower() not in {
    "0", "false", "no", "off", "False"
}

QUARTERLY_PERFORMANCES_URL = 'http://10.245.110.101:3000'

TEMPLATE_HTML = THIS_PROJECT / "tools" / "templates" / "dict_template.html"
INDEX_HTML = "http://localhost:3000"

def llm_selector(mode='local'):
    if mode == 'ollama':
        base_url='http://localhost:11434/v1'
        api_key = OLLAMA_API_KEY
        model = "gemma4:31b-cloud"

    elif mode == 'openai':
        base_url = f"https://api.openai.com/v1"
        api_key = OPENAI_API_KEY
        model = "gpt-5-mini"

    elif mode == 'local':
        base_url='http://localhost:11434/v1'
        api_key = '-'
        model = "gemma4"

    else: 
        print('mode is not available')
        return ["", "", ""]
    
    return [base_url, api_key, model]
