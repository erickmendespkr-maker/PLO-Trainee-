"""PRE-GTO 32: standalone Python/C++ parity audit, synthetic five-node game."""
import random, subprocess, time
from pathlib import Path
def norm(v):
 s=sum(v);return [x/s for x in v] if s else [1/len(v)]*len(v)
def reference(deals,nodes,sizes,it):
 r=[[0.]*s for s in sizes]; avg=[[0.]*s for s in sizes]
 for t in range(1,it+1):
  p=list(map(norm,r)); delta=[[0.]*s for s in sizes]
  def walk(i,d,r0,r1):
   a,ch,ids,b,m=nodes[i];w,q=deals[d]
   if a<0:return b+m*q
   k=ids[d]; pp=p[k];v=[walk(c,d,r0*(x if a==0 else 1),r1*(x if a==1 else 1)) for c,x in zip(ch,pp)];mean=sum(x*y for x,y in zip(pp,v))
   for j,x in enumerate(pp):
    delta[k][j]+=w*(r1 if a==0 else -r0)*(v[j]-mean);avg[k][j]+=t*w*(r0 if a==0 else r1)*x
   return mean
  for d in range(len(deals)):walk(0,d,1.,1.)
  r=[[max(0,x+y) for x,y in zip(a,b)] for a,b in zip(r,delta)]
 return list(map(norm,avg))
def native(exe,deals,nodes,sizes,it):
 lines=[f'{len(nodes)} {len(deals)} {len(sizes)} {it}']+[f'{w:.17g} {q:.17g}' for w,q in deals]
 for a,ch,ids,b,m in nodes:lines.append(' '.join(map(str,[a,len(ch),b,m,*ch,*ids])))
 out=subprocess.run([str(exe)],input='\n'.join(lines)+'\n',text=True,capture_output=True,check=True,timeout=10)
 return [list(map(float,l.split()[1:])) for l in out.stdout.splitlines()]
def main(exe):
 exe=Path(exe).resolve(strict=True)
 rng=random.Random(42);err=0;tp=tc=0;cases=0
 for j in range(50):
  d=1+j%12;weights=[rng.randrange(1,10) for _ in range(d)];deals=[(w/sum(weights),rng.random()) for w in weights];nodes=[(0,[1,2],[i%2 for i in range(d)],0,0),(-1,[],[],-.5,0),(1,[3,4],[min(d,2)+i%3 for i in range(d)],0,0),(-1,[],[],1,0),(-1,[],[],-2,4)];sizes=[2]*(min(d,2)+min(d,3));it=100+j*3
  t=time.perf_counter();a=reference(deals,nodes,sizes,it);tp+=time.perf_counter()-t;t=time.perf_counter();b=native(exe,deals,nodes,sizes,it);tc+=time.perf_counter()-t
  assert len(a)==len(b);err=max(err,max(abs(x-y) for aa,bb in zip(a,b) for x,y in zip(aa,bb)));cases+=1
 assert err<1e-8
 invalid=['0 1 1 10\n','3 1 1 10\n2 .75\n','3 1 1 10\n1 .75\n0 2 0 0 0 2 0\n']
 for s in invalid:assert subprocess.run([str(exe)],input=s,text=True,capture_output=True).returncode!=0
 print(f'PASS {cases} parity cases; max error={err:.3g}; python={tp:.6f}s native={tc:.6f}s speedup={tp/tc:.2f}x; rejected={len(invalid)}')
if __name__=='__main__':
 import sys
 main(sys.argv[1])
