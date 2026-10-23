from datetime import datetime, time
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import holidays

DEFAULT_KRW_UNIT: float = 1e9 # 10 억원
KRW_UNIT_KR = {
    1e6: '100 man',
    1e7: '1k man',
    1e8: 'uk',
    1e9: '10 uk',
    1e10: '100 uk',
    1e11: '1k uk',
    1e12: 'jo',
    1e13: '10 jo',
    1e14: '100 jo',
    1e15: '1k jo',
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
    if len(s) == 0:
        return 0.0, 0.0
    if len(s) == 1:
        return 0.0, float(s.iloc[0])
    x = np.arange(len(s))
    y = s.values
    slope, intercept = np.polyfit(x,y,1)  
    return slope, intercept

# round up to n significant numbers
def round_sig(x, n=3, na_to_zero=False):
    if pd.isna(x) or not np.isfinite(x):
        return 0 if na_to_zero else np.nan
    return float(f"{x:.{n}g}")

def calc_increment(s: pd.Series, measure_duration, base_duration):
    # Designed only for non-negative series
    # args: 
    # - measure_duration: 20 (1 months)
    # - base_duration: 120 (6 months, required length)
    # return: [measure to base, slope]
    # Returns NaN metrics if insufficient valid data remains.

    s = s[np.isfinite(s) & (s != 0)] # dropping zeros too (e.g., suspended days etc)

    if (s < 0).any():
        raise ValueError(f"check nonnegative numbers in {s}")

    bd = min(len(s), base_duration)
    md = min(bd, measure_duration)

    if md == 0:
        return {'measure_to_base': np.nan, 'slope': np.nan}

    slope, intercept = get_slope_intercept(s.iloc[-bd:])

    # Floor to avoid meaningless comparisons near zero
    _min = s.iloc[-bd:].mean() * 0.3

    extrapolated_value = max(intercept + slope * (bd - md / 2), _min)
    measure_duration_average = s.iloc[-md:].mean()

    measure_to_base_ratio = measure_duration_average / extrapolated_value

    return {
        'measure_to_base': round_sig(measure_to_base_ratio),
        'slope': round_sig(slope),
    }


def calc_alpha_beta(
    stock: pd.Series,
    market: pd.Series,
    n=1,
):
    """
    alpha: Average return alpha per period if n = 1.
           If n > 1, result is for n-period return.
    beta: CAPM beta.
    """

    df = pd.concat([stock, market], axis=1, join="inner")
    df.columns = ["stock", "market"]

    df = df.replace([np.inf, -np.inf], np.nan).dropna()

    ret = df.pct_change()
    ret = ret.replace([np.inf, -np.inf], np.nan).dropna()

    if len(ret) < 2 or ret["market"].var() == 0:
        return {'alpha': np.nan, 'beta': np.nan}

    beta = ret["stock"].cov(ret["market"]) / ret["market"].var()
    _alpha = ret["stock"].mean() - beta * ret["market"].mean()
    alpha = (1 + _alpha) ** n - 1

    if not np.isfinite(alpha) or not np.isfinite(beta):
        return {'alpha': np.nan, 'beta': np.nan}

    return {
        'alpha': round_sig(alpha),
        'beta': round_sig(beta),
    }

# -----------------------------------------------------------------------------------
# LLM 
# -----------------------------------------------------------------------------------
# local gemma4 (installed via ollama)
# Standard way to call a local model using the OpenAI-compatible API.
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
