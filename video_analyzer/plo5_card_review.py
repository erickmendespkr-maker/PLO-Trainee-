"""Cached four-color card candidates and conservative offline timeline grouping."""
from fractions import Fraction
from plo5_fourcolor_cards import classify, observe, regions, RANKS, SUITS
from plo5_singleflight import SingleFlight


class CardReader:
    def __init__(self,bank,capacity=1024,*,suprema_bank=None,suprema_soft_bank=None,card_codebook=None):
        if suprema_bank is not None and suprema_soft_bank is not None:
            raise ValueError("Conflicting Suprema profiles")
        self.bank=bank;self.suprema_bank=suprema_bank;self.suprema_soft_bank=suprema_soft_bank
        self.cache=SingleFlight(capacity);self.card_codebook=card_codebook

    def slot(self,image,t,f,i,bank):
        rank,suit=regions(image,t,f,i)
        # Key covers all pixels consumed by feature(), including empty-state checks.
        key=('pppoker',f,rank.size,suit.size,rank.convert('RGB').tobytes()+suit.convert('RGB').tobytes())
        def produce():
            if self.card_codebook is not None:
                from plo5_card_codes import read_slot
                candidate=read_slot(self.card_codebook,'pppoker-1504x696-card-v1',f,rank,suit)
                if candidate is not None:return candidate
            return classify(image,t,f,i,bank)
        return self.cache.get(key,produce)

    def suprema_slot(self,image,t,f,i,bank):
        from plo5_suprema_suits import regions as sup_regions
        from plo5_suprema_cards import classify as sup_classify, highlighted
        profile="suprema-1504x696-v1"
        if self.suprema_soft_bank is not None:
            from plo5_suprema_soft import classify as sup_classify, PROFILE as profile
        # Alternate showdown geometry reads outside the normal cache key; bypass cache.
        if self.suprema_soft_bank is not None and f=='board' and highlighted(image,t):
            return sup_classify(image,t,f,i,bank)
        rank,suit=sup_regions(image,t,f,i)
        # The showdown guard reads a wider board region, not just these glyphs.
        key=(profile,f,rank.size,suit.size,f=='board' and highlighted(image,t),rank.convert('RGB').tobytes()+suit.convert('RGB').tobytes())
        def produce():
            if self.card_codebook is not None:
                from plo5_card_codes import read_slot
                candidate=read_slot(self.card_codebook,profile+'-card-codes-v1',f,rank,suit,guard=not (f=='board' and highlighted(image,t)))
                if candidate is not None:return candidate
            return sup_classify(image,t,f,i,bank)
        return self.cache.get(key,produce)

    def scan(self,image):
        from plo5_mixed_money import detect
        from plo5_suprema_cards import observe as sup_observe
        rows=[]
        for t in range(1,5):
            platform=detect(image,t)
            if platform=='suprema' and self.suprema_soft_bank is not None:
                from plo5_suprema_soft import PROFILE
                r=sup_observe(image,t,self.suprema_soft_bank,slot_reader=self.suprema_slot)
                r['rank_profile']=PROFILE
            elif platform=='suprema' and self.suprema_bank is not None:
                r=sup_observe(image,t,self.suprema_bank,slot_reader=self.suprema_slot)
                r['rank_profile']='suprema-1504x696-v1'
            elif self.bank is not None:
                r=observe(image,t,self.bank,slot_reader=self.slot)
            else:
                r={'variant':5,'platform':platform,'hero_cards':None,'board_cards':None,'hero_slots':[],'board_slots':[],'cards_verified':False}
            rows.append({'table_id':t,**r})
        return rows


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
            if not (r['platform']=='pppoker' or r['platform']=='suprema' and r.get('rank_profile') in ('suprema-1504x696-v1','suprema-soft-1504x696-v2')) or not valid(h,(5,)) or not valid(b,(0,3,4,5)) or set(h)&set(b):
                if old:old['end_reason']='uncertain_or_unsupported'
                continue
            if old:
                prev=Fraction(old['last_pts'])
                contiguous=int(pts//1)-int(prev//1)==1 and 0<pts-prev<=Fraction(3,2)
                compatible=r['platform']==old['platform'] and r.get('rank_profile')==old['rank_profile'] and sorted(h)==old['hero_cards'] and b[:len(old['last_board'])]==old['last_board']
                if not contiguous or not compatible:
                    old['end_reason']='gap' if not contiguous else 'cards_changed_or_board_reset'
                    old=None
            if old is None:
                old={'candidate_id':f'table_{t:02d}_cards_{len(out)+1:05d}','table_id':t,'platform':r['platform'],'rank_profile':r.get('rank_profile'),'hero_cards':sorted(h),'first_pts':str(pts),'observations':[],'hand_verified':False,'financial_result_verified':False,'strategy_authorized':False,'end_reason':'end_of_window'}
                out.append(old)
            old['last_pts']=str(pts);old['last_board']=list(b)
            old['observations'].append({'file':file,'pts':str(pts),'board':list(b)})
            active[t]=old
        if seen!={1,2,3,4}:raise ValueError('Incomplete card roster')
    return out
