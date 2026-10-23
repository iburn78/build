#%%

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from build.analysis.sector_analysis import FinancialsData, DEFAULT_KRW_UNIT, KRW_UNIT_KR
from build.tools.tools import get_name


def draw_roma(codes, names = None, scales=[10, 1, 100, 1]):
    if not names or len(names) != len(codes):
        names = [get_name(code) for code in codes]

    REVENUE_SCALE = scales[0]
    OPINCOME_SCALE = scales[1]
    MARCAP_SCALE = scales[2]
    AMOUNT_SCALE = scales[3]

    SCALE_DICT_TO_DEFAULT = {
        k / DEFAULT_KRW_UNIT: v
        for k, v in KRW_UNIT_KR.items()
    }

    REVENUE_SCALE_LABEL = SCALE_DICT_TO_DEFAULT[REVENUE_SCALE]
    OPINCOME_SCALE_LABEL = SCALE_DICT_TO_DEFAULT[OPINCOME_SCALE]
    MARCAP_SCALE_LABEL = SCALE_DICT_TO_DEFAULT[MARCAP_SCALE]
    AMOUNT_SCALE_LABEL = SCALE_DICT_TO_DEFAULT[AMOUNT_SCALE]

    MIN_DOT_SIZE = 5
    MAX_DOT_SIZE = 30

    # Automatically assign distinct colors
    palette = px.colors.qualitative.Dark24
    colors = [palette[i % len(palette)] for i in range(len(codes))]

    # Load data
    res = []

    for code in codes:
        fd = FinancialsData(key=code)

        fr = fd.fr_data.copy()
        fr.index = pd.to_datetime(fr.index)
        fr = fr.sort_index()

        daily = fd.ma_data.copy()
        daily.index = pd.to_datetime(daily.index)
        daily = daily.sort_index()

        result = fr.join(
            daily['marcap'].reindex(fr.index, method='ffill')
        )

        # Sum daily trading amount for each quarterly period
        quarter_dates = fr.index
        daily_amount = daily['amount_daily']
        amounts = []

        for i, date in enumerate(quarter_dates):
            start = (
                quarter_dates[i - 1]
                if i > 0
                else date - pd.DateOffset(months=3)
            )

            amount = daily_amount.loc[
                (daily_amount.index > start)
                & (daily_amount.index <= date)
            ].sum(min_count=1)

            amounts.append(amount)

        result['amount'] = amounts

        result = result.rename(columns={
            'revenue_qtr': 'revenue',
            'opincome_qtr': 'opincome',
        })

        result = result.dropna(
            subset=['revenue', 'opincome', 'marcap']
        )

        # Scale axis data by dividing raw values
        result['revenue'] /= REVENUE_SCALE
        result['opincome'] /= OPINCOME_SCALE
        result['marcap'] /= MARCAP_SCALE
        result['amount'] /= AMOUNT_SCALE

        res.append(result)


    # Align companies to common dates
    dates = sorted(set().union(*(df.index for df in res)))
    dfs = [df.reindex(dates).ffill() for df in res]


    # Axis ranges include negative values and zero
    def get_axis_range(column):
        values = np.concatenate([
            df[column].to_numpy(dtype=float)
            for df in dfs
        ])
        values = values[np.isfinite(values)]

        if len(values) == 0:
            return [-1, 1]

        low = min(values.min(), 0)
        high = max(values.max(), 0)
        padding = (high - low) * 0.08

        if padding == 0:
            padding = max(abs(high), 1) * 0.08

        return [low - padding, high + padding]


    xrange = get_axis_range('revenue')
    yrange = get_axis_range('opincome')
    zrange = get_axis_range('marcap')


    # Dot sizes represent scaled quarterly trading amount
    all_amounts = pd.concat(
        [df['amount'] for df in dfs]
    ).dropna().clip(lower=0)

    amount_max = all_amounts.max() if not all_amounts.empty else 0

    if not np.isfinite(amount_max) or amount_max <= 0:
        amount_max = 1


    def get_dot_sizes(amount):
        ratio = (
            amount.fillna(0).clip(lower=0) / amount_max
        ).clip(0, 1)

        return MIN_DOT_SIZE + np.sqrt(ratio) * (
            MAX_DOT_SIZE - MIN_DOT_SIZE
        )


    # Build company trajectories
    traces = []

    for df, name, color in zip(dfs, names, colors):
        d = df.dropna(
            subset=['revenue', 'opincome', 'marcap']
        )

        if d.empty:
            continue

        sizes = get_dot_sizes(d['amount'])

        customdata = list(zip(
            d.index.strftime('%Y-%m-%d'),
            d['amount'].fillna(0).tolist(),
        ))

        traces.append(go.Scatter3d(
            x=d['revenue'],
            y=d['opincome'],
            z=d['marcap'],
            mode='lines+markers',
            name=name,
            line=dict(color=color, width=4),
            marker=dict(
                color=color,
                size=sizes,
                opacity=0.85,
                sizemode='diameter',
            ),
            customdata=customdata,
            hovertemplate=(
                f'{name}<br>'
                'Date: %{customdata[0]}<br>'
                f'Revenue ({REVENUE_SCALE_LABEL}): %{{x:,.0f}}<br>'
                f'Operating income ({OPINCOME_SCALE_LABEL}): %{{y:,.0f}}<br>'
                f'Market cap ({MARCAP_SCALE_LABEL}): %{{z:,.0f}}<br>'
                f'Quarterly amount ({AMOUNT_SCALE_LABEL}): '
                '%{customdata[1]:,.0f}'
                '<extra></extra>'
            ),
        ))

        # Label the latest point
        traces.append(go.Scatter3d(
            x=[d['revenue'].iloc[-1]],
            y=[d['opincome'].iloc[-1]],
            z=[d['marcap'].iloc[-1]],
            mode='text',
            text=[name],
            textposition='top center',
            textfont=dict(color=color, size=12),
            showlegend=False,
            hoverinfo='skip',
        ))


    # Amount-size legend using representative scaled amounts
    for ratio in [0.1, 0.5, 1.0]:
        amount = amount_max * ratio
        size = MIN_DOT_SIZE + np.sqrt(ratio) * (
            MAX_DOT_SIZE - MIN_DOT_SIZE
        )

        traces.append(go.Scatter3d(
            x=[None],
            y=[None],
            z=[None],
            mode='markers',
            name=f'Amount ({AMOUNT_SCALE_LABEL}): {amount:,.0f}',
            marker=dict(
                size=size,
                color='gray',
                sizemode='diameter',
            ),
            showlegend=True,
            hoverinfo='skip',
        ))


    # Plot
    fig = go.Figure(
        data=traces,
        layout=go.Layout(
            legend=dict(
                title='Company / Quarterly amount',
            ),
            scene=dict(
                xaxis=dict(
                    title=f'Revenue ({REVENUE_SCALE_LABEL})',
                    range=xrange,
                    showbackground=True,
                    backgroundcolor='white',
                    showgrid=True,
                    gridcolor='#e5e5e5',
                    zeroline=True,
                    zerolinecolor='#999999',
                ),
                yaxis=dict(
                    title=f'Operating income ({OPINCOME_SCALE_LABEL})',
                    range=yrange,
                    showbackground=True,
                    backgroundcolor='white',
                    showgrid=True,
                    gridcolor='#e5e5e5',
                    zeroline=True,
                    zerolinecolor='#999999',
                ),
                zaxis=dict(
                    title=f'Market cap ({MARCAP_SCALE_LABEL})',
                    range=zrange,
                    showbackground=True,
                    backgroundcolor='white',
                    showgrid=True,
                    gridcolor='#e5e5e5',
                    zeroline=True,
                    zerolinecolor='#999999',
                ),
                aspectmode='auto',
            ),
            paper_bgcolor='white',
            plot_bgcolor='white',
        ),
    )

    fig.show(renderer='browser')


codes = ['005930', '000660', '009150']
draw_roma(codes)