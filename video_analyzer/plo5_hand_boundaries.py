"""Conservative PLO5 visual state transitions from offline mixed-video observations."""
from fractions import Fraction
from plo5_card_review import valid
from plo5_seat_candidates import SEATS

STREETS={0:'preflop',3:'flop',4:'turn',5:'river'}
PROFILES={'suprema-1504x696-v1','suprema-soft-1504x696-v2'}


def snapshot(c,s):
    p=c['platform'];h=c['hero_cards'];b=c['board_cards']
    if (c['table_id']!=s['table_id'] or p!=s['platform'] or p not in ('pppoker','suprema')
        or c.get('variant')!=5 or c.get('cards_verified') is not False or s.get('positions_verified') is not False
        or (p=='suprema' and c.get('rank_profile') not in PROFILES)
        or s.get('hero_seat_candidate')!='hero_bottom' or s.get('dealer_seat_candidate') not in SEATS
        or not valid(h,(5,)) or not valid(b,(0,3,4,5)) or set(h)&set(b)):return None
    return {'platform':p,'rank_profile':c.get('rank_profile'),'hero_cards':sorted(h),'board':list(b),'dealer':s['dealer_seat_candidate'],'street':STREETS[len(b)]}


def transition(a,b):
    if (a['platform'],a['rank_profile'])!=(b['platform'],b['rank_profile']):return 'profile_change'
    same_hero=a['hero_cards']==b['hero_cards'];same_dealer=a['dealer']==b['dealer'];old,new=a['board'],b['board']
    if same_hero and same_dealer and len(new)>len(old) and new[:len(old)]==old:
        return 'street_advance' if (len(old),len(new)) in ((0,3),(3,4),(4,5)) else 'street_skip'
    if not same_hero and not same_dealer and not new:return 'new_hand_boundary'
    return 'unresolved_state_change'


def analyze(frames):
    """Require adjacent seconds, complete observations and two samples on each side.
    Unknown observations split runs. A bounded bracket may mark a possible new
    hand but never joins the runs, certifies hand identity or infers settlement.
    """
    previous=None;seen=set();active={};pending={};runs=[];links=[];brackets=[];breaks=[]
    for f in frames:
        pts=Fraction(f['pts']);file=f['file']
        if file in seen or (previous is not None and pts<=previous):raise ValueError('Duplicate or unordered frames')
        seen.add(file);contiguous=previous is not None and int(pts//1)-int(previous//1)==1 and 0<pts-previous<=Fraction(3,2)
        if not contiguous:
            if previous is not None:
                for t,old in active.items():breaks.append({'table_id':t,'last':old['last'],'next':{'file':file,'pts':str(pts)},'reason':'source_gap'})
            active.clear();pending.clear()
        previous=pts
        c={r['table_id']:r for r in f['cards']};s={r['table_id']:r for r in f['seats']}
        if len(f['cards'])!=4 or len(f['seats'])!=4 or set(c)!=set(s) or set(c)!={1,2,3,4}:raise ValueError('Incomplete frame roster')
        for t in range(1,5):
            state=snapshot(c[t],s[t]);old=active.pop(t,None);ref={'file':file,'pts':str(pts)}
            if state is None:
                if old:
                    breaks.append({'table_id':t,'last':old['last'],'next':ref,'reason':'uncertain_observation'})
                    pending[t]=old
                q=pending.get(t)
                # An ambiguous read is not a gap in the source. Keep only a bounded,
                # same-platform bracket; never join the old and new hands.
                if q and (c[t]['platform']!=q['state']['platform'] or s[t]['platform']!=q['state']['platform'] or c[t].get('rank_profile')!=q['state']['rank_profile'] or pts-Fraction(q['last']['pts'])>15):pending.pop(t,None)
                continue
            if old is not None and old['state']==state:
                old['last']=ref;old['samples']+=1;active[t]=old;continue
            run={'run_id':len(runs)+1,'table_id':t,'state':state,'first':ref,'last':ref,'samples':1,'hand_verified':False};runs.append(run);active[t]=run
            if old is not None:links.append((old,run))
            else:
                q=pending.pop(t,None)
                if q and pts-Fraction(q['last']['pts'])<=15 and transition(q['state'],state)=='new_hand_boundary':brackets.append((q,run))
    edges=[]
    for a,b in links:
        kind=transition(a['state'],b['state']);supported=a['samples']>=2 and b['samples']>=2
        edges.append({'table_id':a['table_id'],'before_run':a['run_id'],'after_run':b['run_id'],'before':a['last'],'after':b['first'],
                      'transition_candidate':kind,'repeated_both_sides':supported,
                      'status':'REPEATED_VISUAL_TRANSITION_CANDIDATE' if supported and kind in ('street_advance','new_hand_boundary') else 'UNRESOLVED_TRANSITION',
                      'boundary_verified':False,'hand_verified':False,'action_verified':False,'financial_result_verified':False,'strategy_authorized':False})
    intervals=[{'table_id':a['table_id'],'before_run':a['run_id'],'after_run':b['run_id'],'last_old_state':a['last'],'first_new_state':b['first'],'status':'POSSIBLE_NEW_HAND_INTERVAL','boundary_verified':False,'hand_verified':False,'financial_result_verified':False,'strategy_authorized':False} for a,b in brackets if a['samples']>=2 and b['samples']>=2]
    return {'status':'VISUAL_HAND_TRANSITIONS_ONLY','runs':runs,'transitions':edges,'possible_new_hand_intervals':intervals,'continuity_breaks':breaks,'hands_reconstructed':False,'boundaries_verified':False}
