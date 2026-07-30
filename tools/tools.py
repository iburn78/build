import os
import pandas as pd
from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import json
import re
from pathlib import Path
from pydantic import BaseModel 
from datetime import datetime
from typing import ClassVar


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
    return f"{code}_{sanitized_name(name)}"

def sanitized_name(name): # so that the name can be used as a filename
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

class JsonModel(BaseModel):
    DIR: ClassVar[str] = "" # overridden by subclasses, and json does not include ClassVars / not validate either
    name: str

    def filename(self) -> str:
        return sanitized_name(self.name)

    def save_to_file(self):
        path = Path(self.DIR) / f"{self.filename()}.json"
        path.write_text(
            self.model_dump_json(indent=4, exclude_none=True),
            encoding="utf-8",
        )

    @classmethod
    def load_from_file(cls, path: str | Path):
        return cls.model_validate_json(
            Path(path).read_text(encoding="utf-8")
        )

    def key(self) -> str:
        return self.name

    @classmethod
    def load_all(cls): # dict[str, JsonModel]
        objects_dict = {}

        for path in Path(cls.DIR).glob("*.json"):
            try:
                obj = cls.load_from_file(path)
                objects_dict[obj.key()] = obj
            except Exception as e:
                print(f"Skipping {path}: {e}")

        return objects_dict

class Company(BaseModel):
    name: str
    code: str

    @classmethod
    def from_name(cls, name, df_krx=df_krx):
        # 1. exact match first
        matched = df_krx[df_krx["Name"] == name]

        if len(matched) == 1:
            return cls(
                name=matched.iloc[0]["Name"],
                code=str(matched.index[0])
            )

        # 2. fallback to contains
        matched = df_krx[df_krx["Name"].str.contains(
            name,
            case=False,
            na=False
        )]

        if len(matched) == 1:
            return cls(
                name=matched.iloc[0]["Name"],
                code=str(matched.index[0])
            )

        if len(matched) == 0:
            raise ValueError(
                f"No company found matching name: '{name}'"
            )

        raise ValueError(
            f"Ambiguous company name '{name}': "
            f"{matched['Name'].tolist()}"
        )

    @classmethod
    def from_code(cls, code, df_krx=df_krx):
        if code not in df_krx.index:
            raise ValueError(f"Invalid code: {code}")

        return cls(
            name=str(df_krx.loc[code, "Name"]),
            code=str(code)
        )

def cn(name):
    return Company.from_name(name)

def cc(code):
    return Company.from_code(code)

class Component(JsonModel): 
    DIR = COMPONENTS_DIR
    
    companies: list[Company] # listed domestic
    updated: str = ""
    note: str = "" 

class ValueChain(JsonModel): 
    DIR = VALUECHAIN_DIR

    components: dict[str, Component] 
    updated: str = ""
    note: str = "" 
