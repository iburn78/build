import os
import re
import json
from data.load import get_df_krx

pd_ = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
ppd_ = os.path.dirname(pd_) 
BASE_DATA_DIR = os.path.join(pd_, 'data')
GENERAL_DIR = os.path.join(BASE_DATA_DIR, 'general') # to be created when needed
NEWS_DIR = os.path.join(BASE_DATA_DIR, 'news')
PROFILES_DIR = os.path.join(BASE_DATA_DIR, 'profiles')
COMPONENTS_DIR = os.path.join(BASE_DATA_DIR, 'components')
VALUECHAIN_DIR = os.path.join(BASE_DATA_DIR, 'valuechains')

os.makedirs(BASE_DATA_DIR, exist_ok=True)
os.makedirs(NEWS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(COMPONENTS_DIR, exist_ok=True)
os.makedirs(VALUECHAIN_DIR, exist_ok=True)

OPENAI_CONF = os.path.join(ppd_, 'config/openai_api.json')
with open(OPENAI_CONF, 'r') as json_file:
    config = json.load(json_file)
OPENAI_API_KEY = config['openai_api_key']
OLLAMA_API_KEY = config['ollama_api_key']

df_krx = get_df_krx()

def get_name(code): 
    return str(df_krx.loc[code,'Name'])

def sanitized_filename(name): 
    if name is None or "": raise ValueError(f'name should be given: {name}')
    name = re.sub(r'[<>:"/\\|?*]+', "", name)
    name = "_".join(name.split())
    return name

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