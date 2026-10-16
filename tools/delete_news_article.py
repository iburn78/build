import json
import sys
from pathlib import Path

from build.models.component import Component
from build.models.profile import Profile
from build.models.segment import Segment
from build.models.valuechain import ValueChain
from build.tools.news_html import update_news_html


MODELS = {
    "Profile": Profile,
    "Segment": Segment,
    "Component": Component,
    "ValueChain": ValueChain,
}


def delete_news_article(data):
    object_type = data.get("objectType")
    object_id = data.get("objectId")
    filename = data.get("fileName")
    model_class = MODELS.get(object_type)

    if model_class is None or not isinstance(object_id, str) or not object_id:
        raise ValueError("Invalid model type or identifier")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or not filename.endswith(".md")
    ):
        raise ValueError("Invalid news article filename")

    json_path = model_class._get_json_path_from_prefix(object_id)
    if json_path is None:
        raise ValueError(f"{object_type} not found: {object_id}")

    model = model_class._load_from_path(json_path)
    if model is None:
        raise ValueError(f"Could not load {object_type}: {object_id}")

    news_dir = model.get_news_dir().resolve()
    article_path = (news_dir / filename).resolve()
    if article_path.parent != news_dir or not article_path.is_file():
        raise ValueError("News article not found")

    article_path.unlink()
    update_news_html(model)
    return {"ok": True, "deleted": filename}


if __name__ == "__main__":
    try:
        result = delete_news_article(json.load(sys.stdin))
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        import traceback

        traceback.print_exc(file=sys.stdout)
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        sys.exit(1)
