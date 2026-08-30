from datetime import datetime, time
from zoneinfo import ZoneInfo
import holidays
from pathlib import Path
import pandas as pd
import numpy as np
import json
from html import escape
from data.load import get_df_krx

# -----------------------------------------------------------------------------------
# Definitions and setups
# -----------------------------------------------------------------------------------

KRW_UNIT_KR = {
    1e12: 'jo',
    1e9: '10-uk',
    1e8: 'uk', 
}

import os
import json
import re

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
# -----------------------------------------------------------------------------------
# Data generation
# -----------------------------------------------------------------------------------
def is_KRX_open(now=None, strict=False):
    """
    Returns True if KRX regular market is open now.
    
    Rules:
    - Mon~Fri
    - Not Korean public holiday
    - 09:00 ~ 15:30 KST (if strict==True)
    - or ~ 12:00 KST (if strict==False)
    """

    KR_HOLIDAYS = holidays.KR()
    kst = ZoneInfo("Asia/Seoul")

    if now is None:
        now = datetime.now(kst)
    else:
        now = now.astimezone(kst)

    today = now.date()

    # Weekend
    if now.weekday() >= 5:
        return False

    # Korean holiday
    if today in KR_HOLIDAYS:
        return False

    market_open = time(9, 0)
    if strict:
        market_close = time(15, 30)
    else:
        market_close = time(12, 00)

    return market_open <= now.time() < market_close

def get_slope_intercept(s: pd.Series):
    s = s.dropna()
    x = np.arange(len(s))
    y = s.values

    slope, intercept = np.polyfit(x,y,1)  
    return slope, intercept

# round up to n significant numbers
def round_sig(x, n=4):
    return float(f"{x:.{n}g}")

def dprint(d: dict):
    if isinstance(d, dict):
        print(json.dumps(d, indent=4, ensure_ascii=False))

def calc_increment(s: pd.Series, measure_duration, base_duration): 
    # designed only for non-negative series
    # args: 
    # - measure_duration: 20 (1 months)
    # - base_duration: 120 (6 months, required length)
    # return: [measure to base, slope]

    s = s.dropna()
    s = s[s != 0] # dropping zeros too (e.g., suspended days etc)
    if (s < 0).any(): raise ValueError(f"check nonnegative numbers in {s}")

    bd = min(len(s), base_duration)
    md = min(bd, measure_duration)

    slope, intercept = get_slope_intercept(s[-bd:])

    # define floor 
    # - if extrapolated_value becomes negative or close to zero, comparison with measure_periodis is meaningless
    _min = s[-bd:].mean()*0.3

    extrapolated_value = max(intercept + slope*(bd-md/2), _min)
    measure_duration_average = s[-md:].mean()

    measure_to_base_ratio = measure_duration_average/extrapolated_value

    return {
        'measure_to_base': round_sig(measure_to_base_ratio), 
        'slope': round_sig(slope),
    }

def calc_alpha_beta(
    stock: pd.Series, # price or marcap
    market: pd.Series, # index or marcap
    n = 1,
):
    """
    alpha : float
        Average return alpha per period if n = 1
        if n > 1, then the result is for n-period return 
    beta : float
        CAPM beta
    """

    df = pd.concat([stock, market], axis=1, join="inner").dropna()
    df.columns = ["stock", "market"]

    ret = df.pct_change().dropna()

    beta = ret["stock"].cov(ret["market"]) / ret["market"].var()
    _alpha = ret["stock"].mean() - beta * ret["market"].mean()
    alpha = (_alpha+1)**n - 1

    return {
        'alpha': round_sig(alpha),
        'beta': round_sig(beta),
    }

# -----------------------------------------------------------------------------------
# LLM 
# -----------------------------------------------------------------------------------
# local gemma4 (installed via ollama)
# standard way to call an local model (using openai template)
from openai import OpenAI
import base64, mimetypes

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

client = OpenAI(
    base_url="http://localhost:11434/v1", # ollama
    api_key="dummy"
)

def get_local_response(input_text, image_file=None, context_file=None, client=client, model="gemma4"):
    content = [
        {
            "type": "text",
            "text": input_text,
        }
    ]

    # optional context file: txt or md, etc
    if context_file is not None:
        with open(context_file, "r", encoding="utf-8") as f:
            context_text = f.read()

        content.append(
            {
                "type": "text",
                "text": f"\nContext of the request:\n{context_text}"
            }
        )

    # optional image
    if image_file is not None:
        with open(image_file, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        mime_type, _ = mimetypes.guess_type(image_file)
        mime_type = mime_type or "image/png"

        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_b64}",
                }
            }
        )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ]
    )

    return response.choices[0].message.content

# -----------------------------------------------------------------------------------
# Display dict in html
# -----------------------------------------------------------------------------------

def _fmt_value(key, value):
    if value is None:
        return "-"

    if isinstance(value, bool):
        return "✓" if value else "✗"

    if isinstance(value, float):
        if "(pct)" in key.lower() or "(%)" in key.lower():
            return f"{value:.2%}"
        return f"{value:,.6g}"

    if isinstance(value, int):
        return f"{value:,}"

    return str(value)

def _dict_signature(data):
    if not isinstance(data, dict):
        return ()

    return tuple(
        (
            key,
            _dict_signature(value) if isinstance(value, dict) else None
        )
        for key, value in data.items()
    )

def _same_signature(*dicts):
    """Return True if all dictionaries have the same nested structure."""
    if len(dicts) < 2:
        return True

    signature = _dict_signature(dicts[0])
    passed = all(_dict_signature(d) == signature for d in dicts[1:])
    if not passed:
        print(f"signature mismatching: ")
        for d in dicts:
            print(_dict_signature(d))
    return passed

def _section_row(key, level=0, colspan=1):
    return f"""    <tr class="section-row level-{level}">
        <td class="label" colspan="{colspan}">{escape(str(key))}</td>
    </tr>
"""

def _value_row(key, values=[], level=0):
    cells = "\n".join(
        f'        <td class="value">{escape(_fmt_value(key, v))}</td>'
        for v in values
    )

    return f"""    <tr class="value-row level-{level}">
        <td class="label">{escape(str(key))}</td>
{cells}
    </tr>
"""

def _render_rows(dict_list, level=0):
    """Flatten nested dictionaries into table rows."""
    rows = []
    for key, value in dict_list[0].items():
        values = [d[key] for d in dict_list]

        if isinstance(value, dict):
            rows.append(_section_row(key, level=level, colspan=len(dict_list)+1))
            rows.extend(_render_rows(values, level=level + 1))

        else:
            rows.append(_value_row(key, values, level=level))

    return rows

# general function
def dict_to_html(title, column_names: list, dict_list: list, template_html:Path, output_file=None):
    if not dict_list:
        raise ValueError("dict_list cannot be empty")

    if len(column_names) != len(dict_list):
        raise ValueError("column_names and dict_list must have the same length")

    if not _same_signature(*dict_list):
        raise ValueError("signatures not matching")

    rows = _render_rows(dict_list)

    header = f"""    <tr class="header-row">
        <th class="label">{escape(str(title))}</th>
        {"".join(
            f'<th class="value">{escape(str(name))}</th>'
            for name in column_names
        )}
    </tr>"""

    content = f"""
<table class="dict-table">
    <thead>
{header}    </thead>
    <tbody>
{"".join(rows)}    </tbody>
</table>"""

    template = template_html.read_text(encoding="utf-8")
    html = template.replace("{{ content }}", content)

    with open("templates/dict_template.css", "r", encoding="utf-8") as f:
        css = f.read()
        html_css = html.replace("{{ css }}", css)

    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(html_css, encoding="utf-8")
        print(f"file {output_file} is written...")
    else: 
        print(html)
