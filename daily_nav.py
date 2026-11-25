"""발행주식 수 및 지수 편입 저장소의 일별 NAV를 기준일 종가 1로 표시한다."""
from pathlib import Path
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import dates as md, font_manager

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '보고서'
BASE = pd.Timestamp('2026-09-01')
COLORS = ['#922d3e','#197867','#52658d']


def checked(data):
    if not data.index.is_monotonic_increasing or not data.index.is_unique or BASE not in data.index:
        raise ValueError('기준일이 없거나 거래일이 중복 또는 역순입니다.')
    if not np.isfinite(data).all().all() or not data.gt(0).all().all():
        raise ValueError('일별 평가액을 확인하세요.')
    return data.loc[BASE:]


def draw(values, phase, returns):
    values = checked(values)
    rel = values.div(values.loc[BASE])
    result = pd.concat([phase.rename('구간'),rel.add_suffix('_NAV'),returns.add_suffix('_일수익률')],axis=1).loc[rel.index]
    post = phase.index[phase.eq('후속 보유분 평가')]
    if len(post):
        result.loc[post,'후속첫날종가1_통합NAV'] = values.loc[post,'통합']/values.at[post[0],'통합']
    OUT.mkdir(exist_ok=True)
    for family in ('Malgun Gothic','Noto Sans CJK KR','AppleGothic'):
        if any(f.name == family for f in font_manager.fontManager.ttflist):
            plt.rcParams['font.family']=family
            break
    plt.rcParams['axes.unicode_minus']=False
    plt.rcParams['svg.fonttype']='path'
    plt.rcParams['svg.hashsalt']='quantifi'
    fig,ax=plt.subplots(figsize=(10.5,4.8))
    fig.subplots_adjust(left=.10,right=.97,top=.77,bottom=.19)
    title='발행주식 수 롱숏' if len(values.columns)==1 else 'KOSPI200·100 편입 예측'
    fig.text(.10,.91,title+'   |   일별 모의 NAV',fontsize=18,fontweight='bold',color='#202738')
    fig.text(.10,.837,f'2026.09.01 종가 = 1     /     최종 관측 {values.index[-1]:%Y.%m.%d}',fontsize=10,color='#49566b')
    ax.axhline(1,color='#737982',lw=.8,ls=':')
    for i,col in enumerate(values):
        line=rel[col]
        end=post[0] if len(post) else line.index[-1]+pd.Timedelta(days=1)
        back=line[line.index<end]
        ax.plot(back.index,back,color=COLORS[i],lw=2.4 if i==0 else 1.5,label=col)
        if len(post):
            live=line.loc[back.index[-1]:]
            ax.plot(live.index,live,color=COLORS[i],ls='--',lw=2 if i==0 else 1.4)
        ax.scatter(line.index[-1],line.iloc[-1],s=18,color=COLORS[i],zorder=3)
    if len(post):
        ax.axvspan(post[0],rel.index[-1],color='#d9e0e7',alpha=.45)
    ax.xaxis.set_major_locator(md.AutoDateLocator(minticks=4,maxticks=8))
    ax.xaxis.set_major_formatter(md.DateFormatter('%m.%d'))
    ax.grid(axis='y',color='#e0e2e6')
    ax.spines[['top','right','left']].set_visible(False)
    ax.legend(frameon=False,loc='best',ncol=len(values.columns))
    ax.set_ylabel('NAV')
    fig.text(.10,.055,'점선은 마지막 보유분의 종가 평가 · 신규 주문과 청산은 다음 집행 원장 갱신 때 반영' if len(post)
        else '각 거래일 종가 평가 · 첫날 일수익률은 CSV에 별도로 표시',fontsize=9,color='#536070')
    pic=OUT/'일별_NAV.svg'
    tmp=pic.with_suffix('.tmp')
    fig.savefig(tmp,format='svg',metadata={'Date':None})
    plt.close(fig)
    tmp.replace(pic)
    target=OUT/'일별_NAV.csv'
    tmp=target.with_suffix('.tmp')
    result.to_csv(tmp,index_label='날짜',encoding='utf-8-sig',float_format='%.10f')
    tmp.replace(target)
    print(result.tail(1).to_string())

if __name__ == '__main__':
    source=pd.read_csv(ROOT/'성과/추적_일별수익률_NAV.csv',index_col='date',parse_dates=True)
    vals=source[['nav']].rename(columns={'nav':'발행주식 수'})
    ret=source[['return']].set_axis(vals.columns,axis=1)
    if not np.allclose(vals.iloc[:,0].pct_change().iloc[1:],ret.iloc[1:,0],atol=1e-9):
        raise ValueError('일별 NAV와 일수익률 불일치')
    draw(vals,pd.Series('OOS 이후 모의 운용',index=vals.index),ret)
