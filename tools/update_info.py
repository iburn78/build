import sys
import json
from datetime import datetime
from pathlib import Path

from build.models.profile import Profile, Business
from build.models.segment import Segment, FinancialsAdjuster
from build.models.component import Component, Traits
from build.models.valuechain import ValueChain,Landscape
from build.models.json_model import InfoSection
from build.analysis.sector_analysis import SectorAnalysis

MODELS = {
    "Segment": Segment, 
    "Profile": Profile,
    "Component": Component,
    "ValueChain": ValueChain,
}

INFO_SECTIONS = {
    "Segment": FinancialsAdjuster, 
    "Profile": Business,
    "Component": Traits,
    "ValueChain": Landscape,
}

def update_info(data):
    object_type = data["objectType"]
    object_id = data["objectId"]
    values = data["values"]

    model_class = MODELS.get(object_type)
    info_section_class = INFO_SECTIONS.get(object_type)

    if model_class is None or info_section_class is None:
        raise ValueError(f"Unknown object type: {object_type}")

    if model_class._get_json_path_from_prefix(object_id) is None:
        raise ValueError(f"{object_type} not found: {object_id}")

    updated_section = info_section_class.model_validate(values)
    updated_section.updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    item = model_class.get_item(object_id, info_section = updated_section)
    return {
        "ok": True,
        "updated": updated_section.updated,
        "json_path": str(item.get_json_path()),
    }


# below is executed by nodejs
if __name__ == "__main__":
    data = json.load(sys.stdin)

    try:
        result = update_info(data)
        # fd 3 is a dedicated channel for the JSON response; stdout/stderr remain logs.
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps(result))

    except Exception as e:
        import traceback

        traceback.print_exc(file=sys.stdout)

        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps({
                "ok": False,
                "error": str(e),
            }))

        sys.exit(1)
