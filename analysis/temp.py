#%% 
#!/usr/bin/env python3
"""Plot profile financials: four-quarter operating margin vs. LTM PER."""

import json
import os
from pathlib import Path
from urllib.parse import quote

import plotly.express as px

# Profile and segment JSON files are stored together here. This script intentionally
# reads only records with profile-level fields (name and code), skipping segments.
PROFILES_DIR = Path(__file__).resolve().parents[2] / "data" / "build" / "profiles"
PER_BOUND = 40
SERVER_BASE_URL = os.environ.get("PROFILE_SERVER_URL", "http://localhost:3000").rstrip("/")
CATEGORY_COLORS = {
    "A": "#FF0000",  # dark blue
    "B": "#2BFF00AD",  # blue
    "C": "#64C5F6FF",  # light blue
    "D": "#8A8F98",  # gray
}


def main() -> None:
    if not PROFILES_DIR.is_dir():
        raise SystemExit(f"Profiles directory not found: {PROFILES_DIR}")

    rows = []
    skipped = 0
    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Skipping {path.name}: cannot read JSON ({exc})")
            skipped += 1
            continue

        # A profile has name/code; segment records instead have profile_name/profile_code.
        if not data.get("name") or not data.get("code"):
            continue

        financials = data.get("financials") or {}
        assess = financials.get("assess_data") or {}
        margin = (assess.get("opmargin") or {}).get("4qtrs")
        per = (assess.get("PER") or {}).get("PER_ltm")
        category = (financials.get("assess_result") or {}).get("category")
        try:
            x, y = float(margin), float(per)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if category not in CATEGORY_COLORS:
            skipped += 1
            continue
        if y > PER_BOUND:
            skipped += 1
            continue

        rows.append({
            "profile": data["name"],
            "category": category,
            "opmargin_4qtrs": x,
            "PER_ltm": y,
            "code": data["code"],
            "source": path.name,
            "page_url": (
                f"{SERVER_BASE_URL}/build/profiles/"
                f"{quote(path.with_suffix('.html').name)}"
            ) if path.with_suffix(".html").is_file() else "",
        })

    if not rows:
        raise SystemExit(f"No profiles with opmargin.4qtrs, PER.PER_ltm, and category found in {PROFILES_DIR}")

    fig = px.scatter(
        rows,
        x="opmargin_4qtrs",
        y="PER_ltm",
        color="category",
        color_discrete_map=CATEGORY_COLORS,
        text="profile",
        hover_name="profile",
        hover_data={"code": True, "category": True, "source": False,
                    "opmargin_4qtrs": ":.1%", "PER_ltm": ":.2f", "page_url": False},
        custom_data=["page_url"],
        category_orders={"category": ["A", "B", "C", "D"]},
        labels={"opmargin_4qtrs": "Operating margin (4 quarters)",
                "PER_ltm": "PER (LTM)", "category": "Category"},
        title="Profile operating margin vs. LTM PER",
    )
    fig.update_traces(textposition="top center", marker={"size": 10, "opacity": 0.85})
    fig.update_layout(
        template="plotly_white",
        legend_title_text="Category",
        yaxis={"range": [0, PER_BOUND]},
    )
    fig.update_layout(clickmode="event+select")
    output_path = Path(__file__).with_name("profile_scatter.html")
    post_script = """
    const graphDiv = document.getElementById('{plot_id}');
    graphDiv.on('plotly_click', function(eventData) {
        const url = eventData.points[0].customdata && eventData.points[0].customdata[0];
        if (url) window.open(url, '_blank', 'noopener');
    });
    """
    fig.write_html(output_path, post_script=post_script, auto_open=True)
    missing_pages = sum(not row["page_url"] for row in rows)
    print(f"Plotted {len(rows)} profiles; skipped {skipped} records with unavailable/invalid plot data.")
    print(f"Saved clickable chart to {output_path}")
    if missing_pages:
        print(f"{missing_pages} plotted profiles have no matching HTML page; those dots will not open a page.")


if __name__ == "__main__":
    main()
