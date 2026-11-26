"""Offline candidate recognition: PPPoker four-color deck at 1504x696.
Rank masks are calibrated from explicitly labelled recorded frames. Suit color is
checked in rank and symbol independently. No live assistance or verified hands.
"""
from PIL import Image
from plo5_mixed_money import STARTS, detect

RANKS='23456789TJQKA'
SUITS='cdhs'


def regions(image,table,field,i):
    if image.size!=(1504,696) or type(table) is not int or not 1<=table<=4 or field not in ('hero','board') or type(i) is not int or not 0<=i<5:
        raise ValueError('Unsupported card geometry')
    x=STARTS[table-1]+(214+16*i if field=='hero' else 75+45*i)
    y=562 if field=='hero' else 283
    if field=='hero':return image.crop((x+1,y+2,x+16,y+19)),image.crop((x+2,y+21,x+15,y+33))
    return image.crop((x+2,y+3,x+23,y+22)),image.crop((x+3,y+23,x+18,y+36))


def ink(image):
    rgb=list(image.convert('RGB').getdata());neutral=sorted(max(p) for p in rgb if max(p)-min(p)<25 and min(p)>55)
    ref=neutral[int(.7*(len(neutral)-1))] if neutral else 0
    masks={s:[] for s in SUITS}
    for r,g,b in rgb:
        m=max(r,g,b);n=min(r,g,b)
        masks['h'].append(r>g+18 and r>b+18 and g<r*.77)
        masks['c'].append(g>r+12 and g>b+12 and r<g*.83)
        masks['d'].append(b>r+18 and b>g+15 and r<b*.75)
        masks['s'].append(m-n<25 and m<ref*.55)
    scores=sorted(((sum(v),k) for k,v in masks.items()),reverse=True)
    n,s=scores[0];color=s if n>=4 and n>=1.6*scores[1][0] else None
    return color,masks[s],len(neutral)/len(rgb)


def signature(mask,size):
    im=Image.new('L',size);im.putdata([255 if v else 0 for v in mask]);bbox=im.getbbox()
    if not bbox or sum(mask)<4:return None
    w,h=bbox[2]-bbox[0],bbox[3]-bbox[1]
    return im.crop(bbox).resize((20,24),Image.Resampling.BILINEAR).tobytes(),w/h


def feature(image,table,field,i):
    rank,suit=regions(image,table,field,i);c,mask,bg=ink(rank);cs,_,bs=ink(suit)
    sig=signature(mask,rank.size)
    felt=lambda im:sum(g>=r+25 and g>=b+12 and 60<=g<=190 for r,g,b in im.convert('RGB').getdata())/(im.width*im.height)
    empty=felt(rank)>.85 and felt(suit)>.85
    return c,cs,sig,bg,bs,empty


def distance(a,b):
    return sum(abs(x-y) for x,y in zip(a,b))/max(255,sum(max(x,y) for x,y in zip(a,b)))


def train(examples):
    """Iterable of (RGB frame, table, field, list of explicitly labelled cards)."""
    bank={r:[] for r in RANKS}
    for image,t,f,cards in examples:
        if f not in ('hero','board') or type(cards) is not list or len(cards) not in ((5,) if f=='hero' else (0,3,4,5)) or any(type(c) is not str or len(c)!=2 or c[0] not in RANKS or c[1] not in SUITS for c in cards) or len(set(cards))!=len(cards):raise ValueError('Invalid declared cards')
        if detect(image,t)!='pppoker':raise ValueError('Unsupported platform in calibration')
        for i,c in enumerate(cards):
            a,b,sig,_,_,_=feature(image,t,f,i)
            if a==b==c[1] and sig is not None:
                row=(*sig,f)
                if row not in bank[c[0]] and len(bank[c[0]])<128:bank[c[0]].append(row)
    if any(not v for v in bank.values()):raise ValueError('Missing rank templates')
    return bank


def classify(image,t,f,i,bank):
    a,b,sig,bg,bs,empty=feature(image,t,f,i)
    out={'card':None,'rank':None,'suit_color':b,'rank_color':a,'status':'uncertain','distance':None,'margin':None}
    if empty:out['status']='felt_empty_candidate';return out
    if sig is None or a is None or a!=b or bg<=.25 or bs<=.3:return out
    g,aspect=sig
    scores=sorted((min(distance(g,k)+.15*abs(aspect-ak)+(.06 if f!=fk else 0) for k,ak,fk in vv),r) for r,vv in bank.items() if vv)
    if len(scores)<2:return out
    d,r=scores[0];gap=scores[1][0]-d;out.update(rank=r,distance=d,margin=gap)
    if d<.4 and gap>.06:out.update(card=r+a,status='candidate_unverified')
    return out


def observe(image,t,bank,*,slot_reader=None):
    if image.size!=(1504,696) or type(t) is not int or not 1<=t<=4:raise ValueError('Unsupported layout')
    out={'variant':5,'platform':detect(image,t),'hero_cards':None,'board_cards':None,'hero_slots':[],'board_slots':[],'cards_verified':False}
    if out['platform']!='pppoker':return out
    reader=classify if slot_reader is None else slot_reader
    for f in ('hero','board'):
        rows=[reader(image,t,f,i,bank) for i in range(5)];out[f+'_slots']=rows
        cards=[r['card'] for r in rows if r['card'] is not None]
        if f=='hero' and len(cards)==5 and len(set(cards))==5:out['hero_cards']=cards
        if f=='board' and len(cards) in (0,3,4,5) and len(set(cards))==len(cards) and all(r['card'] for r in rows[:len(cards)]) and all(r['status']=='felt_empty_candidate' for r in rows[len(cards):]):out['board_cards']=cards
    if out['hero_cards'] is not None and out['board_cards'] is not None and set(out['hero_cards'])&set(out['board_cards']):out['hero_cards']=out['board_cards']=None
    return out


def load_bank(path):
    import json
    import math
    from pathlib import Path
    p=Path(path)
    if not p.is_file() or p.is_symlink() or not 0<p.stat().st_size<=2*1024**2:raise ValueError('Invalid bank file')
    raw=json.loads(p.read_text(encoding='utf-8'))
    if type(raw) is not dict or set(raw)!=set(RANKS):raise ValueError('Missing rank templates')
    bank={}
    for r,rows in raw.items():
        if type(rows) is not list or not 1<=len(rows)<=128:raise ValueError('Invalid template count')
        bank[r]=[]
        for row in rows:
            if type(row) is not list or len(row)!=3:raise ValueError('Invalid template')
            g,a,f=row
            if type(g) is not str or len(g)!=960 or type(a) not in (int,float) or not math.isfinite(a) or not .1<=a<=10 or f not in ('hero','board'):raise ValueError('Invalid template')
            bank[r].append((bytes.fromhex(g),a,f))
            if len(bank[r][-1][0])!=480:raise ValueError('Invalid template mask')
    return bank


def main(argv=None):
    import argparse
    import hashlib
    import io
    import json
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('frame');p.add_argument('bank');a=p.parse_args(argv)
    raw=Path(a.frame).read_bytes();bank=load_bank(a.bank)
    with Image.open(io.BytesIO(raw)) as im:
        rgb=im.convert('RGB');tables=[{'table_id':i,**observe(rgb,i,bank)} for i in range(1,5)]
    print(json.dumps({'variant':5,'status':'CARD_CANDIDATES_ONLY','frame_sha256':hashlib.sha256(raw).hexdigest(),'tables':tables,'hands_reconstructed':False,'gto_solution':False,'cards_verified':False},ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
