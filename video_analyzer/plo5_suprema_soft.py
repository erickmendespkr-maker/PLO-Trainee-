"""Experimental offline Suprema rank features with brightness-relative soft ink masks."""
import numpy as np
import cv2
from PIL import Image
from plo5_suprema_suits import regions, felt, detect, BOARD_X
from plo5_mixed_money import STARTS
from plo5_suprema_cards import highlighted
from plo5_fourcolor_cards import RANKS,SUITS


def soft_ink(im):
    a=np.asarray(im.convert('RGB'),dtype=np.float32)
    hi=a.max(axis=2);lo=a.min(axis=2)
    neutral=(hi-lo<=np.maximum(12,hi*.14))&(lo>=40)
    if neutral.mean()<.25:return None,None
    bg=float(np.percentile(hi[neutral],75))
    if bg<45:return None,None
    r,g,b=a.transpose(2,0,1)
    contrasts=np.stack((g-np.maximum(r,b),b-np.maximum(r,g),r-np.maximum(g,b),bg-hi),axis=0)
    # Ignore colored dark pixels for the neutral black class.
    contrasts[3]=np.where(hi-lo<=np.maximum(12,hi*.20),contrasts[3],0)
    contrasts=np.clip(contrasts/bg,0,1)
    totals=(np.maximum(contrasts-.10,0)).sum(axis=(1,2))
    order=np.argsort(totals);idx=int(order[-1]);best=float(totals[idx])
    if best<.85 or best<1.45*float(totals[order[-2]]):return None,None
    # For rank geometry use the magnitude of the dark ink, not a hard saturation cutoff.
    weight=np.clip((bg-lo)/bg,0,1)
    chroma=contrasts[idx]
    weight=np.where(chroma>=.065,weight,0)
    peak=float(np.percentile(weight[weight>0],90)) if np.any(weight>0) else 0
    if peak<.18:return None,None
    weight=np.clip(weight/peak,0,1);binary=(weight>=.24).astype(np.uint8)
    n,labels,stats,_=cv2.connectedComponentsWithStats(binary,8)
    if n<2:return None,None
    largest=int(stats[1:,cv2.CC_STAT_AREA].max());keep=[i for i in range(1,n) if stats[i,cv2.CC_STAT_AREA]>=max(2,largest*.12)]
    weight=np.where(np.isin(labels,keep),weight,0)
    ys,xs=np.nonzero(weight)
    if len(xs)<4:return None,None
    crop=weight[ys.min():ys.max()+1,xs.min():xs.max()+1];h,w=crop.shape
    mask=np.rint(cv2.resize(crop,(20,24),interpolation=cv2.INTER_LINEAR)*255).astype(np.uint8)
    return SUITS[idx],(mask.tobytes(),w/h)


def showdown_regions(image,t,i):
    """Conservative alternate geometry: three broad golden top edges required."""
    x0=STARTS[t-1];flags=[]
    for x in BOARD_X:
        q=np.asarray(image.crop((x0+x-3,242,x0+x+46,248)).convert('RGB'),dtype=np.int16)
        r,g,b=q.transpose(2,0,1)
        yellow=(r>=145)&(g>=110)&(r>b+55)&(g>b+45)
        flags.append(int((yellow.sum(axis=1)>=20).sum())>=2)
    if sum(flags)!=3:return None
    if not flags[i]:return regions(image,t,'board',i)
    x=x0+BOARD_X[i]-2;y=248
    return image.crop((x+2,y+2,x+22,y+23)),image.crop((x+2,y+23,x+15,y+34))


def feature(image,t,f,i):
    rank,suit=regions(image,t,f,i)
    if f=='board' and highlighted(image,t):
        alternate=showdown_regions(image,t,i)
        if alternate is None:return None,None,None,False
        rank,suit=alternate
    if f=='board' and felt(rank)>.85 and felt(suit)>.85:return None,None,None,True
    a,sig=soft_ink(rank);b,_=soft_ink(suit)
    return a,b,sig,False


def distance(a,b):
    a=np.frombuffer(a,np.uint8).astype(np.float32);b=np.frombuffer(b,np.uint8).astype(np.float32)
    return float(np.abs(a-b).sum()/max(255,np.maximum(a,b).sum()))


def train(examples):
    bank={r:[] for r in RANKS}
    for image,t,f,cards in examples:
        if detect(image,t)!='suprema' or f not in ('hero','board') or type(cards) is not list or len(cards) not in ((5,) if f=='hero' else (0,3,4,5)) or any(type(c) is not str or len(c)!=2 or c[0] not in RANKS or c[1] not in SUITS for c in cards) or len(set(cards))!=len(cards):raise ValueError('Invalid calibration')
        for i,c in enumerate(cards):
            a,b,sig,empty=feature(image,t,f,i)
            if a==b==c[1] and sig is not None and not empty:
                row=(*sig,f)
                if row not in bank[c[0]] and len(bank[c[0]])<128:bank[c[0]].append(row)
    if any(not v for v in bank.values()):raise ValueError('Missing rank templates')
    return bank


def classify(image,t,f,i,bank):
    a,b,sig,empty=feature(image,t,f,i)
    out={'card':None,'rank':None,'rank_color':a,'suit_color':b,'status':'uncertain','distance':None,'margin':None}
    if empty:out['status']='felt_empty_candidate';return out
    if a is None or a!=b or sig is None:return out
    g,aspect=sig
    scores=sorted((min(distance(g,k)+.15*abs(aspect-ak)+(.06 if f!=fk else 0) for k,ak,fk in vv),r) for r,vv in bank.items() if vv)
    if len(scores)<2:return out
    d,r=scores[0];gap=scores[1][0]-d;out.update(rank=r,distance=d,margin=gap)
    if d<.30 and gap>.075:out.update(card=r+a,status='candidate_unverified')
    return out


def observe(image,t,bank):
    from plo5_suprema_cards import observe as base
    return base(image,t,bank,slot_reader=classify)


PROFILE='suprema-soft-1504x696-v2'


def load_bank(path):
    import json,math
    from pathlib import Path
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=2*1024**2:raise ValueError('Invalid soft bank file')
    raw=json.loads(p.read_text(encoding='utf-8'))
    if type(raw) is not dict or set(raw)!={'profile','templates'} or raw['profile']!=PROFILE:raise ValueError('Wrong Suprema soft bank profile')
    rows=raw['templates']
    if type(rows) is not dict or set(rows)!=set(RANKS):raise ValueError('Missing rank templates')
    result={}
    for rank,items in rows.items():
        if type(items) is not list or not 1<=len(items)<=128:raise ValueError('Invalid template count')
        result[rank]=[]
        for item in items:
            if type(item) is not list or len(item)!=3:raise ValueError('Invalid template')
            g,a,f=item
            if type(g) is not str or len(g)!=960 or type(a) not in (float,int) or not math.isfinite(a) or not .1<=a<=10 or f not in ('hero','board'):raise ValueError('Invalid template')
            pixels=bytes.fromhex(g)
            if len(pixels)!=480:raise ValueError('Invalid template mask')
            result[rank].append((pixels,a,f))
    return result
