"""장 마감 이후 모의 NAV를 갱신하고 해당 원장·그래프만 원격 저장소에 게시한다."""
import argparse
import json
import logging
import shutil
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def run(args, **kw):
    return subprocess.run(args,cwd=ROOT,check=True,encoding='utf-8',errors='replace',
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),**kw)

def git(*args):
    return run(['git',*args],capture_output=True).stdout.strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--publish',action='store_true')
    opts=parser.parse_args()
    env=os.environ.copy()
    settings=ROOT/'비공개자료/nav_settings.json'
    if settings.is_file():
        for key,value in json.loads(settings.read_text(encoding='utf-8-sig')).items():
            if key in {'KRX_KEY_FILE','CSI_INPUT','CSI_QUOTES','NAV_MIRROR'}:
                env.setdefault(key,value)
    env['PYTHONIOENCODING']='utf-8'
    issued=(ROOT/'CSI_strategy.ipynb').is_file()
    paths=['보고서/일별_NAV.csv','보고서/일별_NAV.svg']
    jobs=[['daily_nav.py','--daily']]
    if issued:
        paths+=['성과/추적_일별수익률_NAV.csv','성과/추적_리밸런싱.csv','성과/시세점검.csv']
        jobs=[['추적계산.py','--daily'],['daily_nav.py']]
    for job in jobs:
        result=run([sys.executable.replace('pythonw.exe','python.exe'),*job],env=env,capture_output=True)
        logging.info(result.stdout[-1500:])
    if env.get('NAV_MIRROR'):
        mirror=Path(env['NAV_MIRROR'])
        for name in ('일별_NAV.svg','일별_NAV.csv'):
            temp=mirror/(name+'.tmp')
            shutil.copyfile(ROOT/'보고서'/name,temp)
            temp.replace(mirror/name)
    if opts.publish:
        if git('branch','--show-current')!='main' or git('diff','--cached','--name-only'):
            raise RuntimeError('자동 게시 대기 · main 브랜치와 스테이징 상태를 확인하세요.')
        remote=git('ls-remote','origin','refs/heads/main').split()[0]
        if remote!=git('rev-parse','HEAD'):
            # 직전 자동 커밋의 전송만 실패한 경우에 한해 해당 커밋을 재시도한다.
            if (git('rev-parse','HEAD^')==remote and git('log','-1','--format=%s')=='장 마감 일별 모의 NAV 갱신'
                and set(git('-c','core.quotepath=false','diff','--name-only',remote,'HEAD').splitlines())<=set(paths)):
                git('push','origin','HEAD:main')
            else:
                raise RuntimeError('원격과 로컬이 달라 자동 게시를 중단했습니다.')
        if git('status','--porcelain','--',*paths):
            git('commit','--only','-m','장 마감 일별 모의 NAV 갱신','--',*paths)
            git('push','origin','HEAD:main')

if __name__=='__main__':
    folder=ROOT/'비공개자료'
    folder.mkdir(exist_ok=True)
    logging.basicConfig(filename=folder/'일별_NAV_갱신.log',encoding='utf-8',level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        main()
        logging.info('갱신 완료')
    except subprocess.CalledProcessError as error:
        logging.error('%s\n%s',error,(error.stderr or '')[-2000:])
        raise
    except Exception:
        logging.exception('마지막 정상 원장과 게시 상태를 확인하세요.')
        raise
