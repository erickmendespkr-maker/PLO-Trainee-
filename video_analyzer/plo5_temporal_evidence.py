"""Offline temporal gates for observed PLO5 stack/pot/label candidates."""
from collections import Counter
from fractions import Fraction
from plo5_pre_gto_context import need
from plo5_reconstruction_candidates import collect, money, state
from plo5_seat_evidence import SEATS


def inspect(frames):
    # Reuse existing roster, timestamps, cards and money validation.
    collect(frames)
    previous={};counts=Counter();intervals=[]
    for f in frames:
        pts=Fraction(f['pts']);by={(r['table_id'],r['field']):r for r in f['observations']}
        for c in f.get('cards',[]):
            t=c['table_id'];old=previous.pop(t,None);e=c.get('seat_evidence')
            if not e or not c['platform']:continue
            need(e['table_id']==t and e['platform']==c['platform'] and [s['seat'] for s in e['seats']]==list(SEATS),'Invalid seat roster')
            need(all(e.get(k) is False for k in ('positions_verified','actions_verified','financial_result_verified')),'Unexpected verification')
            st={s['seat']:money(s['stack']['candidate']) for s in e['seats']};labels={s['seat']:s['action']['candidate'] for s in e['seats']}
            d=e['dealer']['seat'];need(d is None or d in SEATS,'Invalid dealer')
            pot=money(by[t,'pot']['value_bb']);hero=money(by[t,'stack']['value_bb']);cards=state(c)
            now=dict(file=f['file'],pts=pts,platform=c['platform'],profile=c.get('rank_profile'),cards=cards,stacks=st,labels=labels,dealer=d,pot=pot,hero=hero)
            previous[t]=now
            if old is None:continue
            flags=[];delta={s:str(st[s]-old['stacks'][s]) for s in SEATS if st[s] is not None and old['stacks'][s] is not None}
            pd=None if pot is None or old['pot'] is None else str(pot-old['pot'])
            if not (0<pts-old['pts']<=Fraction(3,2) and pts//1-old['pts']//1==1):status='GAP'
            elif (now['platform'],now['profile'])!=(old['platform'],old['profile']):status='PROFILE_CHANGE'
            elif cards is None or old['cards'] is None:status='CARD_CONTINUITY_UNKNOWN'
            elif cards[0]!=old['cards'][0] or cards[1][:len(old['cards'][1])]!=old['cards'][1]:status='HAND_BOUNDARY_OR_CARD_CONFLICT'
            elif d is None or old['dealer'] is None or d!=old['dealer']:status='DEALER_CONTINUITY_UNKNOWN'
            elif len(cards[1])!=len(old['cards'][1]):status='STREET_ADVANCE_CANDIDATE'
            else:
                if len(delta)!=6 or pd is None:flags.append('INCOMPLETE_STACK_OR_POT')
                if hero is None or old['hero'] is None or hero!=st['hero_bottom'] or old['hero']!=old['stacks']['hero_bottom']:flags.append('HERO_STACK_NOT_CORROBORATED')
                if any(st[s]>old['stacks'][s] for s in delta):flags.append('STACK_INCREASE_UNRESOLVED')
                if pd is not None and len(delta)==6 and pot-old['pot']!=sum(old['stacks'][s]-st[s] for s in SEATS):flags.append('DISPLAY_NOT_CONSERVED')
                if flags:status='SAME_STREET_BLOCKED'
                elif any(st[s]!=old['stacks'][s] for s in SEATS):status='CONSISTENT_DISPLAY_DELTAS'
                else:status='UNCHANGED_DISPLAYS'
            # Labels can repeat or disappear; never infer actions across uncertain intervals.
            label_changes={s:[old['labels'][s],labels[s]] for s in SEATS if old['labels'][s]!=labels[s]}
            counts[status]+=1
            intervals.append(dict(table_id=t,before_file=old['file'],after_file=now['file'],before_pts=str(old['pts']),after_pts=str(pts),status=status,blockers=flags,stack_display_deltas_bb=delta,pot_display_delta_bb=pd,label_changes=label_changes,action_verified=False,financial_result_verified=False))
    return dict(status='TEMPORAL_CANDIDATES_ONLY',counts=dict(sorted(counts.items())),intervals=intervals,positions_verified=False,hands_reconstructed=False,financial_result_verified=False,strategy_authorized=False)
