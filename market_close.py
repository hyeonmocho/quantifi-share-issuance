"""거래소가 양 시장 마감 자료를 게시한 거래일만 읽는다."""
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor

def sessions_after(day):
    day = pd.Timestamp(day)
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    end = pd.Timestamp(now.date()) - pd.Timedelta(days=int(now.hour < 16))
    if end <= day:
        return []
    response = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/^KS11',
        params={'period1': int(day.tz_localize('Asia/Seoul').timestamp()),
                'period2': int((end + pd.Timedelta(days=1)).tz_localize('Asia/Seoul').timestamp()),
                'interval':'1d'}, headers={'User-Agent':'Mozilla/5.0'},timeout=20)
    response.raise_for_status()
    dates = pd.to_datetime(response.json()['chart']['result'][0]['timestamp'],unit='s',utc=True).tz_convert('Asia/Seoul').tz_localize(None).normalize()
    return sorted(set(d for d in dates if day < d <= end))

def market_dates(first, keyfile, cache):
    days=sessions_after(first)
    cache.mkdir(exist_ok=True,parents=True)
    def fetch(date):
        path=cache / (date.strftime('%Y%m%d')+'.parquet')
        if path.exists():
            return pd.read_parquet(path)
        key=Path(keyfile).read_text(encoding='utf-8-sig').strip()
        tables=[]
        for market in ('stk','ksq'):
            response=requests.get(f'https://data-dbg.krx.co.kr/svc/apis/sto/{market}_bydd_trd',
                params={'basDd':date.strftime('%Y%m%d')},headers={'AUTH_KEY':key},timeout=20)
            response.raise_for_status()
            rows=response.json()['OutBlock_1']
            if not rows:
                return None
            frame=pd.DataFrame(rows).set_index('ISU_CD')
            if not frame.BAS_DD.eq(date.strftime('%Y%m%d')).all() or not frame.index.is_unique:
                raise ValueError(f'거래소 일자 또는 코드 오류 {date}')
            tables.append(frame[['TDD_CLSPRC','CMPPREVDD_PRC','MKTCAP','ACC_TRDVAL','LIST_SHRS']])
        result=pd.concat(tables).apply(pd.to_numeric,errors='raise')
        if not result.index.is_unique:
            raise ValueError('양 시장 중복 코드')
        temp=path.with_suffix('.tmp')
        result.to_parquet(temp)
        temp.replace(path)
        return result
    with ThreadPoolExecutor(3) as pool:
        frames=list(pool.map(fetch,days))
    result={}
    for day,frame in zip(days,frames):
        if frame is None:
            if day != days[-1]:
                raise ValueError(f'중간 거래일 공식 시세 미확인 {day.date()}')
            break
        result[day]=frame
    return result
