"""Single persistent native rank process; bounded batches and explicit lifetime."""
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from math import isfinite
from plo5_index_native import CARD_ID, SIZES
from plo5_pre_gto_context import cards, need
from plo5_post_gto_context import DECK


class RankWorker:
    def __init__(self, executable, *, timeout=30):
        need(type(timeout) in (int,float) and isfinite(timeout) and 0<timeout<=120,'Invalid timeout')
        self.timeout=timeout;self.lock=Lock();self.closed=False
        self.process=subprocess.Popen([str(Path(executable).resolve(strict=True))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL, text=True,encoding='ascii')
        self.executor=ThreadPoolExecutor(max_workers=1)

    def _exchange(self,street,lines):
        n=len(lines);p=self.process
        p.stdin.write(f'{street} {n}\n'+'\n'.join(lines)+'\n');p.stdin.flush()
        need(p.stdout.readline(64)==f'OK {n}\n','Invalid worker response')
        out=[]
        for _ in lines:
            line=p.stdout.readline(64);fields=line.split()
            need(line.endswith('\n') and len(fields)==2,'Invalid worker row')
            i,r=map(int,fields);need(0<=i<SIZES[street] and 1<=r<=7462,'Invalid worker result')
            out.append(dict(index=i,rank=r,source='NATIVE_COMPUTED'))
        return out

    def lookup(self,street,states):
        need(type(street) is int and street in (3,4,5),'Invalid street')
        need(type(states) is list and len(states)<=4096,'Invalid batch')
        lines=[]
        for h,b in states:
            h=cards(h)
            need(type(b) in (tuple,list) and len(b)==street and all(type(x) is str and x in DECK for x in b) and len(set(h+list(b)))==5+street,'Invalid board')
            lines.append(' '.join(str(CARD_ID[x]) for x in h+list(b)))
        with self.lock:
            need(not self.closed,'Worker closed')
            if not lines:return []
            unique=list(dict.fromkeys(lines))
            future=self.executor.submit(self._exchange,street,unique)
            try:out=future.result(timeout=self.timeout)
            except BaseException:
                self._close();raise
            indexed=dict(zip(unique,out));return [dict(indexed[x]) for x in lines]

    def _close(self):
        if self.closed:return
        self.closed=True;p=self.process
        if p.poll() is None:p.kill()
        p.wait();self.executor.shutdown(wait=True,cancel_futures=True)
        try:p.stdin.close()
        except OSError:pass
        finally:p.stdout.close()

    def close(self):
        with self.lock:self._close()
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
