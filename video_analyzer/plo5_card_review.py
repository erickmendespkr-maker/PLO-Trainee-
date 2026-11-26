"""Cached four-color card candidates and conservative offline timeline grouping."""
from fractions import Fraction
from plo5_fourcolor_cards import classify, observe, regions, RANKS, SUITS
from plo5_singleflight import SingleFlight


class CardReader:
    def __init__(self,bank,capacity=1024):
        self.bank=bank
        self.cache=SingleFlight(capacity)

    def slot(self,image,t,f,i,bank):
        rank,suit=regions(image,t,f,i)
        # Key covers all pixels consumed by feature(), including empty-state checks.
        key=(f,rank.size,suit.size,rank.convert('RGB').tobytes()+suit.convert('RGB').tobytes())
        return self.cache.get(key,lambda:classify(image,t,f,i,bank))

    def scan(self,image):
        return [{'table_id':t,**observe(image,t,self.bank,slot_reader=self.slot)} for t in range(1,5)]


def valid(cards,counts):
    return type(cards) is list and len(cards) in counts and all(type(c) is str and len(c)==2 and c[0] in RANKS and c[1] in SUITS for c in cards) and len(cards)==len(set(cards))


def segments(frames):
    """Group contiguous, mutually consistent observations, not reconstructed hands."""
    active={};out=[];previous=None;ids=set()
    for frame in frames:
        pts=Fraction(frame['pts']);file=frame['file']
        if previous is not None and pts<=previous or file in ids:
            raise ValueError('Duplicate or unordered frames')
        previous=pts;ids.add(file)
        tables=frame['cards'];seen=set()
        for r in tables:
            t=r['table_id']
            if type(t) is not int or not 1<=t<=4 or t in seen or r.get('variant')!=5 or r.get('cards_verified') is not False:
                raise ValueError('Invalid card observation roster')
            seen.add(t);old=active.pop(t,None);h,b=r['hero_cards'],r['board_cards']
            if r['platform']!='pppoker' or not valid(h,(5,)) or not valid(b,(0,3,4,5)) or set(h)&set(b):
                if old:old['end_reason']='uncertain_or_unsupported'
                continue
            if old:
                prev=Fraction(old['last_pts'])
                contiguous=int(pts//1)-int(prev//1)==1 and 0<pts-prev<=Fraction(3,2)
                compatible=sorted(h)==old['hero_cards'] and b[:len(old['last_board'])]==old['last_board']
                if not contiguous or not compatible:
                    old['end_reason']='gap' if not contiguous else 'cards_changed_or_board_reset'
                    old=None
            if old is None:
                old={'candidate_id':f'table_{t:02d}_cards_{len(out)+1:05d}','table_id':t,'hero_cards':sorted(h),'first_pts':str(pts),'observations':[],'hand_verified':False,'financial_result_verified':False,'strategy_authorized':False,'end_reason':'end_of_window'}
                out.append(old)
            old['last_pts']=str(pts);old['last_board']=list(b)
            old['observations'].append({'file':file,'pts':str(pts),'board':list(b)})
            active[t]=old
        if seen!={1,2,3,4}:raise ValueError('Incomplete card roster')
    return out
