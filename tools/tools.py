import os
import pandas as pd
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

pd_ = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
ppd_ = os.path.dirname(pd_) 
df_krx = pd.read_feather(os.path.join(ppd_, "trader/data_collect/data/df_krx.feather"))
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

client = OpenAI(
    base_url="http://localhost:11434/v1", # ollama
    api_key= "-", 
)

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

def get_local_LLM_response(prompt):
    chat_completion = client.chat.completions.create(
        model="gemma4", 
        messages=[
            {
                "role": "user",
                "content": (
                    prompt
                )
            }
        ],
    )
    
    response = chat_completion.choices[0].message.content
    return response

def get_name(code): 
    return str(df_krx.loc[code,'Name'])

def get_code_name(code, name): # santized code_name usable for dir or file
    return f"{code}_{sanitized_filename(name)}"

def sanitized_filename(name): # so that the name can be used as a filename
    name = re.sub(r'[<>:"/\\|?*]+', "", name)
    name = "_".join(name.split())
    if not name:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")[:-2]  
        name = f"unnamed_{ts}"
    return name

def get_overview(code: str): 
    url = (
        "https://wcomp.fnguide.com/CompanyInfo/Snapshot"
        f"?c_id=AA&menu_type=01&cmp_cd={code}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(
        url,
        headers=headers,
        timeout=10,
    )

    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser",
    )

    title = soup.select_one(
        "#bizSummaryHeader"
    )

    date = soup.select_one(
        "#bizSummaryDate"
    )

    content = soup.select_one(
        "#bizSummaryContent"
    )

    desc = ""

    if content:
        desc = "\n\n".join(
            li.get_text(
                " ",
                strip=True,
            )
            for li in content.select("li")
        )

    return {
        'title':(
            title.get_text(strip=True)
            if title else ""
        ),
        'date':(
            date.get_text(strip=True).strip("[]").replace("/","-")
            if date else ""
        ),
        'desc':desc,
    }
