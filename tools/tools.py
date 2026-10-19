import re
from data.tools.load import df_krx, get_name

df_krx = df_krx
get_name = get_name

def sanitized_filename(name): 
    if name is None or "": raise ValueError(f'name should be given: {name}')
    name = re.sub(r'[<>:"/\\|?*]+', "", name)
    name = "_".join(name.split())
    return name

def get_FN_GUIDE_url(code):
    return (
            "https://wcomp.fnguide.com/CompanyInfo/Snapshot"
            f"?c_id=AA&menu_type=01&cmp_cd={code}"
    )

def get_NAVER_url(code):
    return f"https://stock.naver.com/domestic/stock/{code}/price"

# returns name/code, id:char in name(id) or code(id)
def get_id(s: str) -> tuple[str, str | None]:
    m = re.search(r"\(([A-Za-z])\)$", s)
    if not m:
        return s, None

    return s[:m.start()], m.group(1)