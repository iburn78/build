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
# os.environ["BUILD_COLLECT_NEWS"] = "true"
os.environ["BUILD_COLLECT_NEWS"] = "false"

# research
LLM_RESEARCH_REFRESH_THRES = 20 # days
SEARCH_CONTEXT_SIZE = "medium"
USAGE_REQUEST_LIMIT = 4
# os.environ["BUILD_LLM_RESEARCH"] = "true"
os.environ["BUILD_LLM_RESEARCH"] = "false"

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
THIS_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
ppd_ = os.path.dirname(THIS_PROJECT) 
BASE_DATA_DIR = os.path.join(ppd_, 'data') # in global data repo
BUILD_DIR = os.path.join(BASE_DATA_DIR, 'build') # in global data repo
GENERAL_DIR = os.path.join(BUILD_DIR , 'general') # to be created when needed
NEWS_DIR = os.path.join(BUILD_DIR , 'news')
PROFILE_NEWS_DIR = os.path.join(NEWS_DIR , 'profiles')
COMPONENT_NEWS_DIR = os.path.join(NEWS_DIR , 'components')
VALUECHAIN_NEWS_DIR = os.path.join(NEWS_DIR , 'valuechains')
PROFILES_DIR = os.path.join(BUILD_DIR , 'profiles')
COMPONENTS_DIR = os.path.join(BUILD_DIR , 'components')
VALUECHAIN_DIR = os.path.join(BUILD_DIR , 'valuechains')

os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(BUILD_DIR , exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)
os.makedirs(PROFILE_NEWS_DIR, exist_ok=True)
os.makedirs(COMPONENT_NEWS_DIR, exist_ok=True)
os.makedirs(VALUECHAIN_NEWS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(COMPONENTS_DIR, exist_ok=True)
os.makedirs(VALUECHAIN_DIR, exist_ok=True)

# may need to turn on local llm server (i.e., ollama: >> ollama serve)
OPENAI_CONF = os.path.join(ppd_, 'config/openai_api.json')
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

TEMPLATE_HTML = Path(THIS_PROJECT) / "tools" / "templates"  / "dict_template.html"
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

