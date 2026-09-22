import sys
import json
from datetime import datetime
from pathlib import Path

# projects/data
ROOT = Path(__file__).resolve().parents[2]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build.models.profile import Profile, Segment
from build.models.component import Component
from build.models.valuechain import ValueChain
from build.models.json_models import InfoSection
from build.analysis.sector_analysis import SectorAnalysis

MODELS = {
    "Segment": Segment, 
    "Profile": Profile,
    "Component": Component,
    "ValueChain": ValueChain,
}

def update_info(data):
    object_type = data["objectType"]
    object_id = data["objectId"]
    section_name = data["section"]
    values = data["values"]

    model_class = MODELS.get(object_type)

    if model_class is None:
        raise ValueError(f"Unknown object type: {object_type}")

    if object_type == "Profile" or object_type == "Segment":
        obj = model_class.load_from_prefix(object_id)
    else:
        path = Path(model_class.DIR) / f"{object_id}.json"
        ###_ needs fix
        obj = model_class.load_from_path(path)

    if obj is None:
        raise ValueError(
            f"{object_type} not found: {object_id}"
        )

    section = getattr(obj, section_name, None)

    if not isinstance(section, InfoSection):
        raise ValueError(
            f"{section_name} is not an InfoSection"
        )

    # Pydantic validation
    updated_section = type(section).model_validate(values)

    # Server-generated timestamp
    updated_section.updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    setattr(obj, section_name, updated_section)

    obj.save_to_file()
    print(f"SAVING: {obj.get_json_path()} and .html")
    SectorAnalysis().process(obj)

    return {
        "ok": True,
        "updated": updated_section.updated,
        "json_path": str(obj.get_json_path()),
    }


# below is executed by nodejs
if __name__ == "__main__":
    data = json.load(sys.stdin)

    try:
        result = update_info(data)
        print(json.dumps(result), file=sys.stderr)

    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stdout)

        print(json.dumps({
            "ok": False,
            "error": str(e),
        }), file=sys.stderr)

        sys.exit(1)