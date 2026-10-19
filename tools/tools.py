import re
from data.tools.load import df_krx, get_name
from pydantic import BaseModel

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

class Member(BaseModel):
    # simple vehicle that carries only key and company name: works both for profile and segment
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

# member from company name (for segments: append (id))
def cn(name):
    return Member.from_name(name)

# member from key
def ck(key):
    return Member.from_key(key)
