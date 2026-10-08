from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import holidays

KRW_UNIT_KR = {
    1e12: 'jo',
    1e9: '10-uk',
    1e8: 'uk', 
}


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
    if pd.isna(x):
        return None
    return float(f"{x:.{n}g}")

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

    ret = df.pct_change()
    ret = ret.replace([np.inf, -np.inf], np.nan).dropna()

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
