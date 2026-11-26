import pandas as pd
import requests

# Close is 최종가
# this returns with foreign holdings
def fetch_code_fh(symbol, start=None, end=None):
    """Return daily OHLCV and ForeignHold data for a Naver ticker."""
    start = pd.Timestamp(start) if start is not None else pd.Timestamp("1980-01-01")
    end = pd.Timestamp(end) if end is not None else pd.Timestamp.today().normalize()
    url = (
        f"https://api.stock.naver.com/chart/domestic/item/{symbol}/day"
        f"?startDateTime={start:%Y%m%d}0000&endDateTime={end:%Y%m%d}2359"
    )
    response = requests.get(url)
    response.raise_for_status()

    df = pd.DataFrame(response.json())
    if df.empty:
        return df

    df["Date"] = pd.to_datetime(df["localDate"])
    df = df.set_index("Date").sort_index()
    df = df.rename(columns={
        "closePrice": "Close",
        "openPrice": "Open",
        "highPrice": "High",
        "lowPrice": "Low",
        "accumulatedTradingVolume": "Volume",
        "foreignRetentionRate": "ForeignHold",
    })
    if "ForeignHold" not in df.columns:
        df["ForeignHold"] = pd.NA
    columns = ["Open", "High", "Low", "Close", "Volume", "ForeignHold"]
    df = df.loc[start:end, [column for column in columns if column in df.columns]]
    df["Change"] = df["Close"].pct_change()
    return df

