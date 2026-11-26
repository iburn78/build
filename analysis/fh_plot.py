"""Build foreign holding plots for profiles and component members."""
import argparse
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
from plotly.subplots import make_subplots

from build.analysis.foreign_hold import fetch_code_fh
from build.analysis.mv_plot import prices
from build.models.settings import BASE_PERIOD, MEASURE_PERIOD

PROFILES_DIR = Path(__file__).resolve().parents[2] / "data" / "build" / "profiles"
COMPONENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "build" / "components"


def _get_profile_code(key: str) -> tuple[str, str]:
    for path in PROFILES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("key", "")) == key or str(data.get("code", "")) == key:
            return str(data.get("code") or data.get("profile_code")), str(data.get("name") or data.get("profile_name") or key)
    if key.isdigit() and len(key) == 6:
        return key, key
    raise ValueError(f"Profile not found: {key}")


def _fetch_fh_data(code: str, period: int = BASE_PERIOD) -> pd.DataFrame:
    start = prices.index[-period]
    end = prices.index[-1]
    return fetch_code_fh(code, start=start, end=end)


def _members(component_key: str) -> list[tuple[str, str]]:
    component_data = None
    for component_path in COMPONENTS_DIR.glob("*.json"):
        try:
            candidate = json.loads(component_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if candidate.get("key") == component_key:
            component_data = candidate
            break
    if component_data is None:
        raise ValueError(f"Component not found: {component_key}")
    members = []
    for listed in component_data.get("listed_companies", []):
        try:
            code, label = _get_profile_code(str(listed.get("key", "")))
        except ValueError:
            continue
        members.append((code, label))
    return members


def make_fh_figure(code: str | None = None, component_key: str | None = None):
    """Plot foreign holding, plus close price and volume for individual profiles."""
    if (code is None) == (component_key is None):
        raise ValueError("Provide exactly one of code or component_key.")
    members = [_get_profile_code(code)] if code is not None else _members(component_key)
    title = f"Foreign holdings - {members[0][1]}" if code else f"Foreign holding — {component_key}"
    periods = (BASE_PERIOD, MEASURE_PERIOD)
    data_by_code = {
        member_code: _fetch_fh_data(member_code, BASE_PERIOD)
        for member_code, _label in members
    }
    individual_profile = code is not None
    if individual_profile:
        subplot_titles = [f"{BASE_PERIOD} days", "Close price and volume"]
        specs = [[{}], [{"secondary_y": True}]]
        row_heights = [0.55, 0.45]
        periods_to_plot = ((1, BASE_PERIOD),)
    else:
        subplot_titles = [f"{periods[0]} days", f"{periods[1]} days"]
        specs = [[{}], [{}]]
        row_heights = [0.58, 0.42]
        periods_to_plot = tuple(enumerate(periods, start=1))
    figure = make_subplots(
        rows=len(subplot_titles),
        cols=1,
        subplot_titles=tuple(subplot_titles),
        specs=specs,
        shared_xaxes=individual_profile,
        row_heights=row_heights,
        vertical_spacing=0.08,
    )

    component_colors = qualitative.Plotly
    member_colors = {
        member_code: component_colors[index % len(component_colors)]
        for index, (member_code, _label) in enumerate(members)
    }
    for row, period in periods_to_plot:
        for member_code, label in members:
            data = data_by_code[member_code]
            if data.empty or "ForeignHold" not in data:
                continue
            series = pd.to_numeric(data["ForeignHold"], errors="coerce").dropna().sort_index().tail(period)
            if series.empty:
                continue
            plotted_values = series.values
            if not individual_profile:
                start_value = series.iloc[0]
                if pd.isna(start_value) or start_value == 0:
                    continue
                plotted_values = series / start_value * 100
            color = member_colors[member_code] if not individual_profile else None
            figure.add_trace(
                go.Scatter(
                    x=series.index,
                    y=plotted_values,
                    mode="lines+markers",
                    name=label,
                    showlegend=True,
                    legend="legend",
                    line={"color": color} if color else None,
                    marker={"size": 3, "color": color} if color else {"size": 3},
                ),
                row=row,
                col=1,
            )
        figure.update_yaxes(
            title_text="Foreign holding (%)" if individual_profile else "Normalized foreign holding (first = 100)",
            ticksuffix="%" if individual_profile else "",
            row=row,
            col=1,
        )

    correlation_labels = []
    if individual_profile:
        data = data_by_code[code].sort_index().tail(BASE_PERIOD)
        measure_date = data.index[-MEASURE_PERIOD] if len(data) >= MEASURE_PERIOD else None
        close = pd.to_numeric(data.get("Close", pd.Series(dtype=float)), errors="coerce").dropna()
        volume = pd.to_numeric(data.get("Volume", pd.Series(dtype=float)), errors="coerce").dropna()
        foreign_hold = pd.to_numeric(data.get("ForeignHold", pd.Series(dtype=float)), errors="coerce").dropna()
        for duration_name, period in (("Base", BASE_PERIOD), ("Measure", MEASURE_PERIOD)):
            paired = pd.concat(
                [foreign_hold.tail(period).rename("ForeignHold"), close.tail(period).rename("Close")],
                axis=1,
            ).dropna()
            correlation = paired["ForeignHold"].corr(paired["Close"]) if len(paired) >= 2 else float("nan")
            correlation_value = f"{correlation:.2f}" if pd.notna(correlation) else "N/A"
            correlation_labels.append(f"{duration_name} ({period} days): <b>{correlation_value}</b>")
        if not close.empty:
            figure.add_trace(
                go.Scatter(x=close.index, y=close.values, mode="lines", name="Close price",
                           line={"color": "#1f77b4"}),
                row=2, col=1, secondary_y=False,
            )
        if not volume.empty:
            figure.add_trace(
                go.Bar(x=volume.index, y=volume.values, name="Volume",
                       marker={"color": "rgba(128,128,128,0.35)"}),
                row=2, col=1, secondary_y=True,
            )
        figure.update_yaxes(title_text="Close price (KRW)", row=2, col=1, secondary_y=False)
        figure.update_yaxes(title_text="Volume (shares)", row=2, col=1, secondary_y=True)
        if measure_date is not None:
            figure.add_vline(
                x=measure_date,
                line_color="red",
                line_dash="dot",
                line_width=1,
                annotation_text="(m)",
                annotation_position="top",
                row=1,
                col=1,
            )
            figure.add_vline(
                x=measure_date,
                line_color="red",
                line_dash="dot",
                line_width=1,
                row=2,
                col=1,
            )
    figure.update_xaxes(title_text="Date", row=len(subplot_titles), col=1)
    if correlation_labels:
        title = (
            f"{title}<br><br><span style='font-size:0.75em'>"
            f"CORR (FH vs close) - {' / '.join(correlation_labels)}</span>"
        )
    figure.update_layout(title=title, autosize=True, template="plotly_white", hovermode="x unified",
                         showlegend=not individual_profile,
                         legend={"title": {"text": "Series" if individual_profile else "Companies"},
                                 "x": 1.02, "y": 0.98, "xanchor": "left", "yanchor": "top"},
                         margin={"l": 70, "r": 30 if individual_profile else 260,
                                 "t": 145 if individual_profile else 90, "b": 45})
    return figure


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--code", help="Profile company code")
    group.add_argument("--component", help="Component key")
    args = parser.parse_args()
    print(make_fh_figure(code=args.code, component_key=args.component).to_json())
