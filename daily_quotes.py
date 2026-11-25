"""상장 종목의 배당 반영 수익률을 KRX 마감 종가와 대조한다."""
import numpy as np
import pandas as pd
import requests


def load_quotes(code, first, end, directory):
    directory.mkdir(parents=True,exist_ok=True)
    path = directory / f'{code}.parquet'
    if path.exists():
        saved = pd.read_parquet(path)
        if first in saved.index and end in saved.index:
            return saved
    for suffix in ('KS','KQ'):
        symbol = f'{code}.{suffix}'
        response = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/'+symbol,
            params={'period1':int(first.tz_localize('Asia/Seoul').timestamp()),
                    'period2':int((end+pd.Timedelta(days=1)).tz_localize('Asia/Seoul').timestamp()),
                    'interval':'1d','events':'div,splits'},
            headers={'User-Agent':'Mozilla/5.0'}, timeout=20)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        series = response.json()['chart']['result'][0]
        if series['meta']['symbol'] != symbol or series['meta']['currency'] != 'KRW':
            raise ValueError(symbol)
        dates = pd.to_datetime(series['timestamp'],unit='s',utc=True).tz_convert('Asia/Seoul').tz_localize(None).normalize()
        v = series['indicators']
        frame = pd.DataFrame({'close':v['quote'][0]['close'],'adj':v['adjclose'][0]['adjclose']},index=dates)
        if not frame.index.is_unique or first not in frame.index or end not in frame.index:
            continue
        temp=path.with_suffix('.tmp')
        frame.to_parquet(temp)
        temp.replace(path)
        return frame
    raise ValueError(f'{code} 배당조정 시세 연결 실패')


def extend_total_return(series, code, markets, first, end, directory):
    prices = load_quotes(code,first,end,directory)
    days = [d for d in markets if first <= d <= end]
    raw = np.array([markets[d].at[code,'TDD_CLSPRC'] for d in days])
    obs = prices.reindex(days)
    if not np.isfinite(obs[['close','adj']]).all().all() or not obs.gt(0).all().all():
        raise ValueError(f'{code} 배당조정 시세 누락')
    # 무거래 종목의 벤더 과거가격은 수정 기준이 다를 수 있다. 양쪽에서
    # 가격이 그대로이고 발행주식 수도 그대로인 구간만 평가액을 유지한다.
    same_level=np.isclose(obs.close,raw,rtol=1e-5,atol=.01)
    for i in range(1,len(days)):
        prev,cur=markets[days[i-1]].loc[code],markets[days[i]].loc[code]
        frozen=(cur.ACC_TRDVAL==0 and cur.TDD_CLSPRC==prev.TDD_CLSPRC
                and cur.CMPPREVDD_PRC==0 and cur.LIST_SHRS==prev.LIST_SHRS
                and obs.close.iloc[i]==obs.close.iloc[i-1] and obs.adj.iloc[i]==obs.adj.iloc[i-1])
        if not (frozen or (same_level[i-1] and same_level[i])):
            raise ValueError(f'{code} {days[i].date()} 공식 종가 또는 기업행위 확인 필요')
    extension = series.at[first]*obs.adj.iloc[1:]/obs.at[first,'adj']
    return pd.concat([series,extension])
