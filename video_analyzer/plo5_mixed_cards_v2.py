"""Offline mixed PPPoker/Suprema card candidates. No action or hand certification."""
from PIL import ImageChops, Image
from plo5_fourcolor_cards import (RANKS, SUITS, ink, signature, load_bank, regions as ppp_regions,
                                 feature as ppp_feature, MAX_RANK_DISTANCE, MIN_RANK_MARGIN)
from plo5_mixed_money import STARTS, detect
from plo5_singleflight import SingleFlight
from plo5_pre_gto_context import need


def sup_regions(image,t,f,i):
    # Original Suprema v1 geometry; highlighted board is handled separately.
    x=STARTS[t-1]+((225,242,258,275,292) if f=='hero' else (67,117,167,217,267))[i]
    y=546 if f=='hero' else 253
    if f=='hero':return image.crop((x+2,y+2,x+16,y+17)),image.crop((x+2,y+18,x+15,y+29))
    return image.crop((x+2,y+2,x+22,y+23)),image.crop((x+2,y+23,x+15,y+34))


def highlighted(image,t):
    x=STARTS[t-1]
    return sum(r>=145 and g>=110 and r>b+55 and g>b+45 for r,g,b in image.crop((x+65,245,x+316,299)).convert('RGB').getdata())>=35


def clean(mask,size):
    w,h=size;remaining={i for i,v in enumerate(mask) if v};parts=[]
    while remaining:
        seed=remaining.pop();part={seed};queue=[seed]
        while queue:
            j=queue.pop();x,y=j%w,j//w
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    u,v=x+dx,y+dy;k=v*w+u
                    if 0<=u<w and 0<=v<h and k in remaining:
                        remaining.remove(k);part.add(k);queue.append(k)
        parts.append(part)
    if not parts:return mask
    largest=max(map(len,parts));keep=set().union(*(p for p in parts if len(p)>=max(2,largest*.18)))
    return [i in keep for i in range(w*h)]


def sup_feature(image,t,f,i):
    rank,suit=sup_regions(image,t,f,i)
    a,mask,bg=ink(rank);b,_,bs=ink(suit)
    def felt(im):return sum(b>=g+10 and g>=r+5 and 30<=b<=145 for r,g,b in im.convert('RGB').getdata())/(im.width*im.height)
    return a,b,signature(clean(mask,rank.size),rank.size),bg,bs,f=='board' and felt(rank)>.85 and felt(suit)>.85


def feature(image,t,p,f,i):
    return ppp_feature(image,t,f,i) if p=='pppoker' else sup_feature(image,t,f,i)


def augment(bank,examples,platform):
    """Only explicitly labelled cards, no pseudo-labels. Caller separates holdout."""
    need(platform in ('pppoker','suprema'),'Unknown platform')
    out={r:list(bank.get(r,[])) for r in RANKS};accepted=0
    for image,t,f,cards in examples:
        need(detect(image,t)==platform and f in ('hero','board'),'Wrong calibration profile')
        need(type(cards) is list and len(cards) in ((5,) if f=='hero' else (0,3,4,5)) and len(set(cards))==len(cards) and all(len(c)==2 and c[0] in RANKS and c[1] in SUITS for c in cards),'Invalid label')
        if platform=='suprema' and f=='board' and highlighted(image,t):continue
        for i,c in enumerate(cards):
            a,b,sig,bg,bs,empty=feature(image,t,platform,f,i)
            if a==b==c[1] and sig is not None and bg>.25 and bs>.30 and not empty:
                row=(*sig,f)
                if row not in out[c[0]] and len(out[c[0]])<128:
                    out[c[0]].append(row);accepted+=1
    return out,accepted


class MixedCardReader:
    def __init__(self,ppp_path=None,suprema_path=None,capacity=1024,seat_reader=None):
        need(ppp_path is not None or suprema_path is not None,'At least one card bank required')
        self.banks={p:load_bank(path) for p,path in [('pppoker',ppp_path),('suprema',suprema_path)] if path is not None}
        self.cache=SingleFlight(capacity);self.seat_reader=seat_reader
        # Native Pillow C operations on tiny signatures instead of Python per-pixel loops.
        self.masks={p:{r:[(Image.frombytes('L',(20,24),g),sum(g),a,f) for g,a,f in rows] for r,rows in bank.items()} for p,bank in self.banks.items()}
    def classify(self,image,t,p,f,i):
        a,b,sig,bg,bs,empty=feature(image,t,p,f,i)
        out=dict(card=None,rank=None,suit_color=b,rank_color=a,status='uncertain',distance=None,margin=None)
        if empty:out['status']='felt_empty_candidate';return out
        if sig is None or a is None or a!=b or bg<=.25 or bs<=.30:return out
        g,aspect=sig;mass=sum(g);g=Image.frombytes('L',(20,24),g)
        def score(k,km,ak,fk):
            delta=sum(i*n for i,n in enumerate(ImageChops.difference(g,k).histogram()))
            return delta/max(255,(mass+km+delta)//2)+.15*abs(aspect-ak)+(.06 if f!=fk else 0)
        scores=sorted((min(score(k,km,ak,fk) for k,km,ak,fk in vv),r) for r,vv in self.masks[p].items())
        d,r=scores[0];gap=scores[1][0]-d;out.update(rank=r,distance=d,margin=gap)
        md,mm=(MAX_RANK_DISTANCE,MIN_RANK_MARGIN) if p=='pppoker' else (.20,.10)
        if d<md and gap>mm:out.update(card=r+a,status='candidate_unverified')
        return out
    def scan(self,image):
        need(image.mode=='RGB' and image.size==(1504,696),'Unsupported geometry');rows=[]
        for t in range(1,5):
            p=detect(image,t);out=dict(table_id=t,variant=5,platform=p,rank_profile=None,hero_cards=None,board_cards=None,hero_slots=[],board_slots=[],cards_verified=False)
            rows.append(out)
            if p not in self.banks:continue
            out['rank_profile']='pppoker-1504x696-recalibrated-v2' if p=='pppoker' else 'suprema-1504x696-v1'
            for f in ('hero','board'):
                slots=[]
                guard=p=='suprema' and f=='board' and highlighted(image,t)
                for i in range(5):
                    if guard:slots.append(dict(card=None,status='highlighted_board_unresolved'));continue
                    a,b=(ppp_regions if p=='pppoker' else sup_regions)(image,t,f,i)
                    key=(p,f,a.size,b.size,a.tobytes(),b.tobytes())
                    slots.append(self.cache.get(key,lambda:self.classify(image,t,p,f,i)))
                out[f+'_slots']=slots;cards=[r['card'] for r in slots if r['card'] is not None]
                if f=='hero' and len(cards)==5 and len(set(cards))==5:out['hero_cards']=cards
                if f=='board' and len(cards) in (0,3,4,5) and len(set(cards))==len(cards) and all(r['card'] for r in slots[:len(cards)]) and all(r['status']=='felt_empty_candidate' for r in slots[len(cards):]):out['board_cards']=cards
            if out['hero_cards'] is not None and out['board_cards'] is not None and set(out['hero_cards'])&set(out['board_cards']):out['hero_cards']=out['board_cards']=None
        if self.seat_reader is not None:
            for row,e in zip(rows,self.seat_reader.scan(image)):
                need(row['table_id']==e['table_id'] and row['platform']==e['platform'],'Seat layout conflict');row['seat_evidence']=e
        return rows
    def stats(self):
        result=self.cache.stats()
        if self.seat_reader is not None:result['seat_cache']=self.seat_reader.stats()
        return result
