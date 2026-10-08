import json
import sys
import shutil
from pathlib import Path
from build.tools.settings import (
    COMPONENTS_DIR,
    COMPONENT_NEWS_DIR,
    PROFILE_NEWS_DIR,
    PROFILES_DIR,
    VALUECHAIN_DIR,
    VALUECHAIN_NEWS_DIR,
)

'''
Deletion follows the following scope: 
- profiles remove their own files and associated segment files/news while keeping profile news;
- segments, components, and value chains remove their own JSON/PNG/HTML and news directory, leaving their members untouched.
- The server delegates deletion to a script that matches the exact model key.
'''

MODEL_DIRS = {
    "Profile": PROFILES_DIR,
    "Segment": PROFILES_DIR,
    "Component": COMPONENTS_DIR,
    "ValueChain": VALUECHAIN_DIR,
}

NEWS_DIRS = {
    "Segment": PROFILE_NEWS_DIR,
    "Component": COMPONENT_NEWS_DIR,
    "ValueChain": VALUECHAIN_NEWS_DIR,
}

def _resolve_json_path(model_type: str, object_id: str) -> Path:
    model_dir = Path(MODEL_DIRS[model_type])
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
    for suffix in (".json", ".png", ".html"):
        path = json_path.with_suffix(suffix)
        if path.is_file():
            path.unlink()
            deleted.append(str(path))
    return deleted

def _delete_news_dir(news_root: str | Path, filename: str) -> list[str]:
    news_dir = Path(news_root) / filename
    if not news_dir.is_dir():
        return []
    shutil.rmtree(news_dir)
    return [str(news_dir)]

def delete_instance(data: dict) -> dict:
    model_type = data.get("objectType")
    object_id = data.get("objectId")
    if model_type not in MODEL_DIRS or not isinstance(object_id, str) or not object_id:
        raise ValueError("Invalid model type or identifier")

    json_path = _resolve_json_path(model_type, object_id)
    try:
        model_data = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read model data: {json_path.name}") from error

    filename = json_path.stem
    profile_code = None
    if model_type == "Profile":
        profile_code = model_data.get("code") or model_data.get("key")
        if not isinstance(profile_code, str) or not profile_code:
            raise ValueError("Profile data has no valid company code")

    deleted = _delete_model_files(json_path)
    if model_type in NEWS_DIRS:
        deleted.extend(_delete_news_dir(NEWS_DIRS[model_type], filename))

    if model_type == "Profile":
        profile_dir = Path(PROFILES_DIR)
        segment_paths = []
        for candidate in profile_dir.glob("*.json"):
            if candidate == json_path:
                continue
            try:
                candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            is_segment = candidate_data.get("id") is not None
            belongs_to_profile = candidate_data.get("profile_code") == profile_code or (
                isinstance(candidate_data.get("key"), str)
                and candidate_data["key"].startswith(f"{profile_code}(")
                and is_segment
            )
            if is_segment and belongs_to_profile:
                segment_paths.append((candidate, candidate.stem))

        for segment_path, segment_filename in segment_paths:
            deleted.extend(_delete_model_files(segment_path))
            deleted.extend(_delete_news_dir(PROFILE_NEWS_DIR, segment_filename))

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
