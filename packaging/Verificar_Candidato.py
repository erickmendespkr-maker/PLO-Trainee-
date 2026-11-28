"""Reproducible acceptance diagnostics for the recovered candidate, not a release certificate."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
SOURCES={'cli':'plo5_cfr_cli','multistreet':'plo5_multistreet_cfr','multiway':'plo5_multiway_cfr','index_batch':'plo5_index_batch','rank_batch':'plo5_rank_batch','rank_worker':'plo5_rank_worker'}
ENV={'cli':'PLO5_CFR_EXE','multistreet':'PLO5_MULTISTREET_EXE','multiway':'PLO5_MULTIWAY_EXE','index_batch':'PLO5_INDEX_EXE','rank_batch':'PLO5_RANK_EXE','rank_worker':'PLO5_RANK_WORKER_EXE'}


def verify(output,*,native=False,timeout=600):
    output=Path(output).resolve()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():raise ValueError('Escolha uma pasta nova de logs.')
    if not 30<=timeout<=1800:raise ValueError('Timeout invalido')
    output.mkdir();env=dict(os.environ,OMP_THREAD_LIMIT='1',PYTHONUTF8='1',PYTHONPATH=str(ROOT));steps=[]
    for key in list(ENV.values())+['PLO5_RANK_CATALOG']:env.pop(key,None)
    def step(name,args,cwd=ROOT):
        t=perf_counter();log=output/(name+'.log');rc=None;error=None
        with log.open('xb') as f:
            try:rc=subprocess.run(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,timeout=timeout).returncode
            except (OSError,subprocess.TimeoutExpired) as exc:error=str(exc)
        steps.append(dict(name=name,exit_code=rc,error=error,seconds=perf_counter()-t,log=log.name));return rc==0
    ok=step('preflight',[sys.executable,str(ROOT/'video_analyzer/plo5_integrated_desktop.py'),'--check'])
    if ok and native:
        compiler=shutil.which('g++');ok=bool(compiler)
        if not ok:steps.append(dict(name='compiler',exit_code=None,error='g++ ausente'))
        else:
            bin_dir=output/'native';bin_dir.mkdir()
            for name,src in SOURCES.items():
                exe=bin_dir/(name+('.exe' if os.name=='nt' else ''))
                if not step('build_'+name,[compiler,'-O3','-std=c++17','-Wall','-Wextra','-Werror',str(ROOT/'native'/(src+'.cpp')),'-o',str(exe)]):ok=False;break
                env[ENV[name]]=str(exe)
            catalog=ROOT/'rank_macro07/rank_catalog.json'
            if catalog.is_file():env['PLO5_RANK_CATALOG']=str(catalog)
    if ok:ok=step('regression',[sys.executable,'-W','error::ResourceWarning','-m','unittest','discover','-v'],ROOT/'video_analyzer')
    report=dict(platform=platform.platform(),python=sys.version,native_requested=native,steps=steps,diagnostic_passed=ok,beta_ready=False,windows_acceptance_complete=False,drivehud_beta=False)
    (output/'summary.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8');return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--native',action='store_true');p.add_argument('--timeout',type=int,default=600);a=p.parse_args();r=verify(a.output,native=a.native,timeout=a.timeout);print(json.dumps(r,ensure_ascii=False));return 0 if r['diagnostic_passed'] else 1

if __name__=='__main__':raise SystemExit(main())
