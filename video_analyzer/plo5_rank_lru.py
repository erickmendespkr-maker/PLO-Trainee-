"""Bounded exact rank reuse across individual offline decisions and runout batches."""
from collections import OrderedDict
from plo5_pre_gto_context import cards,need
from plo5_post_gto_context import DECK


class CachedRankWorker:
    """Single caller, wraps an existing RankWorker without owning its lifecycle.
    Board order retained because the returned combinatorial index is street-aware.
    """
    def __init__(self,worker,capacity=8192):
        need(type(capacity) is int and 0<=capacity<=65536,'Invalid rank cache capacity');self.worker=worker;self.capacity=capacity;self.cache=OrderedDict();self.hits=self.misses=0
    def lookup(self,street,states):
        need(type(street) is int and street in (3,4,5) and type(states) is list and len(states)<=4096,'Invalid rank batch')
        keys=[];missing={};available={}
        for h,b in states:
            h=cards(h);need(type(b) in (tuple,list) and len(b)==street and all(type(x) is str and x in DECK for x in b) and len(set(h+list(b)))==5+street,'Invalid board')
            k=(street,tuple(h),tuple(b));keys.append(k)
            if k in self.cache:
                self.hits+=1;self.cache.move_to_end(k);available[k]=self.cache[k]
            elif k not in missing:
                self.misses+=1;missing[k]=(h,list(b))
        if missing:
            rows=self.worker.lookup(street,list(missing.values()));need(len(rows)==len(missing),'Incomplete native rank batch')
            for k,r in zip(missing,rows):
                available[k]=dict(r)
                if self.capacity:
                    self.cache[k]=dict(r);self.cache.move_to_end(k)
                    while len(self.cache)>self.capacity:self.cache.popitem(last=False)
        return [dict(available[k]) for k in keys]
    def stats(self):return dict(hits=self.hits,misses=self.misses,entries=len(self.cache),capacity=self.capacity)
