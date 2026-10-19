import json
import sys
from pathlib import Path, PurePosixPath
from bs4 import BeautifulSoup
from build.models.settings import (
    BASE_DATA_DIR,
    COMPONENT_NEWS_DIR,
    COMPONENTS_DIR,
    PROFILE_NEWS_DIR,
    PROFILES_DIR,
    VALUECHAIN_DIR,
    VALUECHAIN_NEWS_DIR,
)

HTML_DIRS = {
    "Profile": PROFILES_DIR,
    "Segment": PROFILES_DIR,
    "Component": COMPONENTS_DIR,
    "ValueChain": VALUECHAIN_DIR,
}
NEWS_DIRS = {
    "Profile": PROFILE_NEWS_DIR,
    "Segment": PROFILE_NEWS_DIR,
    "Component": COMPONENT_NEWS_DIR,
    "ValueChain": VALUECHAIN_NEWS_DIR,
}
DATA_DIR = Path(BASE_DATA_DIR)

def _safe_project_path(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if (
        not relative_path
        or relative.is_absolute()
        or ".." in relative.parts
        or any("\\" in part or ":" in part for part in relative.parts)
    ):
        raise ValueError("Invalid Markdown path")
    resolved = (root / Path(*relative.parts)).resolve()
    if resolved != root.resolve() and root.resolve() not in resolved.parents:
        raise ValueError("Markdown path is outside the data directory")
    return resolved


def _html_path(data: dict, object_type: str) -> Path:
    relative_path = data.get("htmlPath")
    if not isinstance(relative_path, str):
        raise ValueError("Missing current HTML path")
    path = _safe_project_path(DATA_DIR, relative_path)
    if path.suffix.lower() != ".html":
        raise ValueError("Invalid current HTML path")
    expected_dir = Path(HTML_DIRS[object_type]).resolve()
    if path.parent != expected_dir:
        raise ValueError("HTML path does not match the model type")
    if not path.is_file():
        raise ValueError(f"HTML page not found: {path.name}")
    return path


def _matches_target(element, object_type: str, object_id: str) -> bool:
    return (
        element is not None
        and element.get("data-object-type") == object_type
        and element.get("data-object-id") == object_id
    )


def delete_markdown(data: dict) -> dict:
    object_type = data.get("objectType")
    object_id = data.get("objectId")
    kind = data.get("kind", "news_article")
    if object_type not in HTML_DIRS or not isinstance(object_id, str) or not object_id:
        raise ValueError("Invalid model type or identifier")
    if kind not in {"news_article", "llm_research"}:
        raise ValueError("Invalid Markdown deletion kind")
    if kind == "llm_research" and object_type != "Profile":
        raise ValueError("LLM research can only be deleted from a Profile")

    html_path = _html_path(data, object_type)
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    if kind == "llm_research":
        markdown_path = html_path.with_suffix(".md")
        dialog = next(
            (
                item for item in soup.select(".llm-research-dialog")
                if _matches_target(item, object_type, object_id)
            ),
            None,
        )
        if dialog is None:
            raise ValueError("LLM Research dialog not found in the current HTML")
        existed = markdown_path.is_file()
        markdown_path.unlink(missing_ok=True)
        markdown = dialog.select_one(".llm-research-markdown")
        if markdown is not None:
            markdown.clear()
            missing = soup.new_tag("p")
            missing["class"] = "llm-research-missing"
            missing.string = "LLM research md file is missing..."
            markdown.append(missing)
        delete_button = dialog.select_one(".llm-research-delete-button")
        if delete_button is not None:
            delete_button.decompose()
        dialog.attrs.pop("data-research-hash", None)
        html_path.write_text(str(soup), encoding="utf-8")
        return {"ok": True, "deleted": existed, "fileName": markdown_path.name}

    filename = data.get("markdownName")
    relative_path = data.get("markdownPath")
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".md"):
        raise ValueError("Invalid Markdown filename")
    if not isinstance(relative_path, str):
        raise ValueError("Missing Markdown file path")
    article_path = _safe_project_path(DATA_DIR, relative_path)
    expected_news_dir = Path(NEWS_DIRS[object_type]).resolve()
    if (
        article_path.name != filename
        or article_path.parent.parent != expected_news_dir
        or article_path.parent.name != html_path.stem
    ):
        raise ValueError("Markdown path does not match this model's news directory")
    if not article_path.is_file():
        raise ValueError(f"Markdown file not found: {article_path.name}")

    rows = [
        row for row in soup.select(".news-row")
        if row.get("data-news-path") == PurePosixPath(relative_path).as_posix()
        and _matches_target(row, object_type, object_id)
    ]
    article_path.unlink()
    for row in rows:
        row.decompose()
    section = soup.select_one(".news-section")
    if section is not None and not section.select_one(".news-row"):
        heading = section.find_previous("h3")
        if heading is not None and heading.get_text(strip=True).lower() == "news":
            heading.decompose()
        section.decompose()
    html_path.write_text(str(soup), encoding="utf-8")
    return {"ok": True, "deleted": filename}


if __name__ == "__main__":
    try:
        result = delete_markdown(json.load(sys.stdin))
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(json.dumps(result, ensure_ascii=True))
    except Exception as error:
        import traceback

        traceback.print_exc(file=sys.stdout)
        with open(3, "w", encoding="utf-8", closefd=False) as response_pipe:
            response_pipe.write(
                json.dumps({"ok": False, "error": str(error)}, ensure_ascii=True)
            )
        sys.exit(1)
