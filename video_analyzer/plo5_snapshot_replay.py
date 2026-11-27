"""Offline candidate replay across complete PLO5 display snapshots.
Explicit dealt roster, total-pot display semantics and start-of-hand seed are required.
An exact legal sequence within search bounds is not proof of a video action.
"""
from fractions import Fraction
from dataclasses import replace
from plo5_pre_gto_context import ORDERS, cards, integer, need
from plo5_post_gto_context import DECK
from plo5_reconstruction_candidates import money, state as card_state
from plo5_action_recovery import recover, UNKNOWN_ACTOR
from plo5_selective_review import action_key
from plo5_error_prints import bind, frame_index, active_table, stamp
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post

SEATS=('top','upper_right','lower_right','hero_bottom','lower_left','upper_left')
STREET={0:'preflop',3:'flop',4:'turn',5:'river'}


def positions(dealt,button):
    need(type(dealt) in (list,tuple) and len(dealt) in ORDERS and len(set(dealt))==len(dealt) and set(dealt)<=set(SEATS) and button in dealt,'Invalid dealt roster/button')
    ordered=[s for s in SEATS if s in dealt];i=ordered.index(button);cw=ordered[i+1:]+ordered[:i+1]
    order=ORDERS[len(cw)];labels=('BB','SB') if len(cw)==2 else ('SB','BB',*order[:-2])
    return dict(zip(cw,labels))


def chips(value,bb):
    d=money(value);need(d is not None,'Missing stack/pot')
    q=Fraction(d)*bb;need(q.denominator==1,'Display not representable in chip units')
    return integer(q.numerator)


def from_frame(frame,table,dealt,button,bb,*,actor=UNKNOWN_ACTOR,folded=None,street_boundary=False):
    """Use all *dealt* seat candidates, not six occupied/empty slots as players.
    Caller declares dealt roster, button, actor/folds and display pot semantics.
    """
    mapping=positions(dealt,button);integer(bb,1)
    rows=[x for x in frame.get('cards',[]) if x['table_id']==table]
    need(len(rows)==1,'Card evidence missing');c=rows[0];h=card_state(c);need(h is not None,'Incomplete card evidence')
    e=c.get('seat_evidence');need(type(e) is dict and e['table_id']==table and e['platform']==c['platform'] and e['dealer']['seat']==button,'Dealer evidence mismatch')
    seats=e['seats'];need([s['seat'] for s in seats]==list(SEATS),'Invalid seat evidence')
    st={s['seat']:chips(s['stack']['candidate'],bb) for s in seats if s['seat'] in mapping}
    obs=[x for x in frame['observations'] if x['table_id']==table];need(len(obs)==2 and {x['field'] for x in obs}=={'pot','stack'} and all(x['platform']==c['platform'] and x['layout_candidate_active'] is True for x in obs),'Invalid money roster')
    v={x['field']:chips(x['value_bb'],bb) for x in obs}
    need(st.get('hero_bottom')==v['stack'],'Hero stack not corroborated')
    out=dict(pts=frame['pts'],holding=h[0],board=h[1],remaining=st,pot=v['pot'],street_boundary=street_boundary)
    if actor is not UNKNOWN_ACTOR:out['actor']=actor
    if folded is not None:out['folded']=folded
    return out


def reveal(s,new):
    """Advance a closed betting state, preserving folded players and contributions."""
    if isinstance(s,pre.State):
        need(s.status in ('flop_transition','all_in_showdown') and len(new)==3,'Preflop not closed')
        order=('BB','SB') if len(s.order)==2 else ('SB','BB',*s.order[:-2]);ix=[s.order.index(p) for p in order];n=len(ix)
        rem=tuple(s.remaining[i] for i in ix);folded=tuple(s.folded[i] for i in ix)
        return post.prune(post.State(order,tuple(new),0,rem,(0,)*n,tuple(s.paid[i] for i in ix),folded,tuple(i for i in range(n) if not folded[i] and rem[i]),(-1,)*n,(s.bb,)*n,s.bb,s.bb))
    need(len(new)==1,'Invalid street advance')
    if s.status=='all_in_showdown':return replace(s,board=s.board+tuple(new),paid=(0,)*len(s.order))
    return post.advance(s,new[0])


def replay(manifest,seed,snapshots,*,max_actions=4,max_nodes=20000,max_gap=3):
    """Start with standard posted blinds and recover only unique legal intervals.
    Explicit street_boundary asserts the new board was observed before any new
    street action. Crossing a street without that anchor is not inferred.
    Stop at first ambiguity/gap; never promote candidate records to certificates.
    """
    need(type(seed) is dict and set(seed)=={'hand_id','table_id','dealt','button','initial','sb','bb','pot_includes_pending','holding'},'Invalid hand seed')
    need(seed['pot_includes_pending'] is True,'Display pot semantics must be declared')
    need(type(seed['hand_id']) is str and 0<len(seed['hand_id'])<=100,'Invalid hand ID')
    table=seed['table_id'];mapping=positions(seed['dealt'],seed['button']);need('hero_bottom' in mapping,'Hero not dealt')
    h=cards(seed['holding']);need(set(seed['initial'])==set(mapping),'Initial stack roster mismatch')
    s=pre.start({p:seed['initial'][k] for k,p in mapping.items()},seed['sb'],seed['bb']);board=[];events=[];records=[];intervals=[]
    frames=frame_index(manifest);need(type(snapshots) is list and 1<=len(snapshots)<=512,'Snapshot budget');need(type(max_gap) is int and 1<=max_gap<=30,'Gap budget')
    prev=None;blocked=None;platform=None
    for n,row in enumerate(snapshots):
        need(type(row) is dict and {'pts','holding','board','remaining','pot','street_boundary'}<=set(row)<={'pts','holding','board','remaining','pot','street_boundary','actor','folded'},'Invalid snapshot fields')
        pts=stamp(row['pts']);need(pts in frames and (prev is None or pts>prev),'Unbound snapshot PTS')
        need(cards(row['holding'])==h,'Hero holding changed');b=row['board'];need(type(b) is list and len(b) in STREET and all(c in DECK for c in b) and len(set(b+h))==len(b+h),'Invalid board')
        need(type(row['street_boundary']) is bool and set(row['remaining'])==set(mapping),'Invalid snapshot roster')
        target={p:integer(row['remaining'][k]) for k,p in mapping.items()};pot=integer(row['pot'])
        actor=row.get('actor',UNKNOWN_ACTOR);need(actor is UNKNOWN_ACTOR or actor is None or actor in mapping,'Invalid actor seat')
        want_actor=mapping[actor] if actor is not UNKNOWN_ACTOR and actor is not None else actor
        folded=row.get('folded');need(folded is None or type(folded) is dict and set(folded)==set(mapping) and all(type(v) is bool for v in folded.values()),'Invalid folded roster')
        fs=None if folded is None else {p:folded[k] for k,p in mapping.items()}
        observed_platform=active_table(frames[pts],table)
        if platform is not None and observed_platform!=platform:blocked='PLATFORM_CHANGE';break
        platform=observed_platform
        for c in frames[pts].get('cards',[]):
            if c['table_id']==table and c.get('hero_cards') is not None:
                need(cards(c['hero_cards'])==h,'Candidate holding conflicts with annotation')
        # Bind actual frame and candidate street to the declared hand before using it.
        probe=dict(hand_id=seed['hand_id'],decision_id='snapshot-'+str(n),street=STREET[len(b)])
        bind(manifest,probe,row['pts'],table,'before',index=frames)
        if prev is None:
            need(not b and not row['street_boundary'] and pot==s.pot and target==dict(zip(s.order,s.remaining)) and (want_actor is UNKNOWN_ACTOR or want_actor==s.actor) and (fs is None or not any(fs.values())),'First snapshot must match posted blinds')
            prev=pts;continue
        if pts-prev>max_gap:blocked='GAP';break
        if b[:len(board)]!=board or len(b) not in (len(board),3 if not board else len(board)+1):blocked='BOARD_CONFLICT';break
        advancing=b!=board
        if advancing and not row['street_boundary']:blocked='UNANCHORED_STREET_TRANSITION';break
        if not advancing and row['street_boundary']:blocked='UNEXPECTED_BOUNDARY';break
        if any(target[p]>s.remaining[i] for i,p in enumerate(s.order)):blocked='PAYOUT_OR_REBUY_UNRESOLVED';break
        # A board transition is accepted only from a previously closed state.
        # No assumption about which street a hidden payment belongs to.
        if advancing:
            try:next_state=reveal(s,b[len(board):])
            except ValueError:blocked='PRIOR_STREET_NOT_CLOSED';break
            if target!=dict(zip(next_state.order,next_state.remaining)) or pot!=next_state.pot or (want_actor is not UNKNOWN_ACTOR and next_state.actor!=want_actor) or (fs is not None and fs!=dict(zip(next_state.order,next_state.folded))):blocked='STREET_BOUNDARY_SNAPSHOT_MISMATCH';break
            events.append(dict(cards=b[len(board):]));board=list(b);s=next_state;intervals.append(dict(before_pts=str(prev),after_pts=str(pts),status='DECLARED_STREET_BOUNDARY',street=STREET[len(board)]));prev=pts;continue
        try:r=recover(s,target,pot,folded=fs,expected_actor=want_actor,max_actions=max_actions,max_nodes=max_nodes)
        except ValueError:blocked='DISPLAY_CONSERVATION_OR_STATE_MISMATCH';break
        intervals.append(dict(before_pts=str(prev),after_pts=str(pts),status=r['status'],visited=r['visited']))
        if r['status']!='UNIQUE_WITHIN_BOUNDS':blocked=r['status'];break
        engine=pre if isinstance(s,pre.State) else post
        for j,e in enumerate(r['candidates'][0]):
            if e['position']==mapping['hero_bottom']:
                bounds=engine.bounds(s);call=bounds['call_payment'];ident=str(len(events));d=dict(hand_id=seed['hand_id'],decision_id=ident,street=STREET[len(board)],action=action_key([e['action'],e['amount']]),pot_odds=call/(s.pot+call) if call else None,reconstruction_verified=False,strategy_verified=False,action_set_complete=False,action_ev_bounds={})
                # Only first recovered action has a before-frame at the interval start.
                # Later actions need separate anchors; don't reuse the first blindly.
                d['evidence']=bind(manifest,d,str(prev),table,'before',index=frames) if j==0 else None
                records.append(d)
            s=engine.step(s,e['position'],e['action'],e['amount']);events.append(e)
        prev=pts
    return dict(status=blocked or 'COMPATIBLE_DECLARED_SNAPSHOTS',positions=mapping,events=events,intervals=intervals,decision_records=records,last_pts=str(prev) if prev is not None else None,terminal=s.status,board=board,hand_complete_candidate=blocked is None and (s.status=='fold_terminal' or len(board)==5 and s.status in ('all_in_showdown','river_showdown')),hands_reconstructed=False,positions_verified=False,financial_result_verified=False,strategy_authorized=False)


def settlement(seed,result,holdings,observations,*,rake_bps,rake_cap,rake_on_fold):
    """Conditional reconciliation only; never infer a rebuy from stack increase."""
    from plo5_reconstruct_ledger import replay as ledger_replay,reconcile
    need(result['hand_complete_candidate'] is True and result['status']=='COMPATIBLE_DECLARED_SNAPSHOTS','Incomplete candidate')
    mapping=positions(seed['dealt'],seed['button']);need(result['positions']==mapping,'Position mismatch')
    need(type(holdings) is dict and set(holdings)<=set(mapping),'Invalid showdown holdings')
    hero=seed['holding'];need('hero_bottom' not in holdings or cards(holdings['hero_bottom'])==cards(hero),'Hero showdown mismatch')
    known={mapping[k]:v for k,v in dict(holdings,hero_bottom=hero).items()}
    r=ledger_replay({p:seed['initial'][k] for k,p in mapping.items()},seed['sb'],seed['bb'],result['events'],known,rake_bps=rake_bps,rake_cap=rake_cap,rake_on_fold=rake_on_fold)
    a=reconcile(r,**observations)
    return dict(status=a['status'],errors=a['errors'],rebuy_chips=a['rebuy_chips'],net_bb={p:str(v/seed['bb']) for p,v in a['net_chips'].items()} if a['net_chips'] is not None else None,financial_result_verified=False,strategy_authorized=False)
