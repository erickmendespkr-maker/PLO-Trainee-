"""Offline Suprema card candidates from a platform-specific labelled rank bank."""
from plo5_fourcolor_cards import RANKS, SUITS, distance, ink, signature
from plo5_suprema_suits import regions, felt, detect
from plo5_mixed_money import STARTS

MAX_DISTANCE=.20
MIN_MARGIN=.10


def clean(mask,size):
    """Keep substantial connected glyph components; remove isolated compression pixels."""
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


def highlighted(image,t):
    # Highlighted showdown cards can move vertically; do not assume normal ROIs.
    x=STARTS[t-1];pixels=image.crop((x+65,245,x+316,299)).convert('RGB').getdata()
    return sum(r>=145 and g>=110 and r>b+55 and g>b+45 for r,g,b in pixels)>=35


def feature(image,t,f,i):
    rank,suit=regions(image,t,f,i)
    if f=='board' and highlighted(image,t):
        return None,None,None,0,0,False
    a,mask,bg=ink(rank);b,_,bs=ink(suit)
    empty=f=='board' and felt(rank)>.85 and felt(suit)>.85
    return a,b,signature(clean(mask,rank.size),rank.size),bg,bs,empty


def train(examples):
    bank={r:[] for r in RANKS}
    for image,t,f,cards in examples:
        if f not in ('hero','board') or type(cards) is not list or len(cards) not in ((5,) if f=='hero' else (0,3,4,5)) or any(type(c) is not str or len(c)!=2 or c[0] not in RANKS or c[1] not in SUITS for c in cards) or len(set(cards))!=len(cards):
            raise ValueError('Invalid declared Suprema cards')
        if detect(image,t)!='suprema':raise ValueError('Unsupported platform')
        for i,c in enumerate(cards):
            a,b,sig,bg,bs,empty=feature(image,t,f,i)
            if a==b==c[1] and sig is not None and bg>.25 and bs>.30 and not empty:
                row=(*sig,f)
                if row not in bank[c[0]] and len(bank[c[0]])<128:bank[c[0]].append(row)
    if any(not v for v in bank.values()):raise ValueError('Missing Suprema rank classes')
    return bank


def classify(image,t,f,i,bank):
    a,b,sig,bg,bs,empty=feature(image,t,f,i)
    out={'card':None,'rank':None,'suit_color':b,'rank_color':a,'status':'uncertain','distance':None,'margin':None}
    if empty:out['status']='felt_empty_candidate';return out
    if sig is None or a is None or a!=b or bg<=.25 or bs<=.30:return out
    g,aspect=sig
    scores=sorted((min(distance(g,k)+.15*abs(aspect-ak)+(.06 if f!=fk else 0) for k,ak,fk in vv),r) for r,vv in bank.items() if vv)
    if len(scores)<2:return out
    d,r=scores[0];gap=scores[1][0]-d;out.update(rank=r,distance=d,margin=gap)
    if d<MAX_DISTANCE and gap>MIN_MARGIN:out.update(card=r+a,status='candidate_unverified')
    return out


def observe(image,t,bank,*,slot_reader=None):
    platform=detect(image,t)
    out={'variant':5,'platform':platform,'hero_cards':None,'board_cards':None,'hero_slots':[],'board_slots':[],'cards_verified':False}
    if platform!='suprema':return out
    reader=classify if slot_reader is None else slot_reader
    for f in ('hero','board'):
        rows=[reader(image,t,f,i,bank) for i in range(5)];out[f+'_slots']=rows
        cards=[r['card'] for r in rows if r['card'] is not None]
        if f=='hero' and len(cards)==5 and len(set(cards))==5:out['hero_cards']=cards
        if f=='board' and len(cards) in (0,3,4,5) and len(set(cards))==len(cards) and all(r['card'] for r in rows[:len(cards)]) and all(r['status']=='felt_empty_candidate' for r in rows[len(cards):]):out['board_cards']=cards
    if out['hero_cards'] is not None and out['board_cards'] is not None and set(out['hero_cards'])&set(out['board_cards']):out['hero_cards']=out['board_cards']=None
    return out
