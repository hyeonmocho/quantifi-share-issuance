"""원 전략의 월말 NAV를 재현하고 세 하위계좌의 보유 상태를 이어받아 최신 종가로 평가한다."""
from pathlib import Path
import os, json, sys
import numpy as np
import pandas as pd
base = Path(__file__).resolve().parent
raw = Path(os.environ.get('CSI_INPUT', base))
supp = base/'추적입력'
out = base/'성과'
out.mkdir(exist_ok=True)
nb = json.loads((base/'CSI_strategy.ipynb').read_text(encoding='utf-8'))
src = lambda i: ''.join(nb['cells'][i]['source'])
os.chdir(raw)
for i in (6,7,9,11,13,15,17,19,21):
    exec(compile(src(i),f'CSI_strategy.ipynb:{i}','exec'))
logs=[]
hist,_,_=run_strategy(strategy_params(),port_schedules,all_month_ends,logs)
nav=(1+hist).cumprod()
published_nav=9.913986
print('재실행 NAV',nav.tail(),flush=True)
saved_may_aug=np.array([.102866,.038258,.051136,.006728])
assert np.allclose(hist.iloc[-4:],saved_may_aug,atol=1e-5), hist.tail()
pd.DataFrame({'return':hist,'nav':nav}).to_csv(out/'검증기간_월말NAV.csv',index_label='date')
# 8월 OOS 마감이 3개월 전략의 리밸런싱 주기를 강제로 재설정하지 않도록
# 마지막 정상 분기의 시작 상태로 돌아간 후, 원래 일정대로 각 분기를 재평가한다.
state={w['port']:w for w in logs if w['end']==hist.index[-1]}
assert len(state)==3
if '--history' in sys.argv:
    print('HISTORY',nav.iloc[-1],[(k,str(w['start'])) for k,w in state.items()])
    sys.exit()
from concurrent.futures import ThreadPoolExecutor
import requests, time
cut=pd.Timestamp('2026-08-31')
asof=pd.Timestamp(os.environ.get('TRACK_END','2026-11-24'))
px=pd.read_parquet(supp/'수정주가.parquet')
cap=pd.read_parquet(supp/'시총_백만원.parquet')
def extend(old,new,anchor,scale):
    # 같은 날의 가격으로 수정계수 기준일을 맞춘 뒤 후속 수익률만 연결한다.
    if scale:
        ratio=old.loc[anchor]/new.loc[anchor].where(new.loc[anchor]>0)
        new=new.mul(ratio,axis=1)
    return pd.concat([old.loc[:anchor],new.loc[new.index>anchor]]).sort_index()
last_total=adj_close.index[-1]
nodiv=adj_close_nodiv.loc[adj_close_nodiv.index.notna()].dropna(how='all')
cap0=market_capitalization.dropna(how='all')
anchor=cap0.index[-1]
common=cap.loc[anchor].div(cap0.loc[anchor]).dropna()
assert abs(common.median()-1)<0.001, common.describe()
adj_close_nodiv=extend(nodiv,px,cut,True)
market_capitalization=extend(cap0,cap,anchor,False)
return_monthly=adj_close_nodiv.resample('ME').last().pct_change(fill_method=None)
return_for_log=return_monthly.where(return_monthly>-1)
market_cap_monthly=market_capitalization.resample('ME').last()
market_cap_for_log=market_cap_monthly.where(market_cap_monthly>0)
exec(src(9))
exec(src(15))
params=strategy_params()
needed=set()
for w in state.values():
    for key in ['prev_long_w','prev_short_w','hold_long','hold_short']:
        needed.update(w[key].keys())
for date in pd.date_range(cut,'2026-10-31',freq='ME'):
    l,s=select_candidates(date,params)
    needed.update(l[:n]+s[:n])
codes=pd.read_csv(supp/'종목매핑.csv',dtype=str).drop_duplicates('name',keep='first').set_index('name').code.to_dict()
cache=supp/'시세';cache.mkdir(exist_ok=True)
def download(name):
    code=codes.get(name)
    if not code:return None
    file=cache/(code+'.csv')
    if file.exists():
        saved=pd.read_csv(file,index_col=0,parse_dates=True)
        if saved.index.max()>=asof-pd.offsets.BDay(1):return saved.loc[:asof]
    for attempt in range(2):
        for mkt in ['KS','KQ']:
            try:
                symbol=code+'.'+mkt
                u='https://query1.finance.yahoo.com/v8/finance/chart/'+symbol
                pars=dict(period1=int(pd.Timestamp('2026-08-01',tz='Asia/Seoul').timestamp()),period2=int((asof+pd.Timedelta(days=1)).tz_localize('Asia/Seoul').timestamp()),interval='1d',events='div,splits')
                res=requests.get(u,params=pars,headers={'User-Agent':'Mozilla/5.0'},timeout=9)
                if res.status_code!=200:continue
                a=res.json()['chart']['result'][0]
                assert a['meta']['symbol']==symbol and a['meta']['currency']=='KRW'
                ind=a['indicators']; dates=pd.to_datetime(a['timestamp'],unit='s',utc=True).tz_convert('Asia/Seoul').tz_localize(None).normalize()
                vals=pd.DataFrame({'close':ind['quote'][0]['close'],'adj':ind['adjclose'][0]['adjclose']},index=dates).dropna().loc[:asof]
                if len(vals)<3:continue
                vals.to_csv(file,index_label='date');return vals
            except (ValueError,KeyError,IndexError,requests.RequestException,AssertionError):continue
        time.sleep(.3)
    return None
names=sorted(needed)
with ThreadPoolExecutor(8) as pool:
    data=dict(zip(names,pool.map(download,names)))
# FnGuide의 배당반영 가격 만료 후, 검증한 공급자 수익률로 연결한다.
active=extend(adj_close,px,last_total,True)
audit=[]
local_close=pd.read_csv(supp/'네이버_마감시세.csv',dtype={'date':str})
local_close['date']=pd.to_datetime(local_close.date)
official=pd.concat([pd.read_csv(p,dtype={'ISU_CD':str}) for p in supp.glob('KRX_*_20261123.csv')]).set_index('ISU_CD')
for name,quote in data.items():
    if name=='카프로':
        closing=pd.read_csv(supp/'카프로_KRX_정리매매.csv',index_col=0,parse_dates=True).close
        assert closing.loc[last_total]==adj_close.at[last_total,name]
        active.loc[closing.index,name]=closing
        audit.append((name,'KRX 정리매매 종가',1,0));continue
    if quote is None or last_total not in quote.index or name not in adj_close or pd.isna(adj_close.at[last_total,name]):
        raise ValueError(('평가시세 연결 실패',name))
    ref=px[name].loc[last_total:] if name in px else pd.Series(dtype=float)
    diff=(ref.pct_change(fill_method=None)-quote.close.pct_change(fill_method=None)).dropna()
    if len(diff)<5 or diff.abs().median()>0.001 or diff.abs().quantile(.90)>0.004:
        raise ValueError(('FnGuide 교차검증 실패',name))
    series=quote.adj/quote.at[last_total,'adj']*adj_close.at[last_total,name]
    closing=local_close.loc[local_close.name.eq(name)].set_index('date').close
    prev=asof-pd.offsets.BDay(1)
    assert prev in series and closing.loc[prev]>0 and closing.loc[asof]>0,name
    krx=float(str(official.at[codes[name],'TDD_CLSPRC']).replace(',',''))
    assert abs(closing.loc[prev]/krx-1)<.0001,(name,closing.loc[prev],krx)
    # 국내 장 마감 확정 종가. 전날 배당조정 평가액에 오늘 가격 등락률을 연결한다.
    series.loc[asof]=series.loc[prev]*closing.loc[asof]/closing.loc[prev]
    active=active.reindex(active.index.union(series.index[series.index>last_total]))
    active.loc[series.index[series.index>last_total],name]=series.loc[series.index>last_total]
    audit.append((name,'배당조정 시세 · 마지막 날 국내 종가',len(diff),diff.abs().max()))
pd.DataFrame(audit,columns=['name','source','overlap_returns','max_abs_diff']).to_csv(out/'시세점검.csv',index=False)
print('coverage',pd.Series([x[1] for x in audit]).value_counts().to_dict(),flush=True)
adj_close=active.loc[:asof].dropna(how='all')
exec(src(13)); exec(src(15))
cal=adj_close.index
last=cal[-1]
dates=cal[cal>cut]
def track():
 ports={}; holdings=[]
 for port,w in state.items():
    s=w['start']; pl=w['prev_long_w'];ps=w['prev_short_w']; rts=[]
    while s<last:
        e=min(s+pd.offsets.MonthEnd(3),last)
        ds=cal[(cal>s)&(cal<=e)]
        cps=[d+pd.offsets.MonthEnd(0) if d==cal[cal<=d+pd.offsets.MonthEnd(0)][-1] and d+pd.offsets.MonthEnd(0)<=e else d for d in ds]
        ww=strategy_window(s,e,pl,ps,cps,params)
        if e>cut:
            for side in ('long','short'):
                for t,weight in ww['hold_'+side].items(): holdings.append((port,s,side,t,weight))
        rts.append(pd.Series(ww['rets'].values,index=ds));pl,ps=ww['next_long_w'],ww['next_short_w'];s=e
    ports[port]=pd.concat(rts).reindex(dates)
 return pd.DataFrame(ports),holdings
daily,holdings=track()
assert not daily.isna().any().any()
# 원 노트북은 매월 세 슬리브의 월 수익률을 동일가중한다. 월중에는 비중이 움직인다.
group=daily.index.to_period('M')
wealth=(daily+1).groupby(group).cumprod().mean(axis=1)
prev=wealth.groupby(group).shift().fillna(1)
daily['return']=wealth/prev-1
daily['nav']=published_nav*(1+daily['return']).cumprod()
base_price=adj_close.at[cut,'카프로']
adj_close.loc[adj_close.index>cut,'카프로']=adj_close.loc[adj_close.index>cut,'카프로'].where(adj_close.loc[adj_close.index>cut,'카프로'].isna(),base_price)
_liq_px_cache.pop('카프로',None)
flat,_=track()
flat_within_month=(flat+1).groupby(group).cumprod().mean(axis=1)
daily['카프로가격손익제외']=flat_within_month/flat_within_month.groupby(group).shift().fillna(1)-1
for month,g in daily.groupby(group):
    assert abs((g['return']+1).prod()-(g[['port_A','port_B','port_C']]+1).prod().mean())<1e-10
daily.to_csv(out/'추적_일별수익률_NAV.csv',index_label='date',encoding='utf-8-sig')
pd.DataFrame(holdings,columns=['port','signal','side','name','leg_weight']).to_csv(out/'추적_리밸런싱.csv',index=False)
print(daily.tail().to_string(),flush=True)

