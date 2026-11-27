"""Offline PPPoker card candidates using the original calibrated rank classifier."""
from plo5_fourcolor_cards import classify,observe,regions,load_bank
from plo5_singleflight import SingleFlight
from plo5_mixed_money import detect
from plo5_pre_gto_context import need


class PPPCardReader:
    def __init__(self,path,capacity=1024):
        self.bank=load_bank(path);self.cache=SingleFlight(capacity)
    def slot(self,image,t,f,i,bank):
        a,b=regions(image,t,f,i)
        key=(f,a.size,b.size,a.convert('RGB').tobytes(),b.convert('RGB').tobytes())
        return self.cache.get(key,lambda:classify(image,t,f,i,bank))
    def scan(self,image):
        rows=[]
        for t in range(1,5):
            r=observe(image,t,self.bank,slot_reader=self.slot)
            rows.append(dict(table_id=t,rank_profile='pppoker-1504x696-recalibrated-v1' if r['platform']=='pppoker' else None,**r))
        return rows
    def stats(self):return self.cache.stats()
