#%%
import requests
import pandas as pd
from pathlib import Path

df_p = Path(__file__).parent.parent / 'financials/collect/data/df_krx.feather'
df_krx = pd.read_feather(df_p)

# max page_size is 100
def fetch(page_size=100):
    BASE_URL = "https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize={pageSize}"
    rows = []

    with requests.Session() as session:
        for market in ['KOSPI', 'KOSDAQ']:
            url = BASE_URL.format(
                market=market, page=1, pageSize=page_size
            )
            response = session.get(url)
            response.raise_for_status()

            data = response.json()
            total_stocks = data.get('totalCount', 0)
            total_pages = (total_stocks + page_size - 1) // page_size

            for page in range(1, total_pages + 1):
                if page > 1:
                    url = BASE_URL.format(
                        market=market, page=page, pageSize=page_size
                    )
                    response = session.get(url)
                    response.raise_for_status()
                    data = response.json()

                for item in data.get('stocks', []):
                    if item.get('stockEndType') != 'stock':
                        continue

                    close = pd.to_numeric(item.get('closePriceRaw'), errors='coerce')
                    marcap = pd.to_numeric(item.get('marketValueRaw'), errors='coerce')

                    rows.append({
                        'Code': item['itemCode'],
                        'Name': item['stockName'],
                        'Market': market,
                        'Close': close,
                        'Volume': item.get('accumulatedTradingVolumeRaw'),
                        'Amount': item.get('accumulatedTradingValueRaw'),
                        'Marcap': marcap,
                        'Stocks': marcap / close if pd.notna(close) and close else 0,
                    })

    columns = ['Name', 'Market', 'Close', 'Volume', 'Amount', 'Marcap', 'Stocks']
    df = pd.DataFrame(rows).set_index('Code')
    df[columns[2:]] = (
        df[columns[2:]]
        .apply(pd.to_numeric, errors='coerce')
        .fillna(0)
        .astype('int64')
    )

    return df[columns]

new = fetch()
#%%
print(df_krx.loc[~df_krx.index.isin(new.index)])
print('---')
print(new.loc[~new.index.isin(df_krx.index)])



# read existing
# if no existing, then fine.
# if existing but not in new, then check with 
import nfinance