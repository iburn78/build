from dataclasses import dataclass
from typing import ClassVar, Literal
from threading import RLock
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from data.tools import load
from data.tools.tools import set_KoreanFonts
from build.tools.tools import df_krx, get_id, get_name
from build.tools.analysis_tools import DEFAULT_KRW_UNIT, KRW_UNIT_KR, is_KRX_open, get_slope_intercept, round_sig, calc_increment, calc_alpha_beta, add_dfs

'''
ma: MarCap (until last day if is_KRX_open == True; if strict False then include today if it is after 12:00), Amount
outshares: # shares outstanding
volume: # shares traded 
amount: money amount traded (in a period)
slope: liear regression over all periods since start_date
recent_inc: comparing last 2 priods (e.g., last period movement)
ltm: last twelve months (last 4 qurarters)
aggregation: d, w, m, q (refer to the BLOCK_MAP)
'''

prices = load.get_prices()
volumes = load.get_volumes()
fr_main_db = load.get_fr_main_db()
kospi, kosdaq, kospi200 = load.get_market_index()

DEFAULT_AGGREGATION = 'd'
DEFAULT_START_DATE = '2024-01-01'

from build.models.settings import BASE_PERIOD, MEASURE_PERIOD, INDIVIDUAL_PLOT_PERIOD_LONG, INDIVIDUAL_PLOT_PERIOD_SHORT
# BASE_PERIOD = 120 # days
# MEASURE_PERIOD = 20 # days 
# INDIVIDUAL_PLOT_PERIOD_LONG = 120 # days
# INDIVIDUAL_PLOT_PERIOD_SHORT = 20 # days

# ASSESS parameters
OPINCOME_GROWTH_PERCENT = 5
ALLOWED_FLUCTUATION_PERCENT = 10 
OPMARGIN_THRESHOLD_PERCENT = 15 
PER_LOW = 8
PER_MED = 13.5
VOLATILITY_THRESHOLD_PERCENT = 25
AMOUNT_DAILY_THRESHOLD_PERCENT = 25 
ALPHA_DAILY_THRESHOLD_PERCENT = 0.5  # alpha is stored in percentage points

_FR_QCOLS = sorted(c for c in fr_main_db.columns if 'Q' in c)
_FR_QUARTER_MAP = {
    '1Q': '01-01',
    '2Q': '04-01',
    '3Q': '07-01',
    '4Q': '10-01',
}
_FR_DATECOLS = [
    pd.Timestamp(f'{year}-{_FR_QUARTER_MAP[q]}')
    for year, q in (col.split('_') for col in _FR_QCOLS)
]

def _per_ratio(marcap, opincome):
    """Return PER values, treating negative or undefined ratios as NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        per = np.divide(marcap, opincome)
    if isinstance(per, pd.Series):
        return per.where(np.isfinite(per) & (per >= 0), np.nan)
    return per if np.isfinite(per) and per >= 0 else np.nan

@dataclass
class FinancialsData:
    #  contains raw data for max period for a single key
    key: str
    name: str = ""
    time: pd.Timestamp | None = None # creation time

    # daily marcap and amount data
    ma_data: pd.DataFrame | None = None

    # quarterly revenue and opincome data
    fr_data: pd.DataFrame | None = None

    unit: float = DEFAULT_KRW_UNIT
    adjuster: object | None = None

    # Per-process cache of raw, unadjusted data frames. Segment adjustments are
    # applied only to copies so they cannot contaminate other uses of the same
    # company's underlying financial data.
    _raw_data_cache: ClassVar[dict[tuple[str, float, object], tuple[pd.DataFrame, pd.DataFrame]]] = {}
    _raw_data_lock: ClassVar[RLock] = RLock()

    @classmethod
    def aggregate(cls, key, fd_list):
        """Build component-level time series by summing its member companies."""
        if not fd_list:
            return None
        result = object.__new__(cls)
        result.key = key
        result.name = key
        result.time = pd.Timestamp.now()
        result.ma_data = add_dfs([fd.ma_data for fd in fd_list], fill=True)
        result.fr_data = add_dfs([fd.fr_data for fd in fd_list], fill=True)
        result.unit = fd_list[0].unit
        result.adjuster = None
        result.code, result.id = get_id(key)
        return result

    def __post_init__(self):
        self.code, self.id = get_id(self.key)
        self.name = get_name(self.code) + f"({self.id})" if self.id else get_name(self.code)
        self.time = pd.Timestamp.now()
        # Only adjusted series are mutated by adjust_data(). Unadjusted profile
        # data can safely share the cached frames throughout this analysis run.
        self.ma_data, self.fr_data = self._get_raw_data(copy=self.id is not None)
        self.adjust_data()

    def _get_raw_data(self, copy: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
        now = datetime.now()
        # Market-open handling excludes today's partial data. Include that
        # decision in the key so a long-running process doesn't reuse a frame
        # prepared under a different date/session state.
        cache_key = (self.code, self.unit, (now.date(), is_KRX_open(now=now)))
        with self._raw_data_lock:
            frames = self._raw_data_cache.get(cache_key)
            if frames is None:
                # The cached market frame is date/session-specific. Discard
                # prior-day entries so long-lived processes retain only the
                # current build's snapshot.
                for old_key in list(self._raw_data_cache):
                    if old_key[2][0] != now.date():
                        del self._raw_data_cache[old_key]
                frames = (self._build_ma_data(now), self._build_fr_data())
                self._raw_data_cache[cache_key] = frames
            if copy:
                return frames[0].copy(), frames[1].copy()
            return frames

    def get_ma_data(self):
        return self._get_raw_data()[0]

    def _build_ma_data(self, now=None):
        if self.code not in df_krx.index: 
            raise Exception(f'check code in key {self.key}')

        outshares = df_krx.at[self.code, 'Stocks']
        price = prices[self.code]

        ma_data = pd.DataFrame({
            'marcap': price * outshares / self.unit,
            'amount_daily': volumes[self.code] * price / self.unit,
        }, dtype=np.float64)

        if ma_data.iloc[-1].isna().any():
            raise ValueError(f"ma data for code in key {self.key} is nan for last row - check")

        # ffill - nan could exist only in the beginning
        ma_data = ma_data.ffill()

        # ----------------------------------------------------------------------------
        # if market is open (or at least in early hours), then today record is removed
        # as volume is not a full day data
        # ----------------------------------------------------------------------------
        now = now or datetime.now()
        if is_KRX_open(now=now):
            ma_data = ma_data[ma_data.index.date != now.date()]

        return ma_data

    # fr: financial records in quarterly basis
    def get_fr_data(self):
        return self._get_raw_data()[1]

    def _build_fr_data(self):
        fr_target = fr_main_db.loc[fr_main_db['code'] == self.code]

        cfs = fr_target.loc[fr_target['fs_div'] == 'CFS']
        ofs = fr_target.loc[fr_target['fs_div'] == 'OFS']

        # Use CFS where available, fill missing values with OFS
        row_r = cfs.loc[cfs['account'] == 'revenue', _FR_QCOLS].iloc[0].copy()
        ofs_r = ofs.loc[ofs['account'] == 'revenue', _FR_QCOLS].iloc[0]
        row_r = row_r.fillna(ofs_r)

        row_o = cfs.loc[cfs['account'] == 'operating_income', _FR_QCOLS].iloc[0].copy()
        ofs_o = ofs.loc[ofs['account'] == 'operating_income', _FR_QCOLS].iloc[0]
        row_o = row_o.fillna(ofs_o)

        row_r = row_r / self.unit
        row_o = row_o / self.unit

        row_r.index = _FR_DATECOLS
        row_o.index = _FR_DATECOLS

        fr_data = pd.DataFrame({
            'revenue_qtr': row_r,
            'opincome_qtr': row_o,
        }, dtype=np.float64)

        return fr_data.ffill()

    @classmethod
    def dedupe_fds(cls, fd_list):
        groups = {}

        for fd in fd_list:
            code, id = get_id(fd.key)
            groups.setdefault(code, {})[id] = fd

        result = []
        for fds in groups.values():
            result.extend(
                [fds[None]] if None in fds else fds.values()
            )

        return result

    def adjust_data(self):
        if self.id is None: return 

        if self.adjuster.opmargin is None:
            OPM_ltm = self.fr_data['opincome_qtr'].iloc[-4:].sum()/self.fr_data['revenue_qtr'].iloc[-4:].sum()
            self.adjuster.opmargin = round_sig(OPM_ltm, na_to_zero=True)

        self.fr_data['revenue_qtr'] = self.fr_data['revenue_qtr']*self.adjuster.revenue_share
        self.fr_data['opincome_qtr'] = self.fr_data['revenue_qtr']*self.adjuster.opmargin
        self.ma_data = self.ma_data*self.adjuster.marcap_share


class SectorAnalysis: 
    # a sector analysis
    def __init__(self):
        self.meta = {'name': '', 'code': '', 'segment_name': '', 'id': '', 'updated': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
        self.shape = {}
        self.assess_data = {}
        self.assess_result = {}

        self.financials = {}
        self._subitems_financials_processed = []

        self.is_index = False # fr_data not available
        self.adjuster: object | None = None

    # =======================================================================================================================
    # Creation
    # =======================================================================================================================
    def process(self, fd_list, unit=DEFAULT_KRW_UNIT, fill=True, start_date=DEFAULT_START_DATE, **kwargs):
        self.meta = self.meta | {
            'unit': unit,
            'start_date': start_date, # start date in "yyyy-mm-dd" format
            'base_per': BASE_PERIOD, 
            'measure_per': MEASURE_PERIOD, 
            'indplot_long': INDIVIDUAL_PLOT_PERIOD_LONG,
            'indplot_short': INDIVIDUAL_PLOT_PERIOD_SHORT,
        }

        self.ma_data = add_dfs([cd.ma_data for cd in fd_list], fill) # daily basis
        self.fr_data = add_dfs([cd.fr_data for cd in fd_list], fill) # quarterly basis
        _endkeys = [fd.key for fd in fd_list]
        self.endkey_list_str = "[" + ", ".join(_endkeys[:4] + (["..."] if len(_endkeys) > 4 else [])) + "]"

        self._build_shape() 
        if self._build_assess_data():
            self._perform_assess()

        self.financials = {
            'meta': self.meta,
            'shape': self.shape,
            'assess_data': self.assess_data,
            'assess_result': self.assess_result,
        }

        self.post_process(fd_list, **kwargs)

    def process_index(self, name: str, unit=1e12, start_date=DEFAULT_START_DATE, **kwargs):
        self.meta = self.meta | {
            'name': name,
            'unit': unit if unit else DEFAULT_KRW_UNIT, # KRW unit
            'start_date': start_date, # start date in "yyyy-mm-dd" format
            'indplot_long': INDIVIDUAL_PLOT_PERIOD_LONG,
            'indplot_short': INDIVIDUAL_PLOT_PERIOD_SHORT,
        }

        _index = kospi if name == 'KOSPI' else kosdaq if name == "KOSDAQ" else kospi200 if name == "KOSPI200" else None
        _ma_data = _index.rename(columns={'Close': 'index_data', 'MarCap': 'marcap', 'Amount': 'amount_daily'})
        _ma_data['marcap'] = _ma_data['marcap']/self.meta['unit']
        _ma_data['amount_daily'] = _ma_data['amount_daily']/self.meta['unit']
        self.ma_data = _ma_data
        self.is_index = True

        self.post_process([], **kwargs)

    def post_process(self, fd_list, **kwargs):
        subitems_financials = kwargs.get("subitems_financials")
        self._sub_sector_analyses(subitems_financials=subitems_financials)

        individual_plot_fds = kwargs.get("individual_plot_fds")
        individual_analysis_fds = individual_plot_fds or []
        self._individual_period_stats = (
            self._calculate_individual_period_stats(individual_analysis_fds)
            if len(individual_analysis_fds) >= 3 else []
        )
        if individual_plot_fds is not None:
            self.individual_plots(individual_plot_fds)
        elif len(fd_list) > 1:
            self.individual_plots(fd_list)

        self._add_individual_period_stats(subitems_financials)
        self._create_plot(
            save_path=kwargs.get("plot_path"),
            render=not kwargs.get("defer_plot", False),
        )

    # =======================================================================================================================
    # Individual process
    # =======================================================================================================================
    def individual_plots(self, fd_list):
        """Prepare short and long market-cap series for the plot panels."""
        self._individual_plot_data_short = []
        self._individual_plot_data_long = []
        for fd in fd_list:
            marcap = fd.ma_data["marcap"].dropna()
            name = fd.name or fd.key
            for period, plot_data in (
                (self.meta['indplot_long'], self._individual_plot_data_long),
                (self.meta['indplot_short'], self._individual_plot_data_short),
            ):
                period_marcap = marcap.tail(period)
                if not period_marcap.empty:
                    normalized = period_marcap / period_marcap.iloc[0] * 100
                    plot_data.append((name, normalized))

    def _calculate_individual_period_stats(self, fd_list):
        """Calculate long and short alpha/beta against the sum of all lines."""
        group_total = add_dfs([fd.ma_data["marcap"] for fd in fd_list], fill=True)
        return [
            {
                "indplot_long": calc_alpha_beta(
                    fd.ma_data["marcap"].tail(self.meta['indplot_long']),
                    group_total.tail(self.meta['indplot_long']),
                ),
                "indplot_short": calc_alpha_beta(
                    fd.ma_data["marcap"].tail(self.meta['indplot_short']),
                    group_total.tail(self.meta['indplot_short']),
                ),
            }
            for fd in fd_list
        ]

    def _add_individual_period_stats(self, subitems_financials):
        """Attach group-relative statistics to the matching member records."""
        if not subitems_financials or len(self._individual_period_stats) != len(subitems_financials):
            return
        for stats, financials in zip(self._individual_period_stats, subitems_financials):
            alpha_beta = financials.get("assess_data", {}).get("alpha_beta", {})
            if alpha_beta:
                alpha_beta.update(stats)

    # =======================================================================================================================
    # Assessment  
    # =======================================================================================================================
    '''
    * unit: meta['unit'] 
    * start_date: meta['start_date']
    * Base_Period은 Measure_Period을 포함, Measure_Period은 Base_Period의 마지막 기간

    [shape]
        - financials: in meta['unit']
            - marcap: last day close
        - share: last quarter 기준, %
            - opincome_qtr(%): 비중 계산 시 negative opincome 제외

    [assess_data]
        - opincome(시점, 상황에 따라 마지막 분기 data가 duplicated (ffill) 되었을 수 있음): 
            - positive_ltm: 직전 4개 분기 모두 Positive인가
            - higher(comp): 최근 분기가 전년동기, 직전분기의 100-ALLOWED_FLUCTUATION(%) 보다 높은가  
            - slope: start_date 이후 quarterly opincome에 대한 회귀 기울기 (meta['unit'] per quarter)
            - growth(%): slope / 같은 기간의 평균 quarterly opincome * 100 (percent per quarter)

        - volatility:
            - Daily 절대 MarCap 수익률의 최근 Measure_Period 평균을 직전 baseline과 비교
            - measure_to_base(%): 최근 평균 / 직전 baseline 평균 * 100 (100이면 동일)

        - amount:
            - 일별 거래대금 (unit: meta['unit'])
            - measure_to_base(%): (최근 평균 / 직전 baseline 평균 -1) * 100 (100이면 동일)

        - alpha_beta:
            - alpha(%): 해당 구간의 일별 초과수익률 추정치, percent 단위
            - beta: 해당 구간의 일별 수익률로 추정한 단위 없는 값
            - indplot_long, indplot_short: 각 기간 동안 member 수익률을 그룹 합계와 비교한 alpha/beta

            
    [assess_result]
        - basics: True
            - positive_ltm (and) 
            - higher(comp) (and)
            - slope > 0
        
        - financially_sound: True
            - opincome.growth(%) >= OPINCOME_GROWTH_PERCENT (or)
            - 최근 4개 분기 이익률과 LTM 이익률 모두 >= OPMARGIN_THRESHOLD_PERCENT
        
        - PER: 
            - PER_ltm default
            - PER_ltm: 직전 4개 분기 OP Income의 합 대비, 해당시점의 Marcap
            - PER_qx4: 최근 분기 data로 연간 추정 (x4)
            - PER_fwd: (start_date 부터) opincome의 regression으로 extrapolate한 미래 4개 분기 데이터 추정 (직전분기 데이터는 미포함)
            > Low, Mid, High로 구분 (기준: PER_LOW, PER_MID)

        - volatility_movement/amount_movement: 
            > volatility: measure_to_base(%) > VOLATILITY_THRESHOLD_PERCENT이면 Up
            > volatility: measure_to_base(%) < - VOLATILITY_THRESHOLD_PERCENT이면 Dn
            > amount: measure_to_base(%) > + AMOUNT_DAILY_THRESHOLD_PERCENT이면 Up
            > amount: measure_to_base(%) < - AMOUNT_DAILY_THRESHOLD_PERCENT이면 Dn
        
        - alpha_level:
            - alpha(%)가 +/- ALPHA_DAILY_THRESHOLD_PERCENT를 넘는지로 outperform/underperform 구분
            - indplot_long, indplot_short: 각 기간 동안 individual item의 일별 MarCap 수익률을 MarCap 합계의 수익률에 대비하여 계산
                * profile/segment level dedupe 수행하지 않은 단순 sum

        - category: 
            if basics and finantially_sound: 
                PER_level Low: A
                PER_level Mid: B
                PER_level High: C
            else: D
    '''

    def _build_shape(self):  
        self.shape['financials'] = {}
        self.shape['financials']['marcap'] = round_sig(self.ma_data.iat[-1,0])
        self.shape['financials']['revenue_ltm'] = round_sig(self.fr_data[-4:].sum().iat[0], na_to_zero=True)
        self.shape['financials']['opincome_ltm'] = round_sig(self.fr_data[-4:].sum().iat[1], na_to_zero=True)
        self.shape['financials']['revenue_qtr'] = round_sig(self.fr_data.iat[-1, 0], na_to_zero=True)
        self.shape['financials']['opincome_qtr'] = round_sig(self.fr_data.iat[-1, 1], na_to_zero=True)

    def _build_assess_data(self):  
        if self.is_index: 
            print('Assessment is unavailable for index data.')
            return False

        fr = self.fr_data 

        # side="right" and -1 will give data from the quarter that start_date is in
        start_idx = max(0, fr.index.searchsorted(self.meta['start_date'], side="right") - 1) 

        fr = fr.iloc[start_idx:]

        for col in ['revenue_qtr', 'opincome_qtr']:
            s = fr[col].tail(5)

            if len(s) < 5 or s.isna().any():
                print(f'{col} requires 5 non-missing quarterly data points.')
                # print(fr)
                return False

        opic = fr['opincome_qtr'] 
        rev = fr['revenue_qtr']

        opic_slope, _ = get_slope_intercept(opic)

        res = {}
        # ------------------------------------------------------------------
        # opincome_health 
        # ------------------------------------------------------------------
        # check point 1: is opincome for last 4 quarters positive at all 
        c1 = bool((opic.iloc[-4:] > 0).all())

        # check point 2: is latest opincome higher than prev year, quarter (전년동기, 직전분기)
        c2 = bool(opic.iloc[[-1, -2, -5]].notna().all() and opic.iloc[-1] >= max(opic.iloc[-2], opic.iloc[-5])*(100-ALLOWED_FLUCTUATION_PERCENT)/100)

        opic_growth = opic_slope / opic.mean() * 100 if opic.mean() > 0 else np.nan

        res['opincome'] = {
            'positive_ltm': c1, 
            'higher(comp)': c2, 
            'slope': round_sig(opic_slope, n=2), 
            'growth(%)': round_sig(opic_growth, n=2), 
        }

        # ------------------------------------------------------------------
        # opmargin 
        # ------------------------------------------------------------------
        # last 4 quarter opmargin: date is quarter starting date
        # The same forward-fill applies here.
        opms = {
            quarter: round_sig(value, n=2)
            for quarter, value in (opic / rev * 100).iloc[-4:].items()
        }
        res['opmargin(%)'] = {
            f'{k:%y}_{k.quarter}Q': v
            for k, v in opms.items()
        }
        r = self.fr_data[-4:].sum().iat[0]
        o = self.fr_data[-4:].sum().iat[1]
        res['opmargin(%)']['ltm'] = round_sig(o/r*100, n=2)

        # ------------------------------------------------------------------
        # PER
        # ------------------------------------------------------------------
        PER_ltm = _per_ratio(
            self.ma_data['marcap'].iloc[-1],
            self.fr_data['opincome_qtr'].iloc[-4:].sum(),
        )
        PER_qx4 = _per_ratio(
            self.ma_data['marcap'].iloc[-1],
            self.fr_data['opincome_qtr'].iloc[-1] * 4,
        )

        fwd_annual_opincome = sum([opic_slope*i + opic.iloc[-1] for i in [1, 2, 3, 4]]) # this excludes the current quarter by choice
        PER_fwd = _per_ratio(self.ma_data['marcap'].iloc[-1], fwd_annual_opincome)

        res['PER'] = {
            'PER_ltm': round_sig(PER_ltm), 
            'PER_qx4': round_sig(PER_qx4),
            'PER_fwd': round_sig(PER_fwd),
        }

        # ------------------------------------------------------------------
        # volatility and amount increment
        # ------------------------------------------------------------------
        # Volatility: absolute daily market-cap return
        absolute_daily_returns = self.ma_data['marcap'].pct_change().abs()
        res['volatility'] = calc_increment(absolute_daily_returns, self.meta['measure_per'], self.meta['base_per'])

        # Amount:
        res['amount'] = calc_increment(self.ma_data['amount_daily'], self.meta['measure_per'], self.meta['base_per'])

        # ------------------------------------------------------------------
        # alpha and beta
        # ------------------------------------------------------------------
        _from_start_date = calc_alpha_beta(self.ma_data['marcap'], kospi['Close'])
        _base_period = calc_alpha_beta(self.ma_data['marcap'][-self.meta['base_per']:], kospi['Close'])
        _measure_period = calc_alpha_beta(self.ma_data['marcap'][-self.meta['measure_per']:], kospi['Close'])
        alpha_beta = {
            'from_start_date': _from_start_date,
            'base_period': _base_period,
            'measure_period': _measure_period,
        }
        if not self.meta.get('code'):
            alpha_beta['indplot_long'] = {'alpha(%)': None, 'beta': None}
            alpha_beta['indplot_short'] = {'alpha(%)': None, 'beta': None}
        res['alpha_beta'] = alpha_beta
        self.assess_data = res

        return True

    def _perform_assess(self):
        oh = self.assess_data['opincome']
        basics = False
        if oh['positive_ltm'] and oh['higher(comp)'] and oh['slope'] > 0:
            basics = True

        financially_sound = False
        if oh['growth(%)'] >= OPINCOME_GROWTH_PERCENT: 
            financially_sound = True

        om = list(self.assess_data['opmargin(%)'].values())[-5:]
        if len(om) == 5 and all(np.isfinite(x) and x >= OPMARGIN_THRESHOLD_PERCENT for x in om):
            financially_sound = True

        # PER_level
        per = self.assess_data['PER']
        if per['PER_ltm'] < PER_LOW: PER_level = 'Low'
        elif per['PER_ltm'] < PER_MED: PER_level = 'Mid'
        elif per['PER_ltm'] >= PER_MED: PER_level = 'High'
        else: PER_level = '(na)'

        # volatility movement in measure period
        vol = self.assess_data['volatility']
        if vol['measure_to_base(%)'] < -VOLATILITY_THRESHOLD_PERCENT: volatility = 'Dn'
        elif vol['measure_to_base(%)'] <= VOLATILITY_THRESHOLD_PERCENT: volatility = '-'
        elif vol['measure_to_base(%)'] > VOLATILITY_THRESHOLD_PERCENT: volatility = 'Up'
        else: volatility = '(na)'

        # amount movement in measure period
        amt = self.assess_data['amount']
        if amt['measure_to_base(%)'] < -AMOUNT_DAILY_THRESHOLD_PERCENT: amount = 'Dn'
        elif amt['measure_to_base(%)'] <= AMOUNT_DAILY_THRESHOLD_PERCENT: amount = '-'
        elif amt['measure_to_base(%)'] > AMOUNT_DAILY_THRESHOLD_PERCENT: amount = 'Up'
        else: amount = '(na)'

        # alpha_level
        alp = self.assess_data['alpha_beta']['measure_period']
        if alp['alpha(%)'] < -ALPHA_DAILY_THRESHOLD_PERCENT: alpha_level = 'udr_pfm' # strong negative
        elif alp['alpha(%)'] <=  ALPHA_DAILY_THRESHOLD_PERCENT: alpha_level = '-'
        elif alp['alpha(%)'] >  ALPHA_DAILY_THRESHOLD_PERCENT: alpha_level = 'out_pfm' # strong positive
        else: alpha_level = '(na)' 

        # Choose Representative Categories
        market_sentiment = '-'
        if amount == 'Up' and volatility == 'Dn': market_sentiment = 'confidence' # confidence created
        elif amount == 'Up' and volatility == 'Up': market_sentiment = 'unstable' 
        elif amount == 'Dn' and volatility == 'Dn': market_sentiment = 'consumed' # events consumed
        elif amount == 'Dn' and volatility == 'Up': market_sentiment = 'speculators' # speculators remained

        # --------------------------------------------
        # categorization
        # --------------------------------------------
        if basics and financially_sound:
            if PER_level == 'Low':
                category = 'A'
            elif PER_level == 'Mid': 
                category = 'B'
            else: 
                category = 'C'
        else: 
            category = 'D'

        self.assess_result = {
            'basics': basics,
            'financially_sound': financially_sound,
            'PER_level': PER_level,
            'volatility_level': volatility,
            'amount_level': amount,
            'alpha_level': alpha_level,
            'category': category,
            'market_sentiment': market_sentiment,
        }
    
    # =======================================================================================================================
    # Sub SA analyses
    # =======================================================================================================================
    def _sub_sector_analyses(self, subitems_financials: list):
        if not subitems_financials:
            return

        # Parent sector
        self.shape['share'] = {
            'marcap(%)': '-',
            '-m_rank':'-',
            'revenue_qtr(%)': '-',
            '-r_rank': '-',
            'opincome_qtr(%)': '-',
            '-o_rank': '-',
        }

        # Collect raw financial values
        marcaps = [
            sf['shape']['financials']['marcap'] * sf['meta']['unit']
            for sf in subitems_financials
        ]

        revenues = [
            sf['shape']['financials']['revenue_qtr'] * sf['meta']['unit']
            for sf in subitems_financials
        ]

        opincomes = [
            sf['shape']['financials']['opincome_qtr'] * sf['meta']['unit']
            for sf in subitems_financials
        ]

        # Ranking: include negative values
        sorted_marcaps = sorted(marcaps, reverse=True)
        sorted_revenues = sorted(revenues, reverse=True)
        sorted_opincomes = sorted(opincomes, reverse=True)

        m_ranks = [
            sorted_marcaps.index(value) + 1
            for value in marcaps
        ]

        r_ranks = [
            sorted_revenues.index(value) + 1
            for value in revenues
        ]

        o_ranks = [
            sorted_opincomes.index(value) + 1
            for value in opincomes
        ]

        # Percentage calculation
        total_marcap = sum(marcaps)
        total_revenue = sum(revenues)

        # Only positive operating income contributes to shares
        positive_opincomes = [
            max(value, 0)
            for value in opincomes
        ]

        total_opincome = sum(positive_opincomes)

        # Populate each sub-sector
        for i, sf in enumerate(subitems_financials):

            marcap = marcaps[i]
            revenue = revenues[i]
            opincome = opincomes[i]

            sf['shape']['share'] = {
                'marcap(%)': (
                    round_sig(marcap / total_marcap * 100, n=2)
                    if total_marcap > 0 else '-'
                ), 
                '-m_rank': m_ranks[i],

                'revenue_qtr(%)': (
                    round_sig(revenue / total_revenue * 100, n=2)
                    if total_revenue > 0 else '-'
                ),

                '-r_rank': r_ranks[i],

                'opincome_qtr(%)': (
                    round_sig(opincome / total_opincome * 100, n=2)
                    if opincome > 0 and total_opincome > 0
                    else '-'
                ),

                '-o_rank': o_ranks[i],
            }
        self._subitems_financials_processed = subitems_financials

    # =======================================================================================================================
    # Aggregation and plotting
    # =======================================================================================================================
    # cut data from start_date and define aggregation length
    def _create_plot(
        self,
        save_path: Path | None = None,
        aggregation: Literal['d', 'w', 'm', 'q'] = DEFAULT_AGGREGATION,
        render: bool = True,
    ):
        # business days in each aggregation
        BLOCK_MAP = {
            'd': 1,
            'w': 5,
            'm': 20,
            'q': 60,
        }
        if aggregation not in BLOCK_MAP:
            raise ValueError(f'invalid aggregation: {self.meta['aggregation']}')

        # data is 'aggregated' from 'start_date'
        self.meta['aggregation'] = aggregation 
        block_size = BLOCK_MAP[aggregation]

        self._aggr_dataset = self._ma_aggregate_periods(block_size)
        self._aggr_ma_plotdata = self._prep_aggr_ma_plotdata()
        if not self.is_index:
            self._aggr_dataset = self._combine_fr_data()

        if render:
            self._plot(save_path=save_path)

    def save_plot(self, save_path: Path) -> None:
        """Render a plot after financial content has been compared."""
        self._plot(save_path=save_path)

    # aggregate into backward-aligned discrete blocks
    def _ma_aggregate_periods(self, block_size):
        """
        incomplete oldest block is discarded
        index: the last days of periods
        amount: sum of daily amounts, i.e., subtotal
        """
        # use from start_date
        usable = (len(self.ma_data.loc[self.meta['start_date']:]) // block_size) * block_size 

        if usable == 0:
            raise ValueError('not enough rows')

        ma_aggr_data = self.ma_data.iloc[-usable:]

        rows = []
        for start in range(0, usable, block_size):

            block = ma_aggr_data.iloc[start:start + block_size]
            marcap = block['marcap'].iloc[-1]
            amount_subtotal = block['amount_daily'].sum(min_count=1) # all all nan, then nan.

            rows.append({
                'last_day': block.index[-1],
                'marcap': marcap,
                'amount_subtotal': amount_subtotal,
            })

        return pd.DataFrame(rows).set_index('last_day')

    def _combine_fr_data(self):
        # Preprocess financial data before combining it.
        _fr_data = self.fr_data.copy() 
        _fr_data['revenue_ltm'] = _fr_data['revenue_qtr'].rolling(4).sum()
        _fr_data['opincome_ltm'] = _fr_data['opincome_qtr'].rolling(4).sum()
        _fr_data['opincome_qx4'] = _fr_data['opincome_qtr']*4
        _fr_data['opmargin_ltm'] = _fr_data['opincome_ltm']/_fr_data['revenue_ltm']
        _fr_data['opmargin_qtr'] = _fr_data['opincome_qtr']/_fr_data['revenue_qtr'] # quarterly opmargin

        # align index and combine (so fr_data only after start_date is used)
        self._aggr_dataset[_fr_data.columns]=_fr_data.reindex(self._aggr_dataset.index, method='ffill')

        # PER: assumes the same 4 quarters 
        self._aggr_dataset['PER_qx4'] = _per_ratio(
            self._aggr_dataset['marcap'], self._aggr_dataset['opincome_qx4']
        )
        self._aggr_dataset['PER_ltm'] = _per_ratio(
            self._aggr_dataset['marcap'], self._aggr_dataset['opincome_ltm']
        )

        # ffill and return
        return self._aggr_dataset.replace([np.inf, -np.inf], np.nan).ffill().astype('float64')

    def _prep_aggr_ma_plotdata(self):
        ma_plotdata = pd.DataFrame(
            index=['recent_inc', 'slope', 'intercept'],
            columns=['marcap', 'amount_subtotal', 'unit'],
        )

        for col in ['marcap', 'amount_subtotal']:
            ma_plotdata.loc['recent_inc', col] = self._aggr_dataset[col].iloc[-1] / self._aggr_dataset[col].iloc[-2] - 1

            slope, intercpet = get_slope_intercept(self._aggr_dataset[col])
            ma_plotdata.loc['slope', col] = slope
            ma_plotdata.loc['intercept', col] = intercpet

        ma_plotdata.loc['recent_inc', 'unit'] = '%'
        ma_plotdata.loc['slope', 'unit'] = KRW_UNIT_KR[self.meta['unit']]
        ma_plotdata.loc['intercept', 'unit'] = KRW_UNIT_KR[self.meta['unit']]

        return ma_plotdata

    def _plot(self, figsize = None, save_path = None):
        set_KoreanFonts()
        if self.is_index:
            if figsize is None: figsize = (12, 3)
            fig, ax = plt.subplots(
                figsize=(figsize[0], figsize[1]),
                sharex=True,
            )
            self._plot_ma_panel(ax)

        else:
            if figsize is None: figsize = (12, 7)
            individual_panels = [
                ("long", getattr(self, "_individual_plot_data_long", [])),
                ("short", getattr(self, "_individual_plot_data_short", [])),
            ]
            individual_panels = [
                (period_key, plot_data)
                for period_key, plot_data in individual_panels
                if plot_data
            ]
            panel_count = 2 + len(individual_panels)
            panel_heights = (4, 3, *([3] * len(individual_panels)))
            fig, axes = plt.subplots(
                panel_count,
                1,
                figsize=(figsize[0], figsize[1] + 3 * len(individual_panels)),
                sharex=False,
                gridspec_kw={"height_ratios": panel_heights},
            )

            ax1, ax2 = axes[:2]
            ax2.sharex(ax1)

            self._plot_ma_panel(ax1)

            self._plot_financials_panel(ax2, use_ltm=True)

            for ax, (period_key, plot_data) in zip(axes[2:], individual_panels):
                self._plot_individual_panel(
                    ax,
                    plot_data,
                    self.meta[f'indplot_{period_key}'],
                    hide_first_tick_label=True,
                )

        plt.tight_layout()
        if save_path: 
            fig.savefig(save_path)
        else: 
            plt.show()
        plt.close(fig)   

    # =======================================================================================================================
    # (1) TOP PANEL: MARCAP + AMOUNT
    # =======================================================================================================================
    def _plot_ma_panel(self, ax):

        x = self._aggr_dataset.index
        ax_r = ax.twinx()

        # -----------------------------------------------------
        # marcap
        # -----------------------------------------------------
        ax.plot(
            x,
            self._aggr_dataset['marcap'],
            color='black',
            linewidth=2,
            label='marcap',
        )

        _mc_col = self._aggr_dataset['marcap'].dropna()

        mc_fitted = (
            self._aggr_ma_plotdata.at['slope', 'marcap']
            * np.arange(len(_mc_col))
            + self._aggr_ma_plotdata.at['intercept', 'marcap']
        )

        ax.plot(
            _mc_col.index,
            mc_fitted,
            color='gray',
            linestyle='--',
            linewidth=2,
            label='marcap trend',
        )

        # -----------------------------------------------------
        # amount
        # -----------------------------------------------------
        bar_width = max(
            3,
            np.median(np.diff(mdates.date2num(x))),
        )

        ax_r.bar(
            x,
            self._aggr_dataset['amount_subtotal'],
            width=bar_width,
            color='orange',
            alpha=0.5,
            label='amount_subtotal',
        )

        _amt_col = self._aggr_dataset['amount_subtotal'].dropna()

        amt_fitted = ( 
            self._aggr_ma_plotdata.at['slope', 'amount_subtotal']
            * np.arange(len(_amt_col))
            + self._aggr_ma_plotdata.at['intercept', 'amount_subtotal']
        ) 

        ax_r.plot(
            _amt_col.index,
            amt_fitted,
            color='tab:orange',
            linestyle='--',
            linewidth=2,
            label='amount_subtotal trend',
        )

        # Mark the starts of the assessment windows on daily data. Group equal
        # dates so a single line can carry every applicable period marker.
        daily_dates = self.ma_data.index
        markers_by_date = {}
        for marker, period_key, default_period in (
            ('b', 'base_per', BASE_PERIOD),
            ('l', 'indplot_long', INDIVIDUAL_PLOT_PERIOD_LONG),
            ('m', 'measure_per', MEASURE_PERIOD),
            ('s', 'indplot_short', INDIVIDUAL_PLOT_PERIOD_SHORT),
        ):
            if len(daily_dates) == 0:
                continue
            period = int(self.meta.get(period_key, default_period))
            start_index = max(0, len(daily_dates) - period)
            start_date = pd.Timestamp(daily_dates[start_index])
            markers_by_date.setdefault(start_date, []).append(marker)

        for start_date, markers in markers_by_date.items():
            ax.axvline(
                start_date,
                color='green',
                linestyle=':',
                linewidth=1.2,
                alpha=1,
            )
            ax.annotate(
                f"({'/'.join(markers)})",
                xy=(mdates.date2num(start_date), 1),
                xycoords=ax.get_xaxis_transform(),
                xytext=(0, -2),
                textcoords='offset points',
                ha='center',
                va='top',
                fontsize=9,
                color='green',
                clip_on=True,
            )

        # -----------------------------------------------------
        # baseline
        # -----------------------------------------------------
        ax.set_ylim(bottom=0)
        ax_r.set_ylim(bottom=0)

        # -----------------------------------------------------
        # annotations
        # -----------------------------------------------------
        ax.annotate(
            f"rm:{self._aggr_ma_plotdata.loc['recent_inc', 'marcap']:.0%}",
            xy=(x[-1], self._aggr_dataset['marcap'].iloc[-1]),
            xytext=(-3, 5),
            textcoords='offset points',
            fontsize=12,
        )

        ax_r.annotate(
            f"ra:{self._aggr_ma_plotdata.loc['recent_inc', 'amount_subtotal']:.0%}",
            xy=(x[-1], self._aggr_dataset['amount_subtotal'].iloc[-1]),
            xytext=(-3, -5),
            textcoords='offset points',
            fontsize=12,
        )

        mid_ = len(_mc_col) // 2

        ax.annotate(
            f"sm:{self._aggr_ma_plotdata.at['slope', 'marcap']:,.0f}",
            xy=(_mc_col.index[mid_], mc_fitted[mid_]),
            xytext=(0, 10),
            textcoords='offset points',
            fontsize=12,
        )

        mid2_ = len(_amt_col) // 2

        ax_r.annotate(
            f"sa:{self._aggr_ma_plotdata.at['slope', 'amount_subtotal']:,.0f}",
            xy=(_amt_col.index[mid2_], amt_fitted[mid2_]),
            xytext=(0, 10),
            textcoords='offset points',
            fontsize=12,
        )

        # -----------------------------------------------------
        # labels
        # -----------------------------------------------------
        ax.set_ylabel(
            f"MarCap ({KRW_UNIT_KR[self.meta['unit']]} KRW)"
        )

        ax_r.set_ylabel(
            f"Amount ({KRW_UNIT_KR[self.meta['unit']]} KRW)"
        )

        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

        ax_r.yaxis.set_major_formatter(
            FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

        ax.grid(True, linestyle='--', alpha=0.3)

        ax.set_title(
            f"{self.meta['name']} {self.endkey_list_str} | "
            f"{self.meta['updated']} | "
            f"aggr: {self.meta['aggregation']}"
        )

        # -----------------------------------------------------
        # legend
        # -----------------------------------------------------
        lines1, labels1 = ax.get_legend_handles_labels()
        lines1r, labels1r = ax_r.get_legend_handles_labels()

        ax.legend(
            lines1 + lines1r,
            labels1 + labels1r,
            loc='upper left',
        )

    # =======================================================================================================================
    # (2) FINANCIALS PANEL
    # =======================================================================================================================
    def _plot_financials_panel(self, ax, use_ltm: bool):

        x = self._aggr_dataset.index
        ax_r = ax.twinx()

        # -----------------------------------------------------
        # column selection
        # -----------------------------------------------------
        if use_ltm:
            opincome_col = 'opincome_ltm'
            opmargin_col = 'opmargin_ltm'
            per_col = 'PER_ltm'
            basis_text = "Annualized by LTM"
        else:
            opincome_col = 'opincome_qx4'
            opmargin_col = 'opmargin_qtr'
            per_col = 'PER_qx4'
            basis_text = "Annualized by qx4"

        opincome = self._aggr_dataset[opincome_col]
        opmargin_percent = self._aggr_dataset[opmargin_col]*100
        per = self._aggr_dataset[per_col]

        # -----------------------------------------------------
        # opincome bars
        # -----------------------------------------------------
        bar_width = np.median(
            np.diff(mdates.date2num(x))
        )

        ax.bar(
            x,
            opincome,
            width=bar_width,
            color='tab:blue',
            alpha=0.6,
            label='opincome',
        )

        # -----------------------------------------------------
        # opmargin
        # -----------------------------------------------------
        margin_observations = opmargin_percent.dropna()
        margin_top = 25
        if not margin_observations.empty:
            # Keep zero at 1/4 height. Expanding the top scale also lowers the
            # bottom limit to -margin_top / 3, so positive and negative values fit.
            required_top = max(
                margin_top,
                margin_observations.max(),
                -3 * margin_observations.min(),
            )
            if required_top > margin_top:
                margin_top = int(np.ceil(required_top * 1.1 / 10) * 10)
        # Draw margin against the plot height: 0% is 1/4 up from the bottom,
        # and the default top of the panel represents margin_top
        opmargin_plot_y = 0.25 + 0.75 * opmargin_percent / margin_top

        ax.plot(
            x,
            opmargin_plot_y,
            transform=ax.get_xaxis_transform(),
            linestyle=':',
            color='red',
            linewidth=3,
            label='opmargin(%)',
        )

        # -----------------------------------------------------
        # PER
        # -----------------------------------------------------
        ax_r.plot(
            x,
            per,
            color='purple',
            linewidth=2,
            label='PER',
        )

        # -----------------------------------------------------
        # baseline
        # -----------------------------------------------------
        income_values = opincome.dropna()
        if not income_values.empty:
            y_min = min(0, income_values.min())
            y_max = max(0, income_values.max())
            padding = max((y_max - y_min) * 0.05, abs(y_min) * 0.01, abs(y_max) * 0.01, 1)
            ax.set_ylim(y_min - padding, y_max + padding)

        if per.notna().any():
            ax_r.set_ylim(bottom=min(0, per.min()))

        # -----------------------------------------------------
        # annotations
        # -----------------------------------------------------
        ax.annotate(
            f"{opincome.iloc[-1]:,.0f}",
            xy=(x[-1], opincome.iloc[-1]),
            xytext=(1, 2),
            textcoords='offset points',
            fontsize=12,
        )

        if not margin_observations.empty:
            last_date = margin_observations.index[-1]
            last_value = margin_observations.iloc[-1]
            last_plot_y = 0.25 + 0.75 * last_value / margin_top

            extrema = [
                ("min", margin_observations.idxmin(), margin_observations.min(), 12),
                ("max", margin_observations.idxmax(), margin_observations.max(), -12),
            ]
            annotated_dates = {last_date}
            x_numbers = mdates.date2num(x)
            x_midpoint = (x_numbers.min() + x_numbers.max()) / 2
            for label, date, value, offset_y in extrema:
                if date in annotated_dates or np.isclose(value, last_value):
                    continue
                annotated_dates.add(date)
                x_number = mdates.date2num(date)
                text_offset_x = -4 if x_number > x_midpoint else 4
                horizontal_alignment = 'right' if text_offset_x < 0 else 'left'
                ax.annotate(
                    f"{label}: {value:.2g}",
                    xy=(x_number, 0.25 + 0.75 * value / margin_top),
                    xycoords=ax.get_xaxis_transform(),
                    xytext=(text_offset_x, offset_y),
                    textcoords='offset points',
                    ha=horizontal_alignment,
                    fontsize=9,
                    color='red',
                )

            ax.annotate(
                f"{last_value:.2g}",
                xy=(mdates.date2num(last_date), last_plot_y),
                xycoords=ax.get_xaxis_transform(),
                xytext=(1, 2),
                textcoords='offset points',
                fontsize=12,
            )

        ax_r.annotate(
            f"{per.iloc[-1]:.0f}",
            xy=(x[-1], per.iloc[-1]),
            xytext=(1, 2),
            textcoords='offset points',
            fontsize=12,
        )

        # -----------------------------------------------------
        # labels
        # -----------------------------------------------------
        ax.set_ylabel(
            f"Op Income ({KRW_UNIT_KR[self.meta['unit']]} KRW)"
        )

        ax_r.set_ylabel("PER")

        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

        ax_r.yaxis.set_major_formatter(
            FuncFormatter(lambda x, _: f"{x:,.0f}")
        )

        ax.grid(True, linestyle='--', alpha=0.3)

        ax.set_title(
            f"[{basis_text}] opincome | "
            f"opmargin(%) | "
            f"PER (marcap / opincome)"
        )

        # -----------------------------------------------------
        # legend
        # -----------------------------------------------------
        lines, labels = ax.get_legend_handles_labels()
        lines_r, labels_r = ax_r.get_legend_handles_labels()

        ax.legend(
            lines + lines_r,
            labels + labels_r,
            loc='upper left',
        )

        # -----------------------------------------------------
        # x axis
        # -----------------------------------------------------
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter('%Y-%m-%d')
        )

    # =======================================================================================================================
    # (3) INDIVIDUAL PANEL
    # =======================================================================================================================
    def _plot_individual_panel(
        self, ax, plot_data, period, hide_first_tick_label=False
    ):
        """Draw recent individual market caps indexed to 100 at each series start."""
        annotations = []
        for name, series in plot_data:
            (line,) = ax.plot(
                series.index,
                series.values,
                marker="o",
                markersize=3,
                linewidth=1.2,
            )
            annotation = ax.annotate(
                str(name),
                xy=(series.index[-1], series.iloc[-1]),
                xytext=(4, 0),
                textcoords="offset points",
                color=line.get_color(),
                va="center",
                fontsize=8,
            )
            annotations.append((annotation, series.index[-1], series.iloc[-1]))
        first_date = min(series.index[0] for _, series in plot_data)
        ax.set_title(
            f"[Normalized as of {first_date:%Y-%m-%d}] "
            f"MarCap trend ({period} days)"
        )
        ax.set_ylabel("MarCap (first = 100)")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:,.0f}"))
        ax.grid(True, linestyle="--", alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        if hide_first_tick_label:
            ax.figure.canvas.draw()
            tick_labels = ax.get_xticklabels()
            if tick_labels:
                tick_labels[0].set_visible(False)
        self._separate_individual_end_labels(ax, annotations)

    @staticmethod
    def _separate_individual_end_labels(ax, annotations):
        """Space end labels vertically in display coordinates where possible."""
        if len(annotations) < 2:
            return

        figure = ax.figure
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        dpi = figure.dpi
        axes_bottom, axes_top = ax.bbox.y0, ax.bbox.y1
        labels = []
        for annotation, x_value, y_value in annotations:
            point_y = ax.transData.transform((mdates.date2num(x_value), y_value))[1]
            bbox = annotation.get_window_extent(renderer=renderer)
            labels.append({
                "annotation": annotation,
                "point_y": point_y,
                "height": bbox.height + 2,
                "target_y": bbox.y0 + bbox.height / 2,
                "placed_y": bbox.y0 + bbox.height / 2,
            })
        labels.sort(key=lambda item: item["target_y"])

        # Push labels apart from bottom to top. If the panel is too crowded,
        # clamp to its bounds and allow the remaining overlap.
        for index in range(1, len(labels)):
            previous = labels[index - 1]
            current = labels[index]
            minimum_y = previous["placed_y"] + (previous["height"] + current["height"]) / 2
            current["placed_y"] = max(current["target_y"], minimum_y)
        overflow = labels[-1]["placed_y"] + labels[-1]["height"] / 2 - axes_top
        if overflow > 0:
            for label in labels:
                label["placed_y"] -= overflow
        underflow = axes_bottom - (labels[0]["placed_y"] - labels[0]["height"] / 2)
        if underflow > 0:
            for label in labels:
                label["placed_y"] += underflow

        for label in labels:
            offset_points = (label["placed_y"] - label["point_y"]) * 72 / dpi
            label["annotation"].set_position((4, offset_points))
