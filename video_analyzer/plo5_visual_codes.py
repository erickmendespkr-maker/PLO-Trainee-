"""Offline exact visual codes. No near-match substitution for money or actions."""
from collections import OrderedDict
from hashlib import sha256
import json
from pathlib import Path
from PIL import Image

VERSION = 'plo5-exact-visual-v1'
MAX_BANK_BYTES = 8 * 1024 * 1024


def need(ok, message):
    if not ok:
        raise ValueError(message)


def pixels(image, rect, mode='RGB'):
    need(type(rect) in (tuple, list) and len(rect)==4 and all(type(x) is int for x in rect), 'Invalid ROI')
    x,y,z,w=rect
    need(0<=x<z<=image.width and 0<=y<w<=image.height and (z-x)*(w-y)<=65536, 'ROI outside budget')
    need(mode in ('RGB','L'), 'Invalid mode')
    im=image.crop(rect).convert(mode)
    return (im.size,mode,im.tobytes())


def code(profile, field, patch):
    size,mode,data=patch
    need(type(profile) is str and 0<len(profile)<=128 and type(field) is str and 0<len(field)<=128,'Invalid namespace')
    need(type(size) is tuple and len(size)==2 and all(type(x) is int and x>0 for x in size) and size[0]*size[1]<=65536 and mode in ('RGB','L') and type(data) is bytes and len(data)==size[0]*size[1]*(3 if mode=='RGB' else 1),'Invalid patch')
    # Hash is for compact reporting; raw bytes are the equality key.
    header=json.dumps([VERSION,profile,field,size,mode],separators=(',',':')).encode()
    return sha256(header+b'\0'+data).hexdigest()


class Codebook:
    """Manual labels only; exact pixel conflicts abstain, never pick a majority."""
    def __init__(self, rows):
        need(type(rows) is list and len(rows)<=4096,'Invalid codebook')
        self._labels={};total=0
        for r in rows:
            need(type(r) is dict and set(r)=={'profile','field','size','mode','hex','label'},'Invalid row')
            need(type(r['hex']) is str and len(r['hex'])<=393216 and len(r['hex'])%2==0,'Invalid bytes')
            raw=bytes.fromhex(r['hex']);total+=len(raw);need(total<=MAX_BANK_BYTES,'Codebook pixel budget')
            patch=(tuple(r['size']),r['mode'],raw)
            code(r['profile'],r['field'],patch)
            label=r['label'];need(type(label) is str and 0<len(label)<=80,'Invalid label')
            key=(r['profile'],r['field'],patch)
            self._labels.setdefault(key,set()).add(label)
    @classmethod
    def load(cls,path):
        p=Path(path);need(p.is_file() and not p.is_symlink() and p.stat().st_size<=2*MAX_BANK_BYTES+1024**2,'Invalid bank file')
        d=json.loads(p.read_text('utf-8'));need(type(d) is dict and set(d)=={'version','rows'} and d['version']==VERSION,'Invalid bank version')
        return cls(d['rows'])
    def match(self,profile,field,patch):
        labels=self._labels.get((profile,field,patch),set())
        return dict(code=code(profile,field,patch),status='MATCH' if len(labels)==1 else 'CONFLICT' if labels else 'UNKNOWN',label=next(iter(labels)) if len(labels)==1 else None)


def labeled_row(profile,field,image,rect,label,mode='RGB'):
    size,mode,raw=pixels(image,rect,mode)
    return dict(profile=profile,field=field,size=list(size),mode=mode,hex=raw.hex(),label=label)


class LayoutCache:
    """Exact keys cover ALL patches read by the current mixed_money.detect."""
    def __init__(self,capacity=256):
        need(type(capacity) is int and 0<=capacity<=2048,'Invalid capacity')
        self.capacity=capacity;self.cache=OrderedDict();self.hits=self.misses=0
    def scan(self,image):
        from plo5_mixed_money import STARTS,detect
        need(image.mode=='RGB' and image.size==(1504,696),'Unsupported frame geometry')
        out=[]
        for t,x in enumerate(STARTS,1):
            rects=[(x+120,5,x+245,22)]
            for px,py in ((.25,.43),(.75,.43),(.30,.52),(.70,.52),(.30,.66),(.70,.66),(.5,.45),(.5,.75)):
                u,v=x+round(372*px),round(696*py);rects.append((u-3,v-3,u+4,v+4))
            key=b''.join(image.crop(r).tobytes() for r in rects)
            if key in self.cache:
                self.hits+=1;self.cache.move_to_end(key);p=self.cache[key]
            else:
                self.misses+=1;p=detect(image,t)
                if self.capacity:
                    self.cache[key]=p
                    while len(self.cache)>self.capacity:self.cache.popitem(last=False)
            out.append(p)
        return out
    def stats(self):
        return dict(hits=self.hits,misses=self.misses,entries=len(self.cache),key_pixel_bytes=sum(map(len,self.cache)))


class RegionReader:
    """Reuse exact patches across tables, frames and fields with explicit namespaces.
    Reader must consume only the supplied patch; do not pass a whole frame.
    Manual bank matches remain candidates, and conflict never invokes fallback.
    """
    def __init__(self,bank=None,capacity=512):
        from plo5_singleflight import SingleFlight
        self.bank=bank;self.memo=SingleFlight(capacity)
    def read(self,profile,field,image,rect,decoder,*,mode='RGB'):
        patch=pixels(image,rect,mode)
        def produce():
            if self.bank is not None:
                match=self.bank.match(profile,field,patch)
                if match['status']!='UNKNOWN':
                    return dict(source='MANUAL_CODE' if match['status']=='MATCH' else 'CONFLICT',label=match['label'],candidate_verified=False)
            im=Image.frombytes(patch[1],patch[0],patch[2])
            return dict(source='FALLBACK',label=decoder(im),candidate_verified=False)
        result=self.memo.get((profile,field,patch[0],patch[1],patch[2]),produce)
        return dict(result,visual_code=code(profile,field,patch))
    def stats(self):return self.memo.stats()


class MixedReader:
    """Drop-in mixed-review money reader; all four slots remain in the roster."""
    def __init__(self,capacity=512,workers=3,*,bank=None):
        from plo5_singleflight import SingleFlight
        need(type(workers) is int and 1<=workers<=3,'Invalid workers')
        self.cache=SingleFlight(capacity);self.layout=LayoutCache(capacity);self.workers=workers;self.bank=bank
    def scan(self,image):
        from concurrent.futures import ThreadPoolExecutor
        from plo5_mixed_money import STARTS,REGIONS,read,parse
        platforms=self.layout.scan(image)
        def task(j):
            t,p,f=j
            if p is None:result=dict(value_bb=None,raw='',confidence=None,source='NO_LAYOUT',visual_code=None)
            else:
                x=STARTS[t-1];a,b,c,d=REGIONS[p][f];patch=pixels(image,(x+a,b,x+c,d),'L')
                profile=p+'-1504x696-money-v1'
                def produce():
                    if self.bank is not None:
                        m=self.bank.match(profile,f,patch)
                        if m['status']=='CONFLICT':return dict(value_bb=None,raw='',confidence=None,source='CONFLICT')
                        if m['status']=='MATCH':
                            v=parse(m['label'],p,f)
                            return dict(value_bb=v,raw=m['label'],confidence=None,source='MANUAL_CODE' if v is not None else 'INVALID_LABEL')
                    return dict(read(image,t,p,f),source='OCR_FALLBACK')
                result=dict(self.cache.get((profile,f,patch[0],patch[1],patch[2]),produce),visual_code=code(profile,f,patch))
            return dict(table_id=t,platform=p,field=f,**result,layout_candidate_active=p is not None,financial_result_verified=False)
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(task,[(t,p,f) for t,p in enumerate(platforms,1) for f in ('stack','pot')]))
