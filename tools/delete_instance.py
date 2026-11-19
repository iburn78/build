import json
import sys
import shutil
from pathlib import Path
from build.models.settings import (
    COMPONENTS_DIR,
    COMPONENT_NEWS_DIR,
    PROFILE_NEWS_DIR,
    PROFILES_DIR,
    VALUECHAINS_DIR,
    VALUECHAIN_NEWS_DIR,
)

'''
Deletion follows the following scope: 
- profiles remove their own files/news and all associated segment files/news;
- segments, components, and value chains remove their own JSON/PNG/HTML and news directory, leaving their listed companies untouched.
- The server delegates deletion to a script that matches the exact model key.
'''

MODEL_DIRS = {
    "Profile": PROFILES_DIR,
    "Segment": PROFILES_DIR,
    "Component": COMPONENTS_DIR,
    "ValueChain": VALUECHAINS_DIR,
}

# Profile news are kept intentionally
NEWS_DIRS = {
    "Segment": PROFILE_NEWS_DIR,
    "Component": COMPONENT_NEWS_DIR,
    "ValueChain": VALUECHAIN_NEWS_DIR,
}

def _resolve_json_path(model_type: str, object_id: str) -> Path:
    model_dir = MODEL_DIRS[model_type]
    matches = []
    for path in model_dir.glob("*.json"):
        try:
            model_data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if model_data.get("key") == object_id:
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(f"{model_type} not found or identifier is ambiguous: {object_id}")
    return matches[0]

def _delete_model_files(json_path: Path) -> list[str]:
    deleted = []
    for suffix in (".json", ".png", ".html", ".md"):
        path = json_path.with_suffix(suffix)
        if path.is_file():
            path.unlink()
            deleted.append(str(path))
    return deleted

def _delete_news_dir(news_root: Path, filename: str) -> list[str]:
    news_dir = news_root / filename
    if not news_dir.is_dir():
        return []
    shutil.rmtree(news_dir)
    return [str(news_dir)]

def _normalize_stock_code(value: object) -> str:
    code = str(value).strip()
    return code.zfill(6) if code.isdigit() else code

def delete_profile_by_code(stock_code: str) -> dict:
    """Delete a profile, its segments, and all of their generated/news files."""
    stock_code = _normalize_stock_code(stock_code)
    profiles = []
    segments = []
    for path in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if data.get("id") is not None:
            key = str(data.get("key", ""))
            parent_code = data.get("profile_code") or key.split("(", 1)[0]
            if _normalize_stock_code(parent_code) == stock_code:
                segments.append(path)
        elif _normalize_stock_code(data.get("code") or data.get("key", "")) == stock_code:
            profiles.append(path)

    if len(profiles) > 1:
        raise ValueError(f"Profile code is ambiguous: {stock_code}")

    deleted = []
    if profiles:
        profile_path = profiles[0]
        deleted.extend(_delete_model_files(profile_path))

    for segment_path in segments:
        deleted.extend(_delete_model_files(segment_path))

    # Remove parent and segment news folders, including folders orphaned by
    # an earlier interrupted cleanup that no longer have matching JSON files.
    for news_dir in PROFILE_NEWS_DIR.iterdir():
        if (
            news_dir.is_dir()
            and (
                news_dir.name.startswith(f"{stock_code}_")
                or news_dir.name.startswith(f"{stock_code}(")
            )
        ):
            shutil.rmtree(news_dir)
            deleted.append(str(news_dir))

    return {"ok": True, "deleted": deleted}

def delete_instance(data: dict) -> dict:
    model_type = data.get("objectType")
    object_id = data.get("objectId")
    if model_type not in MODEL_DIRS or not isinstance(object_id, str) or not object_id:
        raise ValueError("Invalid model type or identifier")

    if model_type == "Profile":
        return delete_profile_by_code(object_id)

    json_path = _resolve_json_path(model_type, object_id)
    try:
        model_data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read model data: {json_path.name}") from error

    filename = json_path.stem
    deleted = _delete_model_files(json_path)
    if model_type in NEWS_DIRS:
        deleted.extend(_delete_news_dir(NEWS_DIRS[model_type], filename))

    return {"ok": True, "deleted": deleted}

if __name__ == "__main__":
    try:
        result = delete_instance(json.load(sys.stdin))
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps(result))
    except Exception as error:
        import traceback

        traceback.print_exc(file=sys.stdout)
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps({"ok": False, "error": str(error)}))
        sys.exit(1)
