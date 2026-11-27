"""Persistent offline C++ equity worker; explicit executable, bounded timeout."""
import subprocess
import threading
import queue
from pathlib import Path
from math import sqrt,log
from plo5_pre_gto_context import cards,need

DECK=tuple(r+s for r in "23456789TJQKA" for s in "cdhs")
IDS={c:i for i,c in enumerate(DECK)}

class NativeEquity:
    def __init__(self, executable, *, timeout=120):
        p=Path(executable).resolve(strict=True)
        need(p.is_file() and type(timeout) in (int,float) and 0<timeout<=3600,"Invalid executable or timeout")
        self.timeout=timeout
        self.lock=threading.Lock()
        self.lines=queue.Queue()
        self.proc=subprocess.Popen([str(p),"stream"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL,text=True,bufsize=1)
        def reader():
            try:
                for line in self.proc.stdout:self.lines.put(line)
            finally:self.lines.put(None)
        self.reader=threading.Thread(target=reader,daemon=True)
        self.reader.start()
    def close(self):
        with self.lock:self._close()
    def _close(self):
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.reader.join(timeout=2)
        self.proc.stdin.close();self.proc.stdout.close()
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
    def equity(self,hands,*,trials=10000,seed=42,threads=2):
        need(type(hands) in (tuple,list) and 2<=len(hands)<=6,"Expected 2-6 holdings")
        hh=[cards(h) for h in hands]
        need(len(set().union(*map(set,hh)))==5*len(hh),"Overlapping holdings")
        need(type(trials) is int and 1<=trials<=10000000 and type(seed) is int and 0<=seed<2**64
             and type(threads) is int and 1<=threads<=32,"Invalid simulation options")
        request=" ".join(map(str,[trials,seed,threads,len(hh)]+[IDS[c] for h in hh for c in h]))+"\n"
        with self.lock:
            try:
                if self.proc.poll() is not None:raise RuntimeError("Native worker not running")
                self.proc.stdin.write(request);self.proc.stdin.flush()
                line=self.lines.get(timeout=self.timeout)
                if line is None:raise RuntimeError("Native worker exited")
                values=list(map(int,line.split()))
                need(len(values)==1+len(hh) and values[0]==trials and min(values[1:])>=0
                     and sum(values[1:])==60*trials,"Invalid native response")
            except (queue.Empty,ValueError,OSError,RuntimeError) as exc:
                self._close()
                raise RuntimeError("Native equity request failed") from exc
        shares=[x/(60*trials) for x in values[1:]]
        radius=sqrt(log(2*len(hh)/.05)/(2*trials))
        return dict(variant=5,backend="native_fixed_holdings_v1",trials=trials,seed=seed,
                    share_units=values[1:],share_denominator=60*trials,equity=shares,
                    simultaneous_ci95=[[max(0,x-radius),min(1,x+radius)] for x in shares],
                    gto_solution=False)

def selftest(executable):
    h=[["As","Kd","Qh","Jc","Ts"],["2s","3d","4h","5c","6s"]]
    with NativeEquity(executable) as w:
        a=w.equity(h,trials=1000,threads=1)
        b=w.equity(h,trials=1000,threads=4)
        assert a==b
    print("PASS persistent native worker")

if __name__=="__main__":
    import sys
    selftest(sys.argv[1])
