"""11월 23·24일 국내 종가 대조용. 시세표는 11월 24일 정규장 종료 후 취득."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import requests
import pandas as pd
base=Path(__file__).resolve().parent
folder=base/'추적입력'
audit=pd.read_csv(base/'성과/시세점검.csv')
co=pd.read_csv(folder/'종목매핑.csv',dtype=str).drop_duplicates('name').set_index('name')
def fetch(n):
    c=co.at[n,'code'];u=f'https://m.stock.naver.com/api/stock/{c}/price'
    for attempt in range(3):
        resp=requests.get(u,params=dict(page=1,pageSize=10),headers={'User-Agent':'Mozilla/5.0'},timeout=15)
        if resp.ok:
            rows=[x for x in resp.json() if x['localTradedAt']=='2026-11-24']
            if rows:
                x=rows[0]; close=float(x['closePrice'].replace(',',''));change=float(x['compareToPreviousClosePrice'].replace(',',''))
                return [(n,c,'20261124',close,x['accumulatedTradingVolume']), (n,c,'20261123',close-change,None)]
    return []
with ThreadPoolExecutor(8) as pool:
    rows=sum(list(pool.map(fetch,[n for n in audit.name if n in co.index and n!='카프로'])),[])
v=pd.DataFrame(rows,columns=['name','code','date','close','volume'])
v.to_csv(folder/'네이버_마감시세.csv',index=False);print(v.groupby('date').size())

