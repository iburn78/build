#%%
import re, json
import holidays
from datetime import datetime, timedelta
from functools import lru_cache
from pydantic import BaseModel
import pandas as pd
from threading import RLock
from data.tools.load import df_krx, get_name
from build.models.settings import COMPONENTS_DIR, VALUECHAINS_DIR, REFS_DIR, CLASSIFICATION_PATH, CLASSIFICATION_STRUCTURE

df_krx = df_krx
get_name = get_name
df_sector = pd.read_pickle(CLASSIFICATION_PATH)
sector_structure = json.loads(CLASSIFICATION_STRUCTURE.read_text(encoding="utf-8"))
_df_sector_lock = RLock()

def sync_classification_structure() -> None:
    """Refresh subindustry member codes from the current sector summary."""
    with _df_sector_lock:
        if "classification" not in df_sector.columns:
            members = {}
        else:
            members = {}
            for code, classification in df_sector["classification"].items():
                if pd.isna(classification):
                    continue
                classification = str(classification).strip()
                if not classification or classification.lower() == "nan":
                    continue
                members.setdefault(classification, []).append(str(code))

        for sector in sector_structure.get("sectors", []):
            for group in sector.get("groups", []):
                for industry in group.get("industries", []):
                    for subindustry in industry.get("subindustries", []):
                        subindustry["companies"] = sorted(
                            members.get(str(subindustry.get("code")), [])
                        )
        CLASSIFICATION_STRUCTURE.parent.mkdir(parents=True, exist_ok=True)
        CLASSIFICATION_STRUCTURE.write_text(
            json.dumps(sector_structure, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


sync_classification_structure()

def _save_df_sector() -> None:
    CLASSIFICATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_sector.to_pickle(CLASSIFICATION_PATH)
    sync_classification_structure()

# Migrate older summary files before using the sector_group column.
if "sector_group" not in df_sector.columns and "class" in df_sector.columns:
    df_sector = df_sector.rename(columns={"class": "sector_group"})
    _save_df_sector()

def get_industries(
    company_code: str | None = None,
    class_code: str | None = None,
) -> dict:
    if (company_code is None) == (class_code is None):
        raise ValueError("Provide exactly one of company_code or class_code")

    if company_code is not None:
        company_code = str(company_code).strip().zfill(6)
        try:
            class_code = str(df_sector.loc[company_code, "sector_group"])
        except KeyError as error:
            raise ValueError(f"No KRICS class found for company code {company_code}") from error
    else:
        class_code = str(class_code).strip()

    matches = []
    for sector in sector_structure.get("sectors", []):
        groups = [group for group in sector.get("groups", []) if str(group.get("code")) == class_code]
        if groups:
            matches.append({**sector, "groups": groups})

    if not matches:
        raise ValueError(f"No KRICS sector/group found for class {class_code!r}")

    result = {"sectors": matches}
    return result

def save_company_classification(
    company_code: str,
    class_code: str,
    classification_code: str,
) -> None:
    """Save a company's group and final subindustry code when they change."""
    company_code = str(company_code).strip().zfill(6)
    if company_code not in df_sector.index:
        raise ValueError(f"Cannot save KRICS class for unknown company code {company_code}")
    with _df_sector_lock:
        class_code = str(class_code).strip()
        classification_code = str(classification_code).strip()
        if (
            str(df_sector.at[company_code, "sector_group"]) == class_code
            and "classification" in df_sector.columns
            and str(df_sector.at[company_code, "classification"]) == classification_code
        ):
            return
        df_sector.loc[company_code, "sector_group"] = class_code
        df_sector.loc[company_code, "classification"] = classification_code
        _save_df_sector()

def save_segment_classification(
    segment_code: str,
    company_code: str,
    classification_code: str,
) -> None:
    """Save a segment row with inherited company fields and its own leaf code."""
    segment_code = str(segment_code).strip()
    company_code = str(company_code).strip().zfill(6)
    classification_code = str(classification_code).strip()
    if company_code not in df_sector.index:
        raise ValueError(f"Cannot save segment classification without parent {company_code}")
    if "sector_group" not in df_sector.columns:
        raise ValueError("KRICS summary is missing the sector_group column")

    with _df_sector_lock:
        parent = df_sector.loc[company_code]
        inherited_columns = list(
            df_sector.columns[:df_sector.columns.get_loc("sector_group") + 1]
        )
        values = {column: parent[column] for column in inherited_columns}
        values["classification"] = classification_code
        if "classification" not in df_sector.columns:
            df_sector["classification"] = pd.Series(index=df_sector.index, dtype="object")

        if segment_code in df_sector.index:
            current = df_sector.loc[segment_code]
            if all(
                (pd.isna(current.get(column)) and pd.isna(value))
                or str(current.get(column)) == str(value)
                for column, value in values.items()
            ):
                return

        df_sector.loc[segment_code, list(values)] = list(values.values())
        _save_df_sector()

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

def print_components() -> None:
    print("#------------------------------------------")
    print("# COMPONENTS:")
    print("#------------------------------------------")
    for path in sorted(COMPONENTS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        namelist = []
        for listed_company in data.get("listed_companies", []):
            name = listed_company["name"]
            match = re.search(r"\(([A-Za-z])\)$", listed_company.get("key", ""))
            if match:
                name += f"({match.group(1)})"
            namelist.append(name)

        print(
            f"Component.get_item({data['key']!r}, "
            f"namelist={namelist!r})"
        )

def print_valuechains() -> None:
    print("#------------------------------------------")
    print("# VALUE CHAINS:")
    print("#------------------------------------------")
    for path in sorted(VALUECHAINS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        print("vc = ValueChain.get_item(")
        print(f"    key={data['key']!r},")
        print(f"    component_keys={data.get('component_keys', [])!r},")
        print(f"    valuechain_keys={data.get('valuechain_keys', [])!r},")
        print(")")

