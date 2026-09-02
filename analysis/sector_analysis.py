#%%
from dataclasses import dataclass
from typing import Literal
import numpy as np
import pandas as pd
from functools import reduce
from datetime import datetime
import json
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
from data import load
from data.tools import set_KoreanFonts
from build.tools.settings import df_krx, sanitized_filename
from build.tools.analysis_tools import KRW_UNIT_KR, is_KRX_open, get_slope_intercept, round_sig, calc_increment, calc_alpha_beta, dprint, dict_to_html
from build.models.profile import Profile, ProfileManager
from build.models.component import Component, ComponentManager
from build.models.valuechain import ValueChain, ValueChainManager

'''
ma: MarCap (until last day if is_KRX_open == True; if strict False then include today if it is after 12:00), Amount
outshares: # shares outstanding
volume: # shares traded 
amount: money amount traded (a period)
slope: liear regression over all periods since start_date
recent_inc: comparing last 2 priods (e.g., last period movement)
ltm: last twelve months (last 4 qurarters)
aggregation: d, w, m, q (refer to the BLOCK_MAP)
'''
prices = load.get_prices()
volumes = load.get_volumes()
fr_main_db = load.get_fr_main_db()
kospi, kosdaq, kospi200 = load.get_market_index()

DEFAULT_KRW_UNIT: float = 1e9 # 10 억원
MEASURE_DURATION = 20 # days 
BASE_DURATION = 120 # days
DEFAULT_START_DATE = '2024-01-01'

# ASSESS parameters
OPINCOME_GROWTH_RATE = 0.05 # per quarter 
OPMARGIN_THRESHOLD = 0.25 
PER_LOW = 7
PER_MED = 12
VOLATILITY_THRESHOLD = 0.33 # 0.33 for 33% volality up/down
AMOUNT_DAILY_THRESHOLD = 0.33 # 0.33 for 33% amount up/down
ALPHA_DAILY_THRESHOLD = 0.0004 # to convert yearly: x 250 (busines days), 0.0004 if 10% +/- compared to index


@dataclass
class CodeData:
    # single code data that contains raw data for max period
    code: str
    time: pd.Timestamp | None = None # creation time

    # daily marcap and amount data
    ma_data: pd.DataFrame | None = None

    # quarterly revenue and opincome data
    fr_data: pd.DataFrame | None = None

    unit: float = DEFAULT_KRW_UNIT

    def __post_init__(self):
        self.time = pd.Timestamp.now()
        self.ma_data = self.get_ma_data()
        self.fr_data = self.get_fr_data()

    # ma: MarCap, Amount in daily basis
    def get_ma_data(self):
        if self.code not in df_krx.index: 
            raise Exception(f'check code {self.code}')

        outshares = df_krx.at[self.code, 'Stocks']
        ma_data = pd.DataFrame({
            'marcap': prices[self.code] * outshares / self.unit,
            'amount_daily': volumes[self.code] * prices[self.code] / self.unit,
        })

        ###_ checker (temporary)
        if ma_data.iloc[-1].isna().any():
            print(f'{self.code}: price, volume, outshare ----------------------------')
            print(prices[self.code].iloc[-3:])
            print(volumes[self.code].iloc[-3:])
            print(outshares)
            print(ma_data.iloc[-3:])
            raise ValueError(f"ma data for code {self.code} is nan for last row - check")

        # ffill - nan could exist only in the beginning
        ma_data = ma_data.ffill()

        # ----------------------------------------------------------------------------
        # if market is open (or at least in early hours), then today record is removed
        # as volume is not a full day data
        # ----------------------------------------------------------------------------
        now = datetime.now()
        if is_KRX_open(now=now):
            ma_data = ma_data[ma_data.index.date != now.date()]

        return ma_data
    
    # fr: financial records in quarterly basis
    def get_fr_data(self):
        QCOLS = sorted(c for c in fr_main_db.columns if 'Q' in c)
        _quarter_map = {
            '1Q': '01-01',
            '2Q': '04-01',
            '3Q': '07-01',
            '4Q': '10-01',
        }
        DATECOLS = [
            pd.Timestamp(f'{year}-{_quarter_map[q]}')
            for year, q in (col.split('_') for col in QCOLS)
        ]

        # get CFS(consolidated) if not empty
        fr_target = fr_main_db.loc[fr_main_db['code']==self.code]
        fr_db_for_code = fr_target.loc[fr_target['fs_div'] == "CFS"]
        cfs_qcols = fr_db_for_code.loc[(fr_db_for_code['account'] == 'revenue') | (fr_db_for_code['account'] == 'operating_income'), QCOLS]
        if cfs_qcols.isna().all().all():
            fr_db_for_code = fr_target.loc[fr_target['fs_div'] == "OFS"] 

        row_r = fr_db_for_code.loc[fr_db_for_code['account'] == 'revenue', QCOLS].iloc[0].copy() # series
        row_r = (row_r/self.unit)
        row_r.index = DATECOLS

        row_o = fr_db_for_code.loc[fr_db_for_code['account'] == 'operating_income', QCOLS].iloc[0].copy() # series
        row_o = (row_o/self.unit)
        row_o.index = DATECOLS
        fr_data = pd.DataFrame({
            'revenue_qtr': row_r,
            'opincome_qtr': row_o,
        })

        # return with ffill 
        return fr_data.ffill()

class SectorAnalysis: 
    # a sector analysis
    def __init__(self):
        self.meta = {'name': '','updated': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")}
        self.codelist = [] 
        self.shape = {}
        self.assess_data = {}
        self.assess_result = {}

        # this class basically assumes a group of code (a sector, codelist, or component), but can handle company and index too
        self.jsonmodel = None
        self.model_class = None
        self.sub_sas = None
        self.is_index = False # fr_data not available

        self.pm = ProfileManager()
        self.cm = ComponentManager()
        self.vm = ValueChainManager()

    # =======================================================================================================================
    # Creation
    # =======================================================================================================================
    @classmethod
    def get_from_code(cls, code, **kwargs):
        sa = cls()
        pr = sa.pm.get_item(code)
        return sa.process_profile(pr, **kwargs)

    @classmethod
    def get_from_component_name(cls, name, **kwargs):
        sa = cls()
        cp = sa.cm.get_item(name)
        return sa.process_component(cp, **kwargs)
    
    @classmethod
    def get_from_valuechain_name(cls, name, **kwargs):
        sa = cls()
        vm = sa.vm.get_item(name)
        return sa.process_valuechain(vm, **kwargs)
    
    # -------------------------------------------------------------------------------------------------------
    # public interfaces
    # -------------------------------------------------------------------------------------------------------
    def process_profile(self, pr: Profile, unit=None, fill=False, start_date=DEFAULT_START_DATE):
        self.jsonmodel = pr
        self.model_class = Profile
        self.meta['name'] = df_krx.at[pr.code, 'Name']
        self.codelist = [pr.code]
        self.meta['code'] = pr.code 
        self._process_codelist(unit=unit, fill=fill, start_date=start_date)
        return self

    def process_component(self, cp: Component, unit=None, fill=False, start_date=DEFAULT_START_DATE): 
        self.jsonmodel = cp
        self.model_class = Component
        self.meta['name'] = cp.name
        self.codelist = cp.get_codelist()
        self.meta['code'] = self.codelist
        self._process_codelist(unit=unit, fill=fill, start_date=start_date)
        return self

    def process_valuechain(self, vc: ValueChain, unit=None, fill=False, start_date=DEFAULT_START_DATE): 
        self.jsonmodel = vc
        self.model_class = ValueChain
        self.meta['name'] = vc.name
        self.codelist = vc.get_codelist()
        self.meta['code'] = self.codelist
        self._process_codelist(unit=unit, fill=fill, start_date=start_date)
        return self

    def process_index(self, name: str, unit=1e12, start_date=DEFAULT_START_DATE):
        self.meta = self.meta | {
            'name': name,
            'unit': unit if unit else DEFAULT_KRW_UNIT, # KRW unit
            'start_date': start_date, # start date in "yyyy-mm-dd" format
        }

        _index = kospi if name == 'KOSPI' else kosdaq if name == "KOSDAQ" else kospi200 if name == "KOSPI200" else None
        _ma_data = _index.rename(columns={'Close': 'index_data', 'MarCap': 'marcap', 'Amount': 'amount_daily'})
        _ma_data['marcap'] = _ma_data['marcap']/self.meta['unit']
        _ma_data['amount_daily'] = _ma_data['amount_daily']/self.meta['unit']
        self.ma_data = _ma_data
        self.is_index = True
        return self

    # -------------------------------------------------------------------------------------------------------
    # private 
    # -------------------------------------------------------------------------------------------------------
    # codelist: target sector -> returns an SA for the group of the codelist
    def _process_codelist(self, unit=None, fill=False, start_date=DEFAULT_START_DATE):
        if len(self.codelist) != len(set(self.codelist)): raise ValueError(f'codelist should not contain any duplications: {self.codelist}')

        self.meta = self.meta | {
            'unit': unit if unit else DEFAULT_KRW_UNIT, # KRW unit
            'start_date': start_date, # start date in "yyyy-mm-dd" format
        }

        cd_list = [CodeData(code=code, unit=self.meta['unit']) for code in self.codelist]

        # ma_data, fr_data stay as raw
        self.ma_data = self._add_dfs([cd.ma_data for cd in cd_list], fill) # daily basis
        self.fr_data = self._add_dfs([cd.fr_data for cd in cd_list], fill) # quarterly basis

        self._post_process()
        return self

    # function that sums multiple serieses
    def _add_dfs(self, df_list, fill=False):
        return reduce(lambda a, b: a.add(b, fill_value=0 if fill else None), df_list)

    def _post_process(self):
        self._build_shape() 
        self._build_assess_data()
        self._perform_assess()
        self._create_json()
        self._create_plot()
        self._build_sub_sector_analyses()
        self._create_html() 

    # create or append to/replace existing json
    def _create_json(self):
        if self.model_class is Profile:
            key = self.codelist[0]
            json_filename = f'{key}_{sanitized_filename(self.meta['name'])}.json'
        else:
            key = sanitized_filename(self.meta['name'])
            json_filename = f'{key}.json'

        files = list(Path(self.jsonmodel.DIR).glob(f'{key}*.json'))

        if len(files) > 1:
            raise ValueError(f"Expected 1 file for {key}, found {len(files)}")

        if files:
            json_file = files[0]
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            json_file = Path(self.jsonmodel.DIR) / json_filename
            print(f"json file with {self.model_class.__name__} {key} does not exist: {json_filename} to be created")
            data = {}

        data['financials'] = {
            'meta': self.meta,
            'shape': self.shape,
            'assess_data': self.assess_data,
            'assess_result': self.assess_result,
        }

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    # recursively refreshing profiles and components
    def _build_sub_sector_analyses(self):
        if self.model_class is Component:
            self.sub_sas = []
            for code in self.jsonmodel.get_codelist():
                self.sub_sas.append(SectorAnalysis().get_from_code(code))
        elif self.model_class is ValueChain:
            self.sub_sas = []
            for component_name in self.jsonmodel.component_names:
                self.sub_sas.append(SectorAnalysis().get_from_component_name(component_name))
        self._sub_sector_analyses()

    def _create_html(self):
        sa_list = [self] + self.sub_sas if self.sub_sas is not None else [self]
        name_list = [{'name': sa.meta['name'], 'link': sa.jsonmodel.get_json_path().with_suffix('.html')} for sa in sa_list]
        dict_list = [sa.get_combined_dict() for sa in sa_list]
        qs = self.jsonmodel.get_qualitative_dict()
        output_file = self.jsonmodel.get_json_path().with_suffix('.html')

        dict_to_html(self.model_class.__name__, name_list, dict_list, qs, output_file)

    # =======================================================================================================================
    # Assessment  
    # =======================================================================================================================
    '''
    [shape]
        - share: last quarter 기준, %
        - opincome: negative opincome 제외

    [basics]
        - OP Income (시점, 상황에 따라 마지막 분기 data가 duplicated (ffill) 되었을 수 있음):
            * 최근 4개 분기 모두 Positive 인가?
            * 최근 분기가 전년동기, 직전분기보다 좋아졌는가?
            * (START_DATE 부터) 성장중인가? (positive slope)

        > 모두 충족하면 True

    [financially sound]
        - OP Income: (START_DATE 부터) 성장률이 충분히 높은가? (slope > THRESHOLD)
        - OP Margin: 최근 4개 분기 이익률이 각각 충분히 높은가? (each of opmargin > THRESHOLD, 영업이익률은 트렌드를 보지 않음)

        > 둘중의 하나 충족하면 True

    [PER]
        - PER_ltm: 직전 4개 분기 OP Income의 합 대비, 해당시점의 Marcap
        - PER_qx4: 최근 분기 data로 연간 추정 (x4)
        - PER_fwd: (START_DATE 부터) OP Income의 Regression으로 Extrapolate한 미래 4개 분기 데이터 추정 (직전분기 데이터는 미포함)
        
        > (PER_ltm default로 사용) Low, Mid, High로 구분: PER_LOW, PER_MID로 구분 (2026-08, KOSPI PER = ~17)

    [Volatility]
        - Marcap의 변화율(daily pct change)에 대해, Measure_Duration(직전, business days)기간동안 Standard_Dev로 정의함 (Rolling 일별, 양수)
        - Volatility를 Base_Duration 동안 Regression 하였을 때, Measure_Duration 중간지점(비교위치) 값(Prediction)과 실제 Measure_Duration의 평균값(Real_mean)비교

        > ratio = Real_mean/Prediction > 1 + THRESHOLD: 최근 Volatility가 증대 (Up)
        > ratio > 1 - THRESHOLD: 최근 감소 (Dn)

        * Base_Duration은 Measure_Duration을 포함, Measure_Duration은 Base_Duration의 마지막 기간 (recent business days)
        * Regression 결과가 비교위치에서 near zero or negative 되는 것을 방지하기 위한 floor value 설정 (실제 구현 참조)
        * THRESHOLD in float

    [Amount]
        - 일별 거래대금 대상 Volatility와 동일하게 산정

        > ratio > 1 + THRESHOLD: Up
        > ratio > 1 - THRESHOLD: Dn

    [Alpha]
        - Measure_Duration (or Base_Duration, from START_DATE) 동안, Index (KOSPI default) 대비 Alpha, Beta 분석

        > alpha > THRESHOLD: outperform 
        > alpha < -THRESHOLD: underperform 

        * THRESHOLD: 일별 수익률, in float (기간 수익률은 convert 필요하며, x days로 estimate)
    
    [Result]
        - Categorization: 
            if basics and finantially_sound: 
                PER_level Low: A
                PER_level Mid: B
                PER_level High: C
            else: D
            * Logic: 재무 사항이 갖추어진 회사중에, PER가 아직 낮은 회사가 보다 높은 등급
            * in D, PER has to be interpreted individually, high per doesn't mean high valuation (negative or high value PER)
    '''
    def print(self):
        if not self.is_index:
            print('Meta Data:')
            dprint(self.meta)
            print('Shape:')
            dprint(self.shape)
            print('Assess Data:')
            dprint(self.assess_data)
            print('Assess Result:')
            dprint(self.assess_result)
        else: 
            self._create_plot()

    def _build_shape(self):  
        self.shape['financials'] = {}
        self.shape['financials']['revenue_4qtrs'] = round_sig(self.fr_data[-4:].sum().iat[0])
        self.shape['financials']['opincome_4qtrs'] = round_sig(self.fr_data[-4:].sum().iat[1])
        self.shape['financials']['revenue_qtr'] = round_sig(self.fr_data.iat[-1, 0])
        self.shape['financials']['opincome_qtr'] = round_sig(self.fr_data.iat[-1, 1])

    def _build_assess_data(self):  
        if self.is_index: 
            print('no assess available for index data')
            return False

        fr = self.fr_data # drop_duplicates() not applied here

        # side="right" and -1 will give data from the quarter that start_date is in
        start_idx = max(0, fr.index.searchsorted(self.meta['start_date'], side="right") - 1) 

        fr = fr.iloc[start_idx:]

        if len(fr) < 5: 
            print('need fr data at least 5 qtrly data points')
            return False

        opic = fr['opincome_qtr'] 
        rev = fr['revenue_qtr']
        opic_slope , _ = get_slope_intercept(opic)

        res = {}
        # ------------------------------------------------------------------
        # opincome_health 
        # ------------------------------------------------------------------
        # check point 1: is opincome for last 4 quarters positive at all 
        c1 = bool((opic.iloc[-4:] > 0).all())

        # check point 2: is latest opincome higher than prev year, quarter (전년동기, 직전분기)
        # note: current quarter may be the same as the prev quarter due to ffill (on assumption that the performance stays)
        #       this is necessary, since some companies' financials may not be updated yet within a sector
        c2 = bool(opic.iloc[-1] >= max(opic.iloc[-2], opic.iloc[-5]))

        # opincome slope over the average of last 4 quarters
        opic_growth = opic_slope / opic.iloc[-4:].mean() 

        res['opincome'] = {
            'positive_last_4qtrs': c1, 
            'higher_than_comp': c2, # higher than comparable quarters 
            'slope': round_sig(opic_slope), # measured from start_date given 
            'growth_per_qtr': round_sig(opic_growth),
        }

        # ------------------------------------------------------------------
        # opmargin 
        # ------------------------------------------------------------------
        # last 4 quarter opmargin: date is quarter starting date
        # refer to note: the same situation applies here
        opms = (opic/rev).iloc[-4:].apply(round_sig).to_dict()
        res['opmargin'] = {f'{k:%y}_{k.quarter}Q': v for k, v in opms.items()}
        r = self.fr_data[-4:].sum().iat[0]
        o = self.fr_data[-4:].sum().iat[1]
        res['opmargin']['4qtrs'] = round_sig(o/r)

        # ------------------------------------------------------------------
        # PER
        # ------------------------------------------------------------------
        PER_ltm = self.ma_data['marcap'].iloc[-1]/self.fr_data['opincome_qtr'].iloc[-4:].sum()
        PER_qx4 = self.ma_data['marcap'].iloc[-1]/(self.fr_data['opincome_qtr'].iloc[-1]*4)

        fwd_annual_opincome = sum([opic_slope*i + opic.iloc[-1] for i in [1, 2, 3, 4]]) # this excludes the current quarter by choice
        PER_fwd = self.ma_data['marcap'].iloc[-1]/fwd_annual_opincome

        res['PER'] = {
            'PER_ltm': round_sig(PER_ltm), 
            'PER_qx4': round_sig(PER_qx4),
            'PER_fwd': round_sig(PER_fwd),
        }

        # ------------------------------------------------------------------
        # volatility and amount increment
        # ------------------------------------------------------------------
        # Volatility:
        # volality is measured as std(percent change of marcap for last MEASURE_DURATION days)
        res['volatility'] = calc_increment(self.ma_data['marcap'].pct_change().rolling(MEASURE_DURATION).std().dropna(), MEASURE_DURATION, BASE_DURATION)
        # Amount:
        res['amount'] = calc_increment(self.ma_data['amount_daily'], MEASURE_DURATION, BASE_DURATION)

        # ------------------------------------------------------------------
        # alpha and beta
        # ------------------------------------------------------------------
        _from_start_date = calc_alpha_beta(self.ma_data['marcap'], kospi['Close'])
        _base_duration = calc_alpha_beta(self.ma_data['marcap'][-BASE_DURATION:], kospi['Close'])
        _measure_duration = calc_alpha_beta(self.ma_data['marcap'][-MEASURE_DURATION:], kospi['Close'])
        res['alpha_beta'] = {
            'from_start_date': _from_start_date,
            'base_duration': _base_duration,
            'measure_duration': _measure_duration,
        }
        self.assess_data = res

    def _perform_assess(self):
        oh = self.assess_data['opincome']
        basics = False
        if oh['positive_last_4qtrs'] and oh['higher_than_comp'] and oh['slope'] > 0:
            basics = True

        finantially_sound = False
        if oh['growth_per_qtr'] >= OPINCOME_GROWTH_RATE: 
            finantially_sound = True

        om = self.assess_data['opmargin'].values()
        if all(x > OPMARGIN_THRESHOLD for x in om):
            finantially_sound = True

        # PER_level
        per = self.assess_data['PER']
        if per['PER_ltm'] <= PER_LOW: PER_level = 'Low'
        elif per['PER_ltm'] <= PER_MED: PER_level = 'Mid'
        else: PER_level = 'High'

        # volatility movement in measure period
        vol = self.assess_data['volatility']
        if vol['measure_to_base'] < 1-VOLATILITY_THRESHOLD: volatility = 'Dn'
        elif vol['measure_to_base'] < 1+VOLATILITY_THRESHOLD: volatility = '-'
        else: volatility = 'Up'

        # amount movement in measure period
        amt = self.assess_data['amount']
        if amt['measure_to_base'] < 1-AMOUNT_DAILY_THRESHOLD: amount = 'Dn'
        elif amt['measure_to_base'] < 1+AMOUNT_DAILY_THRESHOLD: amount = '-'
        else: amount = 'Up'

        # alpha_level
        alp = self.assess_data['alpha_beta']['measure_duration']
        if alp['alpha'] < -ALPHA_DAILY_THRESHOLD: alpha_level = 'underperform' # strong negative
        elif alp['alpha'] <=  ALPHA_DAILY_THRESHOLD: alpha_level = 'at_market'
        else: alpha_level = 'outperform' # strong positive

        # Choose Representative Categories
        market_sentiment = 'unchanged'
        if amount == 'Up' and volatility == 'Dn': market_sentiment = 'confidence_created'
        elif amount == 'Up' and volatility == 'Up': market_sentiment = 'unstable'
        elif amount == 'Dn' and volatility == 'Dn': market_sentiment = 'events_consumed'
        elif amount == 'Dn' and volatility == 'Up': market_sentiment = 'speculators_remained'

        # --------------------------------------------
        # categorization
        # --------------------------------------------
        if basics and finantially_sound:
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
            'financially_sound': finantially_sound,
            'PER_level': PER_level,
            'volatility_movement': volatility,
            'amount_movement': amount,
            'alpha_level': alpha_level,
            'market_sentiment': market_sentiment,
            'category': category,
        }
    
    # =======================================================================================================================
    # Sub SA analyses
    # =======================================================================================================================
    def _sub_sector_analyses(self):
        if not self.sub_sas:
            return

        # Parent sector
        self.shape['share'] = {
            'revenue': '-',
            '-r_rank': '-',
            'opincome': '-',
            '-o_rank': '-',
        }

        # Collect raw financial values
        revenues = [
            sa.shape['financials']['revenue_qtr'] * sa.meta['unit']
            for sa in self.sub_sas
        ]

        opincomes = [
            sa.shape['financials']['opincome_qtr'] * sa.meta['unit']
            for sa in self.sub_sas
        ]

        # Ranking: include negative values
        sorted_revenues = sorted(revenues, reverse=True)
        sorted_opincomes = sorted(opincomes, reverse=True)

        r_ranks = [
            sorted_revenues.index(value) + 1
            for value in revenues
        ]

        o_ranks = [
            sorted_opincomes.index(value) + 1
            for value in opincomes
        ]

        # Percentage calculation
        total_revenue = sum(revenues)

        # Only positive operating income contributes to shares
        positive_opincomes = [
            max(value, 0)
            for value in opincomes
        ]

        total_opincome = sum(positive_opincomes)

        # Populate each sub-sector
        for i, sa in enumerate(self.sub_sas):

            revenue = revenues[i]
            opincome = opincomes[i]

            sa.shape['share'] = {
                'revenue': (
                    round_sig(revenue / total_revenue)
                    if total_revenue > 0 else '-'
                ),

                '-r_rank': r_ranks[i],

                'opincome': (
                    round_sig(opincome / total_opincome)
                    if opincome > 0 and total_opincome > 0
                    else '-'
                ),

                '-o_rank': o_ranks[i],
            }

    # =======================================================================================================================
    # Display in html
    # =======================================================================================================================
    def get_combined_dict(self):
        combined_dict = {
            'meta': self.meta,
            'shape': self.shape,
            'assess_data': self.assess_data,
            'assess_result': self.assess_result
        }
        return combined_dict

    # =======================================================================================================================
    # Aggregation and plotting
    # =======================================================================================================================
    # cut data from start_date and define aggregation length
    def _create_plot(self, save_path: Path | None = None, aggregation: Literal['d', 'w', 'm', 'q'] = 'w'): 
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

        if save_path is None:
            if self.jsonmodel is not None:
                save_path=self.jsonmodel.get_json_path().with_suffix('.png')

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
        # fr_data pre-process before combine
        _fr_data = self.fr_data.copy() 
        _fr_data['revenue_ltm'] = _fr_data['revenue_qtr'].rolling(4).sum()
        _fr_data['opincome_ltm'] = _fr_data['opincome_qtr'].rolling(4).sum()
        _fr_data['opincome_qx4'] = _fr_data['opincome_qtr']*4
        _fr_data['opmargin_ltm'] = _fr_data['opincome_ltm']/_fr_data['revenue_ltm']
        _fr_data['opmargin_qtr'] = _fr_data['opincome_qtr']/_fr_data['revenue_qtr'] # quarterly opmargin

        # align index and combine (so fr_data only after start_date is used)
        self._aggr_dataset[_fr_data.columns]=_fr_data.reindex(self._aggr_dataset.index, method='ffill')

        # PER: assumes the same 4 quarters 
        self._aggr_dataset['PER_qx4'] = self._aggr_dataset['marcap']/self._aggr_dataset['opincome_qx4']
        self._aggr_dataset['PER_ltm'] = self._aggr_dataset['marcap']/self._aggr_dataset['opincome_ltm']

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
            if figsize is None: figsize = (12, 6)
            fig, axes = plt.subplots(
                2,
                1,
                figsize=(figsize[0], figsize[1]),
                sharex=True,
            )

            ax1, ax2 = axes

            self._plot_ma_panel(ax1)

            self._plot_financials_panel(ax2, use_ltm=True)

            # self._plot_financials_panel(ax3, use_ltm=False)

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

        # -----------------------------------------------------
        # baseline
        # -----------------------------------------------------
        ax.set_ylim(bottom=0)
        ax_r.set_ylim(bottom=0)

        # -----------------------------------------------------
        # annotations
        # -----------------------------------------------------
        ax.annotate(
            f"rp:{self._aggr_ma_plotdata.loc['recent_inc', 'marcap']:.0%}",
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
            f"sp:{self._aggr_ma_plotdata.at['slope', 'marcap']:,.0f}",
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

        _codelist = self.codelist if not self.is_index else ''
        if len(_codelist) > 5:
            _codelist = f"[{_codelist[0]}, {_codelist[1]}, ... : {len(_codelist)} codes]"

        ax.set_title(
            f"{self.meta['name']} {_codelist} | "
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
        opmargin = self._aggr_dataset[opmargin_col]
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
        scale_factor = np.nanmax(np.abs(opincome))

        if scale_factor == 0 or np.isnan(scale_factor):
            scale_factor = 1

        opmargin_scaled = opmargin * scale_factor

        ax.plot(
            x,
            opmargin_scaled,
            linestyle=':',
            color='red',
            linewidth=3,
            label='opmargin',
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
        ax.set_ylim(
            bottom=min(0, np.nanmin(opincome))
        )

        ax_r.set_ylim(
            bottom=min(0, np.nanmin(per))
        )

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

        ax.annotate(
            f"{opmargin.iloc[-1]:.2f}",
            xy=(x[-1], opmargin_scaled.iloc[-1]),
            xytext=(1, 2),
            textcoords='offset points',
            fontsize=12,
        )

        ax_r.annotate(
            f"{per.iloc[-1]:.1f}",
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
            f"opmargin (%) | "
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

# -----------------------------------------------------------------------------------------------
# Usage examples
# -----------------------------------------------------------------------------------------------
if __name__ == "__main__": 
    pm = ProfileManager()
    cm = ComponentManager()
    vm = ValueChainManager()

    # company profile
    code = '005930'
    pr = pm.get_item(code)
    sa = SectorAnalysis().process_profile(pr)

    # component
    name = "Memory"
    cp = cm.get_item(name)
    sa = SectorAnalysis().process_component(cp)

    # valuechain
    name = "Electronics"
    vc = vm.get_item(name)
    sa = SectorAnalysis().process_valuechain(vc)

    # index
    sa = SectorAnalysis().process_index('KOSDAQ')
    sa.print()
