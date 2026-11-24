"""11월 FnGuide 갱신본을 원래 종목 식별자와 금융 단위에 맞춰 축소 저장한다."""
import os
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
base=Path(__file__).resolve().parent
q=Path(os.environ['QUANTIFI_ROOT'])
d=q/'개인프로젝트/01_data'
s=base/'추적입력'
s.mkdir(exist_ok=True)
def names(path):
    w=load_workbook(path,read_only=True)
    rows=w.active.iter_rows(min_row=9,max_row=10,values_only=True)
    codes=list(next(rows))[1:]; ns=list(next(rows))[1:]
    w.close()
    return {str(c).removeprefix('A'):n for c,n in zip(codes,ns) if c and n}
old=names(q/'메인세션/data/raw/수정주가배당반영.xlsx')
new=names(next((d/'raw/fnguide').glob('*수정주가_1120.xlsx')))
rename={n: old.get(c,n) for c,n in new.items()}
pd.DataFrame([(c,n,old.get(c,n)) for c,n in new.items()],columns=['code','current','name']).to_csv(s/'종목매핑.csv',index=False)
def subset(pat):
    p=next((d/'processed/fnguide').glob(pat))
    x=pd.concat([b.loc[b.index>='2026-08-01'] for b in pd.read_csv(p,index_col=0,chunksize=250,thousands=',',low_memory=False)])
    x.index=pd.to_datetime(x.index)
    x=x.apply(pd.to_numeric,errors='coerce').rename(columns=rename)
    if x.columns.duplicated().any(): raise ValueError(x.columns[x.columns.duplicated()].tolist())
    return x
px=subset('*수정주가_1120.csv')
px.to_parquet(s/'수정주가.parquet')
cap=subset('*종가_1120.csv')*subset('*상장주식수_1120.csv')/1e6
cap.to_parquet(s/'시총_백만원.parquet')
print(px.shape,cap.shape,cap['삼성전자'].loc['2026-09-04'])

