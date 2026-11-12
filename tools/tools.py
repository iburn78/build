import re
import unicodedata
import holidays
from data.tools.load import df_krx, get_name
from datetime import datetime, timedelta
from functools import lru_cache
from pydantic import BaseModel

df_krx = df_krx
get_name = get_name

def sanitized_filename(name): 
    if name is None or "": raise ValueError(f'name should be given: {name}')
    name = re.sub(r'[<>:"/\\|?*]+', "", name)
    name = "_".join(name.split())
    return name

def nfc(value):
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value

def get_FN_GUIDE_url(code):
    return (
            "https://wcomp.fnguide.com/CompanyInfo/Snapshot"
            f"?c_id=AA&menu_type=01&cmp_cd={code}"
    )

def get_NAVER_url(code):
    return f"https://stock.naver.com/domestic/stock/{code}/price"


def remove_nonlanguage_parentheticals(text: str) -> str:
    """Remove parentheticals that contain no English or Korean letters."""
    return re.sub(
        r"\(([^()]*)\)",
        lambda match: "" if not re.search(r"[A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]", match.group(1)) else match.group(0),
        text,
    )

def business_days_elapsed(start: datetime, end: datetime) -> int:
    """Count completed Korean business days between two naive datetimes."""
    if end <= start:
        return 0

    day = start.date() + timedelta(days=1)
    end_day = end.date()
    count = 0
    while day <= end_day:
        if is_korean_business_day(day):
            count += 1
        day += timedelta(days=1)

    # A weekday only counts once the corresponding time of day has elapsed.
    if is_korean_business_day(end.date()) and end.time() < start.time():
        count -= 1
    return count

@lru_cache(maxsize=16)
def _korean_holidays(year: int):
    """Build each year's Korean holiday calendar once, even across many models."""
    return holidays.KR(years=year)

def is_korean_business_day(day) -> bool:
    """Return whether a date is a weekday and not a Korean public holiday."""
    return day.weekday() < 5 and day not in _korean_holidays(day.year)

# returns name/code, id:char in name(id) or code(id)
def get_id(s: str) -> tuple[str, str | None]:
    m = re.search(r"\(([A-Za-z])\)$", s)
    if not m:
        return s, None

    return s[:m.start()], m.group(1)

class ListedCompany(BaseModel):
    # Holds a company or segment key and display name.
    key: str
    name: str

    @classmethod
    def from_name(cls, name, df_krx=df_krx):
        def _get_code_name(name, df_krx=df_krx):
            # 1. exact match first
            matched = df_krx[df_krx["Name"] == name]
            if len(matched) == 1:
                return str(matched.index[0]), matched.iloc[0]["Name"]

            # 2. fallback to contains
            matched = df_krx[df_krx["Name"].str.contains(
                name,
                case=False,
                na=False
            )]

            if len(matched) == 1:
                return str(matched.index[0]), matched.iloc[0]["Name"]

            if len(matched) == 0:
                raise ValueError(
                    f"No company found matching name: '{name}'"
                )

            raise ValueError(
                f"Ambiguous company name '{name}': "
                f"{matched['Name'].tolist()}"
            )

        _name, id = get_id(name)
        code, company_name = _get_code_name(_name)
        key = f"{code}({id})" if id else code
        company_name = f"{company_name}({id})" if id else company_name
        return cls(
            key = key,
            name = company_name
        )

    @classmethod
    def from_key(cls, key, df_krx=df_krx):
        code, id = get_id(key)

        matched = df_krx.loc[df_krx.index == code]
        if len(matched) != 1:
            raise ValueError(f"Invalid code: {code}")

        name = str(matched.iloc[0]["Name"])
        if id:
            name = f"{name}({id})"

        return cls(
            key = f"{code}({id})" if id else code,
            name=name
        )

# Resolve a listed company by name; segment IDs may be appended to the name.
def cn(name):
    return ListedCompany.from_name(name)

# Resolve a listed company by key.
def ck(key):
    return ListedCompany.from_key(key)
