"""Reassign one profile or segment to a KRICS subindustry."""
import json
import re
import sys

from build.models.profile import Profile
from build.models.segment import Segment
from build.tools.tools import (
    df_sector,
    save_company_classification,
    save_segment_classification,
    sector_structure,
)


MODEL_CLASSES = {"Profile": Profile, "Segment": Segment}


def _find_subindustry(code: str) -> dict | None:
    for sector in sector_structure.get("sectors", []):
        for group in sector.get("groups", []):
            for industry in group.get("industries", []):
                for subindustry in industry.get("subindustries", []):
                    if str(subindustry.get("code", "")) == code:
                        return {
                            "sector": f"{sector['name']['ko']} ({sector['code']})",
                            "group": f"{group['name']['ko']} ({group['code']})",
                            "industry": f"{industry['name']['ko']} ({industry['code']})",
                            "subindustry": f"{subindustry['name']['ko']} ({subindustry['code']})",
                            "group_code": str(group["code"]),
                        }
    return None


def _load_item(object_type: str, object_id: str):
    model_class = MODEL_CLASSES.get(object_type)
    if model_class is None:
        raise ValueError("Only Profile and Segment classifications can be reassigned.")
    matches = []
    for path in model_class.DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("key", "")) == object_id:
            matches.append(path)
    if len(matches) != 1:
        raise ValueError(f"{object_type} not found: {object_id}")
    item = model_class._load_from_path(matches[0])
    if item is None:
        raise ValueError(f"Could not load {object_type}: {object_id}")
    if not isinstance(item.financials, dict) or not isinstance(item.financials.get("meta"), dict):
        raise ValueError(f"{object_type} has no saved financial classification to update.")
    return item


def _parent_group_code(item) -> str | None:
    if isinstance(item, Segment):
        parent_code = str(item.profile_code).strip().zfill(6)
        if parent_code in df_sector.index:
            value = df_sector.at[parent_code, "sector_group"]
            if value is None or str(value).strip().lower() in {"", "nan", "none"}:
                return None
            group_code = str(value).strip()
            if group_code.endswith(".0"):
                group_code = group_code[:-2]
            return group_code.zfill(2) if group_code.isdigit() else group_code
    return None


def _write_classification(item, classification: dict) -> None:
    if isinstance(item, Segment):
        save_segment_classification(
            item.key, item.profile_code, classification["subindustry"].rsplit("(", 1)[1][:-1]
        )
    else:
        group_code = classification["group"].rsplit("(", 1)[1][:-1]
        subindustry_code = classification["subindustry"].rsplit("(", 1)[1][:-1]
        save_company_classification(item.code, group_code, subindustry_code)
    item.financials["meta"]["classification"] = {
        key: classification[key]
        for key in ("sector", "group", "industry", "subindustry")
    }
    item.save_to_file()


def _refresh_page(item) -> None:
    if isinstance(item, Profile):
        item._get_subitems()
        item._subitems_financials_processed = [
            segment.financials for segment in item.get_subitems().values()
        ]
    else:
        item._subitems_financials_processed = []
    item.create_html()


def reassign_classification(data: dict) -> dict:
    object_type = data.get("objectType")
    object_id = data.get("objectId")
    action = data.get("action")
    if not isinstance(object_id, str) or not object_id:
        raise ValueError("Invalid profile or segment identifier.")
    if action not in {"reassign", "auto"}:
        raise ValueError("Choose Reassign or Auto.")

    item = _load_item(object_type, object_id)
    if action == "auto":
        original = item.financials["meta"].get("classification")
        item.financials["meta"]["classification"] = None
        classification = item._classification_for_financials()
        if not item._classification_is_complete(classification):
            item.financials["meta"]["classification"] = original
            raise ValueError("Automatic classification did not return a valid result.")
    else:
        code = str(data.get("classificationCode", "")).strip()
        if not re.fullmatch(r"\d{4}", code):
            raise ValueError("Enter a valid 4-digit classification code.")
        classification = _find_subindustry(code)
        if classification is None:
            raise ValueError(f"{code} is not a valid classification in the taxonomy.")
        parent_group = _parent_group_code(item)
        if parent_group is not None and classification["group_code"] != parent_group:
            raise ValueError(
                f"{code} is valid, but belongs to group {classification['group']}. "
                "A segment must stay within its parent profile's group."
            )

    _write_classification(item, classification)
    _refresh_page(item)

    # Rebuild classification-derived components and their value-chain parents.
    from build.dataset.update_all_models import _cache_model_items_for_run, create_update_from_classification

    with _cache_model_items_for_run():
        create_update_from_classification()

    return {
        "ok": True,
        "classification": item.financials["meta"]["classification"],
        "message": f"Classification updated for {object_type} {object_id}.",
    }


if __name__ == "__main__":
    try:
        result = reassign_classification(json.load(sys.stdin))
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        import traceback

        traceback.print_exc(file=sys.stdout)
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        sys.exit(1)
