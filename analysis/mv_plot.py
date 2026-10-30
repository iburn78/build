#%%
import numpy as np
import pandas as pd
import argparse
import plotly.graph_objects as go
from build.models.settings import (
    INDIVIDUAL_PLOT_PERIOD_LONG,
    INDIVIDUAL_PLOT_PERIOD_SHORT,
    MV_CLOSESTS_N_TO_CHOOSE,
    MV_MIN_MARCAP,
)
from plotly.subplots import make_subplots
from data.tools.load import df_krx, get_prices
prices = get_prices()

def _pct_change_distance(s1: pd.Series, s2: pd.Series, period: int):
    """RMS distance between the last ``period`` daily percentage changes."""
    s1 = s1.sort_index()
    s2 = s2.sort_index()
    dates = s1.index[-(period + 1):]
    if len(dates) != period + 1 or not dates.equals(s2.index[-(period + 1):]):
        return np.nan

    r1 = s1.loc[dates].pct_change(fill_method=None).iloc[1:]
    r2 = s2.loc[dates].pct_change(fill_method=None).iloc[1:]

    if r1.isna().any() or r2.isna().any():
        return np.nan

    return np.sqrt(((r1 - r2) ** 2).mean())

def build_RMS_matrix(period: int, min_mc: float = MV_MIN_MARCAP):
    """Build pairwise price-return distances for codes above the market-cap threshold."""
    codelist = df_krx.index[df_krx['Marcap'] >= min_mc]
    values = np.full((len(codelist), len(codelist)), np.nan)
    res = pd.DataFrame(values, index=codelist, columns=codelist)

    for i in range(len(codelist)):
        print(i)
        for j in range(i + 1, len(codelist)):
            res.iloc[i,j] = _pct_change_distance(
                prices[codelist[i]], prices[codelist[j]], period
            )
            res.iloc[j,i] = res.iloc[i,j]
    return res

def get_closests(code, period: int, min_mc: float = MV_MIN_MARCAP, n: int = MV_CLOSESTS_N_TO_CHOOSE):
    """Return the closest price-return matches among market-cap eligible codes."""
    candidates = df_krx.index[df_krx['Marcap'] >= min_mc]
    candidates = candidates[candidates != code]
    if period <= 0 or n <= 0 or len(candidates) == 0:
        return pd.Series(dtype=float, name="RMS")

    window = prices.loc[:, [code, *candidates]].sort_index().tail(period + 1)
    if len(window) != period + 1:
        return pd.Series(dtype=float, name="RMS")

    returns = window.pct_change(fill_method=None).iloc[1:].to_numpy(dtype=float)
    target_returns = returns[:, 0]
    candidate_returns = returns[:, 1:]
    valid = np.isfinite(target_returns).all() & np.isfinite(candidate_returns).all(axis=0)
    if not valid.any():
        return pd.Series(dtype=float, name="RMS")

    differences = candidate_returns[:, valid] - target_returns[:, None]
    distances = np.sqrt(np.mean(differences ** 2, axis=0))
    return pd.Series(distances, index=candidates[valid], name="RMS").nsmallest(n)


def make_mv_figure(code: str, min_mc: float = MV_MIN_MARCAP, n: int = MV_CLOSESTS_N_TO_CHOOSE):
    """Plot normalized price movement for the target and its closest matches."""
    figure = make_subplots(
        rows=2,
        cols=1,
        subplot_titles=(
            f"{INDIVIDUAL_PLOT_PERIOD_LONG} days",
            f"{INDIVIDUAL_PLOT_PERIOD_SHORT} days",
        ),
        vertical_spacing=0.12,
    )

    for row, period in enumerate(
        (INDIVIDUAL_PLOT_PERIOD_LONG,  INDIVIDUAL_PLOT_PERIOD_SHORT), start=1
    ):
        closest_codes = get_closests(code, period, min_mc=min_mc, n=n).index.tolist()
        plot_codes = [code, *closest_codes]
        window = prices.loc[:, plot_codes].sort_index().tail(period)
        for plot_code in plot_codes:
            series = window[plot_code].dropna()
            if series.empty or series.iloc[0] == 0:
                continue
            normalized = series / series.iloc[0] * 100
            name = str(plot_code)
            if plot_code in df_krx.index:
                name = f"{plot_code} {df_krx.at[plot_code, 'Name']}"
            figure.add_trace(
                go.Scatter(
                    x=normalized.index,
                    y=normalized.values,
                    mode="lines",
                    name=name,
                    legend="legend" if row == 1 else "legend2",
                ),
                row=row,
                col=1,
            )

        figure.update_yaxes(
            title_text="Normalized price (first = 100)", row=row, col=1
        )

    figure.update_xaxes(title_text="Date", row=2, col=1)
    figure.update_layout(
        title=f"Price movement peers — {df_krx.loc[code, 'Name']}",
        autosize=True,
        template="plotly_white",
        hovermode="x unified",
        legend={
            "title": {"text": "Long peers"},
            "x": 1.02,
            "y": 0.98,
            "xanchor": "left",
            "yanchor": "top",
        },
        legend2={
            "title": {"text": "Short peers"},
            "x": 1.02,
            "y": 0.43,
            "xanchor": "left",
            "yanchor": "top",
        },
        margin={"l": 70, "r": 190, "t": 90, "b": 45},
    )
    return figure


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure", required=True, help="Profile or mother company code")
    parser.add_argument("--min-mc", type=float, default=MV_MIN_MARCAP)
    parser.add_argument("--n", type=int, default=MV_CLOSESTS_N_TO_CHOOSE)
    args = parser.parse_args()
    print(make_mv_figure(args.figure, min_mc=args.min_mc, n=args.n).to_json())
