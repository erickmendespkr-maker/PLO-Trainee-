"""Conservative temporal preflop roster candidates, never verified positions."""
from fractions import Fraction
from plo5_card_review import valid
from plo5_seat_candidates import SEATS, conditional_positions

OPP=set(SEATS)-{'hero_bottom'}
PROFILES={'suprema-1504x696-v1','suprema-soft-1504x696-v2'}


def snapshot(card,seat):
    t=card['table_id'];p=card['platform']
    if (seat['table_id']!=t or seat['platform']!=p or card.get('variant')!=5
        or card.get('cards_verified') is not False or seat.get('positions_verified') is not False
        or seat.get('dealt_roster_verified') is not False
        or p not in ('pppoker','suprema') or (p=='suprema' and card.get('rank_profile') not in PROFILES)
        or not valid(card['hero_cards'],(5,)) or card['board_cards']!=[]
        or seat['hero_seat_candidate']!='hero_bottom' or seat['dealer_seat_candidate'] not in SEATS):return None
    rows=seat['opponents']
    if len(rows)!=5 or {q['seat'] for q in rows}!=OPP:return None
    if any(q.get('dealt_verified') is not False or q['status'] not in ('card_backs_visible_candidate','explicit_empty_marker_candidate') for q in rows):return None
    dealt=['hero_bottom']+[q['seat'] for q in rows if q['status']=='card_backs_visible_candidate']
    empty=[q['seat'] for q in rows if q['status']=='explicit_empty_marker_candidate']
    dealer=seat['dealer_seat_candidate']
    positions=conditional_positions(dealer,dealt,standard_blinds=True)
    if positions is None:return None
    return {'platform':p,'rank_profile':card.get('rank_profile'),'hero_cards':sorted(card['hero_cards']),
            'dealer':dealer,'visible_dealt_seats':[s for s in SEATS if s in dealt],
            'explicit_empty_seats':[s for s in SEATS if s in empty],
            'positions_if_standard_blinds_and_full_roster':positions}


def candidates(frames):
    previous=None;state={};seen_files=set();out=[]
    for f in frames:
        pts=Fraction(f['pts']);file=f['file']
        if file in seen_files or (previous is not None and pts<=previous):raise ValueError('Unordered or duplicate samples')
        seen_files.add(file)
        contiguous=previous is not None and int(pts//1)-int(previous//1)==1 and 0<pts-previous<=Fraction(3,2)
        if not contiguous:state.clear()
        previous=pts
        cards={r['table_id']:r for r in f['cards']};seats={r['table_id']:r for r in f['seats']}
        if len(f['cards'])!=4 or len(f['seats'])!=4 or set(cards)!=set(seats) or set(cards)!={1,2,3,4}:raise ValueError('Incomplete frame roster')
        for t in range(1,5):
            current=snapshot(cards[t],seats[t]);old=state.pop(t,None)
            if current is None:continue
            if old is None or old['snapshot']!=current:
                state[t]={'snapshot':current,'first':{'file':file,'pts':str(pts)},'record':None};continue
            if old['record'] is None:
                row={'table_id':t,**current,'first':old['first'],'last':{'file':file,'pts':str(pts)},'samples':2,
                     'status':'REPEATED_PREFLOP_VISUAL_ROSTER_CANDIDATE','initial_deal_verified':False,
                     'dealt_roster_verified':False,'blinds_verified':False,'positions_verified':False,
                     'hero_position':None,'strategy_authorized':False}
                out.append(row);old['record']=row
            else:
                old['record']['last']={'file':file,'pts':str(pts)};old['record']['samples']+=1
            state[t]=old
    return out
