"""Build interactive margin-versus-PER plots for profile, segment and sector pages."""

import json
import sys
from pathlib import Path
from urllib.parse import quote

PROFILES_DIR = Path(__file__).resolve().parents[2] / "data" / "build" / "profiles"
DATA_DIR = PROFILES_DIR.parents[1]
COMPONENTS_DIR = DATA_DIR / "build" / "components"
VALUECHAINS_DIR = DATA_DIR / "build" / "valuechains"
PER_BOUND = 40
OPMARGIN_BOUND = 1.0
CATEGORY_COLORS = {
    "A": "#003B73",  # dark blue
    "B": "#1976D2",  # blue
    "C": "#64B5F6",  # light blue
    "D": "#8A8F98",  # gray
}


def build_profile_plot_data() -> dict:
    """Return profile and segment points for the Node navbar plot."""
    if not PROFILES_DIR.is_dir():
        raise FileNotFoundError(f"Profiles directory not found: {PROFILES_DIR}")

    rows = []
    for json_path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        is_profile = bool(data.get("name") and data.get("code"))
        is_segment = bool(data.get("profile_name") and data.get("profile_code") and data.get("id"))
        if not (is_profile or is_segment):
            continue

        page_path = json_path.with_suffix(".html")
        if not page_path.is_file():
            continue

        point = make_mp_point(
            label=(f"{data['profile_name']}({data['id']})" if is_segment else data["name"]),
            code=data["profile_code"] if is_segment else data["code"],
            financials=data.get("financials"),
            page_path=page_path,
        )
        if point:
            rows.append(point)

    return {
        "per_bound": PER_BOUND,
        "category_colors": CATEGORY_COLORS,
        "points": rows,
    }


def make_mp_point(label: str, code: str, financials: dict | None, page_path: Path) -> dict | None:
    """Convert a model's saved financial assessment into a chart point."""
    financials = financials or {}
    assess_data = financials.get("assess_data") or {}
    margin = (assess_data.get("opmargin") or {}).get("ltm(%)")
    if margin is not None:
        margin = margin / 100
    per = (assess_data.get("PER") or {}).get("PER_ltm")
    category = (financials.get("assess_result") or {}).get("category")

    try:
        x, y = float(margin), float(per)
    except (TypeError, ValueError):
        return None
    if category not in CATEGORY_COLORS or y > PER_BOUND or x > OPMARGIN_BOUND:
        return None

    relative_page = page_path.with_suffix(".html").relative_to(DATA_DIR).as_posix()
    return {
        "label": label,
        "category": category,
        "opmargin_ltm": x,
        "PER_ltm": y,
        "code": code,
        "page_url": "/" + quote(relative_page, safe="/"),
    }


def _load_records(directory: Path) -> dict[str, tuple[dict, Path]]:
    records = {}
    for json_path in directory.glob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("key"):
            records[data["key"]] = (data, json_path)
    return records


def _append_model_point(points: list[dict], data: dict, json_path: Path,
                        model_type: str, seen: set[tuple[str, str]]) -> None:
    key = str(data.get("key", ""))
    identity = (model_type, key)
    if not key or identity in seen:
        return
    seen.add(identity)

    if model_type == "Profile":
        label = data.get("name", key)
        code = data.get("code", key)
    elif model_type == "Segment":
        label = f"{data.get('profile_name', key)}({data.get('id', '')})"
        code = data.get("profile_code", key)
    else:
        label = key
        code = key

    point = make_mp_point(label, code, data.get("financials"), json_path.with_suffix(".html"))
    if point:
        point["bold_label"] = model_type in {"Component", "ValueChain"}
        points.append(point)


def build_model_plot_data(model_type: str, model_key: str) -> dict:
    """Collect one component or value chain and the companies it contains."""
    if model_type not in {"Component", "ValueChain"}:
        raise ValueError("MP plots are available for Component and ValueChain pages")

    profiles = _load_records(PROFILES_DIR)
    components = _load_records(COMPONENTS_DIR)
    points = []
    seen = set()

    if model_type == "Component":
        target = components.get(model_key)
        if not target:
            raise ValueError(f"Component not found: {model_key}")
        component_data, component_path = target
        _append_model_point(points, component_data, component_path, "Component", seen)
        component_records = [component_data]
    else:
        valuechains = _load_records(VALUECHAINS_DIR)
        target = valuechains.get(model_key)
        if not target:
            raise ValueError(f"Value chain not found: {model_key}")
        chain_data, chain_path = target
        _append_model_point(points, chain_data, chain_path, "ValueChain", seen)
        component_records = [
            components[key][0]
            for key in chain_data.get("component_keys", [])
            if key in components
        ]

    for component_data in component_records:
        if model_type == "ValueChain":
            component_path = components[component_data["key"]][1]
            _append_model_point(points, component_data, component_path, "Component", seen)
        for listed in component_data.get("listed_companies", []):
            record = profiles.get(listed.get("key"))
            if not record:
                continue
            data, json_path = record
            point_type = "Segment" if data.get("profile_name") else "Profile"
            _append_model_point(points, data, json_path, point_type, seen)

    return {
        "per_bound": PER_BOUND,
        "category_colors": CATEGORY_COLORS,
        "points": points,
        "title": f"Margin vs PER — {model_key}",
    }


def draw_mp_plot(points: list[dict], title: str):
    """Return a Plotly scatter figure. Legend clicks toggle each category."""
    import plotly.graph_objects as go

    traces = []
    points_by_coordinates = {}
    for point in points:
        points_by_coordinates.setdefault(
            (point["opmargin_ltm"], point["PER_ltm"]), []
        ).append(point)

    text_offsets = {}
    for (_, per), same_position in points_by_coordinates.items():
        same_position.sort(key=lambda point: point["label"].casefold())
        duplicate_count = len(same_position)
        for index, point in enumerate(same_position):
            if duplicate_count == 1:
                text_offsets[id(point)] = (0, 14, "center")
                continue
            column = index % 2
            row = index // 2
            xshift = (-1 if column == 0 else 1) * (12 + row * 2)
            xanchor = "right" if column == 0 else "left"
            vertical_direction = -1 if per >= PER_BOUND * 0.85 else 1
            if per <= PER_BOUND * 0.1:
                vertical_direction = 1
            yshift = vertical_direction * (14 + row * 20)
            text_offsets[id(point)] = (xshift, yshift, xanchor)

    annotations = []
    for point in points:
        xshift, yshift, xanchor = text_offsets[id(point)]
        annotations.append({
            "x": point["opmargin_ltm"],
            "y": point["PER_ltm"],
            "xref": "x",
            "yref": "y",
            "text": point["label"],
            "name": f"{point['category']}::{point['page_url']}",
            "showarrow": False,
            "captureevents": True,
            "xshift": xshift,
            "yshift": yshift,
            "xanchor": xanchor,
            "font": {
                "color": CATEGORY_COLORS[point["category"]],
                "weight": 700 if point.get("bold_label") else 400,
            },
        })

    for category, color in CATEGORY_COLORS.items():
        category_points = [point for point in points if point["category"] == category]
        if category_points:
            traces.append(go.Scatter(
                x=[point["opmargin_ltm"] for point in category_points],
                y=[point["PER_ltm"] for point in category_points],
                text=[point["label"] for point in category_points],
                customdata=[[point["page_url"], point["code"]] for point in category_points],
                mode="markers",
                name=category,
                legendgroup=category,
                marker={"color": color, "size": 10, "opacity": 0.85},
                hovertemplate=(
                    "%{text}<br>Code: %{customdata[1]}<br>"
                    "Operating margin: %{x:.1%}<br>PER (LTM): %{y:.2f}"
                    f"<extra>{category}</extra>"
                ),
            ))

    figure = go.Figure(data=traces)
    if not traces:
        figure.add_annotation(
            text="No usable plot data is available for this component or value chain.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 16, "color": "#64748b"},
        )
    figure.update_layout(
        title=title,
        template="plotly_white",
        autosize=True,
        margin={"t": 55, "r": 25, "b": 90, "l": 95},
        xaxis={
            "title": {"text": "X: Operating margin (LTM)", "standoff": 14},
            "tickformat": ".0%",
            "automargin": True,
        },
        yaxis={
            "title": {"text": "Y: PER (LTM)", "standoff": 14},
            "range": [0, PER_BOUND],
            "automargin": True,
        },
        legend={"title": {"text": "Category"}, "itemclick": "toggle",
                "groupclick": "togglegroup", "itemdoubleclick": False},
        annotations=annotations,
        clickmode="event",
    )
    return figure


if __name__ == "__main__":
    if sys.argv[1:] == ["--json"]:
        print(json.dumps(build_profile_plot_data(), ensure_ascii=False))
    elif len(sys.argv) == 4 and sys.argv[1] == "--figure":
        plot_data = build_model_plot_data(sys.argv[2], sys.argv[3])
        print(draw_mp_plot(plot_data["points"], plot_data["title"]).to_json())
    else:
        raise SystemExit("Usage: mp_plot.py --json | --figure Component|ValueChain KEY")
