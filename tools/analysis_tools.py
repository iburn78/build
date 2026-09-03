from datetime import datetime, time
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import numpy as np
import json
from html import escape
import holidays
import requests
from build.tools.settings import THIS_PROJECT, QUARTERLY_PERFORMANCES_URL
from pydantic import BaseModel

KRW_UNIT_KR = {
    1e12: 'jo',
    1e9: '10-uk',
    1e8: 'uk', 
}

# HTML 
TEMPLATE_HTML = Path(THIS_PROJECT) / "analysis" / "templates"  / "dict_template.html"
COLLAPSED_PATHS = {
    'meta', 
    'assess_data.alpha_beta.from_start_date', 
    'shape.financials'
}
year = str(datetime.today().year)

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
def round_sig(x, n=3):
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
        return (
            '<span class="true_bool">✓</span>'
            if value
            else '<span class="false_bool">✗</span>'
        )

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

def _section_row(key, level=0, colspan=1, collapsed=False):
    return f"""    
                        <tr class="section-row level-{level}{" collapsed" if collapsed else ""}">
                            <td class="label" colspan="{colspan}">{escape(str(key))}</td>
                        </tr>"""

def _value_row(key, values=None, level=0):
    values = values or []
    cells = "".join(
        f'''
                            <td class="value">{_fmt_value(key, v)}</td>'''
        for v in values
    ).strip()

    return f"""        
                        <tr class="value-row level-{level}">
                            <td class="label">{escape(str(key))}</td>
                            {cells}
                        </tr>"""

def _render_rows(dict_list, level=0, path="", collapsed_paths=None):
    """Flatten nested dictionaries into table rows."""
    collapsed_paths = collapsed_paths or set()
    rows = []
    for key, value in dict_list[0].items():
        current_path = f"{path}.{key}" if path else str(key)
        values = [d[key] for d in dict_list]

        if isinstance(value, dict):
            collapsed = current_path in collapsed_paths
            rows.append(_section_row(key, level=level, colspan=len(dict_list)+1, collapsed=collapsed))
            rows.extend(_render_rows(values, level=level + 1, path=current_path, collapsed_paths=collapsed_paths))

        else:
            rows.append(_value_row(key, values, level=level))

    return rows

# column_names = [{'name': , 'link': }, ...]
def _render_header(title, column_names):
    cells = []

    for column in column_names:
        name = escape(str(column["name"]))
        link = column.get("link")

        if link:
            name = f'<a href="../{escape(str(link))}">{name}</a>'

        cells.append(f'''
                            <th class="value">{name}</th>''')

    return f"""<tr class="header-row">
                            <th class="label">{escape(str(title))}</th>
                            {"".join(cells).strip()}
                        </tr>"""

def _render_table(header, rows): 
    return f"""<thead>
                        {header}    
                    </thead>
                    <tbody>
                        {"".join(rows).strip()}    
                    </tbody>"""

def _url_exists(url):
    try:
        return requests.get(url, stream=True, timeout=2).ok
    except requests.RequestException:
        return False

def _render_images(output_file, meta_dict):
    images = []

    sa_image = Path(output_file).with_suffix(".png")
    if sa_image.exists():
        images.append(sa_image.name)

    code = meta_dict.get('code')
    # only profiles have string format code (otherwise meta['code'] is a list)
    if isinstance(code, str):
        url = f"{QUARTERLY_PERFORMANCES_URL}/data/{code}.png"
        if _url_exists(url):
            images.append(url)
        else: 
            print(f'url {url} not reached')

    # ------------------------------
    # may add additional images here
    # ------------------------------

    return "".join(
        f'''
            <div class="chart-card">
                <img src="{image}" class="analysis-image" onclick="openPopup('{image}');">
            </div>'''
        for image in images
    ).strip()

def _render_financials(title, column_names: list, dict_list: list, output_file: Path, collapsed_paths=COLLAPSED_PATHS):
    header = _render_header(title, column_names)
    rows = _render_rows(dict_list, collapsed_paths=collapsed_paths)
    table_content = _render_table(header, rows)
    images = _render_images(output_file, dict_list[0].get('meta', {}))
    return f"""<h3>Financials Analysis</h3>
    <div class="dashboard">
        <div class="table-panel">
            <div class="table-wrapper">
                <div class="table-controls">
                    <button onclick="expandAll()">Expand All</button>
                    <button onclick="collapseAll()">Collapse All</button>
                </div>
                <table class="dict-table">
                    {table_content}
                </table>
            </div>
        </div>
        <div class="charts-panel">
            { images }
        </div>
    </div>"""


def _render_qualitative_value(value):
    """Recursively render dict, list, and scalar values as HTML."""
    # Pydantic BaseModel → dict
    if isinstance(value, BaseModel):
        value = value.model_dump()

    # Nested dict
    if isinstance(value, dict):
        rows = []

        for key, val in value.items():
            rows.append(f"""
                            <tr>
                                <th>{escape(str(key))}</th>
                                <td>{_render_qualitative_value(val)}</td>
                            </tr>""")

        return f"""<table class="qualitative-table">
                        <tbody>
                            {"".join(rows).strip()}
                        </tbody>
                    </table>"""

    # List
    elif isinstance(value, list):
        rows = []

        for item in value:
            rows.append(f"""
                            <tr>
                                <td>{_render_qualitative_value(item)}</td>
                            </tr>""")

        return f"""<table class="qualitative-table">
                        <tbody>
                            {"".join(rows).strip()}
                        </tbody>
                    </table>"""

    # Simple value
    else:
        return escape(str(value))

def _render_qualitative(qual_dict):
    if not qual_dict:
        return ""

    cards = []
    for key, value in qual_dict.items():
        title = escape(str(key))
        content = _render_qualitative_value(value)

        cards.append(f"""
            <div class="qualitative-card">
                <h4>{title}</h4>
                <div class="qualitative-content">
                    {content}
                </div>
            </div>""")

    return f"""<h3>Qualitative Analysis</h3>
    <div class="qualitative-section">
        <div class="qualitative-grid">
            {"".join(cards).strip()}
        </div>
    </div>"""

# list all news articles in the given folder newest first
def _render_news(news_dir):
    if news_dir is None or not news_dir.exists(): return ""
    
    paths = sorted(
        news_dir.glob("*.md"),
        key=lambda p: p.name,
        reverse=True,  # yyyy-mm-dd prefix → newest first
    )

    if not paths:
        return ""

    rows = []

    for path in paths:
        rows.append(f"""
            <div class="news-row">
                <a href="#" onclick="openPopup('{path.as_uri()}'); return false;">
                    {path.stem.replace('_', ' ')}
                </a>
            </div>
        """)

    return f"""
    <h3>News</h3>
    <div class="news-section">
        {"".join(rows).strip()}
    </div>
    """

def render_html(title, column_names: list, dict_list: list, qual_dict: dict, news_dir: None,
                 output_file: Path, template_html:Path = TEMPLATE_HTML, 
                 collapsed_paths=COLLAPSED_PATHS):
    if not dict_list:
        raise ValueError("dict_list cannot be empty")

    if len(column_names) != len(dict_list):
        raise ValueError("column_names and dict_list must have the same length")

    if not _same_signature(*dict_list):
        raise ValueError("signatures not matching")

    financials_section = _render_financials(title, column_names, dict_list, output_file, collapsed_paths)
    qual_section = _render_qualitative(qual_dict)
    news_section = _render_news(news_dir)

    html = template_html.read_text(encoding="utf-8")
    html = html.replace("{{ year }}", year)
    html = html.replace("{{ financials }}", financials_section)
    html = html.replace("{{ qualitative }}", qual_section)
    html = html.replace("{{ news }}", news_section)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding="utf-8")
    print(f"file {output_file} is written...")
