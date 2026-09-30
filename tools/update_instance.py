import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from build.analysis.sector_analysis import SectorAnalysis
from build.models.component import Component
from build.models.profile import Profile
from build.models.segment import Segment
from build.models.valuechain import ValueChain


MODELS = {
    "Profile": Profile,
    "Segment": Segment,
    "Component": Component,
    "ValueChain": ValueChain,
}

def update_instance(data):
    object_type = data.get("objectType")
    object_id = data.get("objectId")
    model_class = MODELS.get(object_type)
    if model_class is None or not isinstance(object_id, str) or not object_id:
        raise ValueError("Invalid model type or identifier")

    if model_class._get_json_path_from_prefix(object_id) is None:
        raise ValueError(f"{object_type} not found: {object_id}")

    model = model_class.get_item(object_id)
    return {"ok": True, "json_path": str(model.get_json_path())}


if __name__ == "__main__":
    try:
        result = update_instance(json.load(sys.stdin))
        print(json.dumps(result), file=sys.stderr)
    except Exception as error:
        import traceback

        traceback.print_exc(file=sys.stdout)
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        sys.exit(1)
