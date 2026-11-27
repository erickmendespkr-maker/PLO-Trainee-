"""Offline replay of declared PLO5 evidence; never certifies a video hand."""
from dataclasses import replace
from fractions import Fraction
from plo5_pre_gto_context import need, integer, cards
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post
from plo5_post_gto_context import DECK
from plo5_post_gto_multiway_ledger import settle
from offline_omaha_showdown import omaha_rank


def replay(stacks,sb,bb,events,holdings,*,rake_bps,rake_cap,rake_on_fold):
    """Events are declared incremental chips or public board reveals, not OCR labels.
    Full original contributions survive street changes and folds.
    """
    need(type(events) is list and len(events)<=512,'Invalid events')
    s=pre.start(stacks,sb,bb);board=();street='preflop';history=[]
    need(type(holdings) is dict and set(holdings)<=set(stacks),'Invalid holdings')
    known={p:cards(h) for p,h in holdings.items()};dead=[x for h in known.values() for x in h]
    need(len(dead)==len(set(dead)),'Duplicate private cards')
    for e in events:
        need(type(e) is dict,'Invalid event')
        if set(e)=={'cards'}:
            new=e['cards'];need(type(new) is list and len(new)==(3 if not board else 1) and len(board)<5,'Invalid reveal')
            need(all(type(x) is str and x in DECK and x not in dead and x not in board for x in new) and len(set(new))==len(new),'Card conflict')
            need(s.status in ('flop_transition','chance_transition','all_in_showdown'),'Betting not closed')
            board+=tuple(new);street={3:'flop',4:'turn',5:'river'}[len(board)]
            if isinstance(s,pre.State):
                order=('BB','SB') if len(s.order)==2 else tuple(p for p in ('SB','BB',*s.order) if p in s.order)
                order=tuple(dict.fromkeys(order));ix=[s.order.index(p) for p in order];n=len(ix)
                rem=tuple(s.remaining[i] for i in ix);folded=tuple(s.folded[i] for i in ix)
                s=post.prune(post.State(order,board,0,rem,(0,)*n,tuple(s.paid[i] for i in ix),folded,
                    tuple(i for i in range(n) if not folded[i] and rem[i]),(-1,)*n,(bb,)*n,bb,bb))
            elif s.status=='all_in_showdown':s=replace(s,board=board,paid=(0,)*len(s.order))
            else:s=post.advance(s,new[0])
            history.append(dict(street=street,cards=new,pot=s.pot));continue
        need(set(e)=={'position','action','amount'},'Invalid action event')
        p,a,v=e['position'],e['action'],integer(e['amount']);before=s.pot
        s=(pre.step if isinstance(s,pre.State) else post.step)(s,p,a,v)
        history.append(dict(e,street=street,pot_before=before,pot_after=s.pot,remaining=s.remaining[s.order.index(p)]))
    need(s.status in ('fold_terminal','all_in_showdown','river_showdown'),'INCOMPLETE_BETTING')
    paid=s.paid if isinstance(s,pre.State) else s.total_paid
    ranks=[None]*len(s.order)
    if len(s.active)>1:
        need(len(board)==5 and all(s.order[i] in known for i in s.active),'INCOMPLETE_SHOWDOWN')
        for i in s.active:ranks[i]=omaha_rank(known[s.order[i]],board)
    ledger=settle(0,paid,s.folded,ranks,rake_bps,rake_cap,rake_on_fold=rake_on_fold)
    def mapping(values):return {p:v for p,v in zip(s.order,values)}
    awards=mapping(ledger['awards']);returned=mapping(ledger['returned']);contributions=mapping(paid)
    final={p:Fraction(stacks[p]-contributions[p])+awards[p]+returned[p] for p in s.order}
    net={p:final[p]-stacks[p] for p in s.order}
    return dict(status='REPLAY_CONSISTENT_DECLARED_INPUT',board=list(board),history=history,contributions=contributions,
                awards=awards,returned=returned,rake=ledger['rake'],final_before_rebuy=final,net_chips=net,
                net_bb={p:v/bb for p,v in net.items()},layers=ledger['layers'],positions_declared=True,
                room_rules_verified=False,financial_result_verified=False,hands_reconstructed=False,strategy_authorized=False)


def reconcile(replayed,observed_awards,observed_returns,observed_rake,observed_before_rebuy,rebuy,observed_after_rebuy):
    """Check independent declared settlement and explicit external deposits.
    A matching total is necessary, not proof of correct observations.
    """
    expected=replayed['final_before_rebuy'];seats=set(expected)
    for values in (observed_awards,observed_returns,observed_before_rebuy,rebuy,observed_after_rebuy):
        need(type(values) is dict and set(values)==seats,'Incomplete settlement roster')
        for v in values.values():integer(v)
    integer(observed_rake)
    errors=[]
    for label,actual,want in (('award',observed_awards,replayed['awards']),('return',observed_returns,replayed['returned']),('before_rebuy',observed_before_rebuy,expected)):
        for p in sorted(seats):
            if actual[p]!=want[p]:errors.append(f'{label}:{p}')
    if observed_rake!=replayed['rake']:errors.append('rake')
    for p in sorted(seats):
        if observed_before_rebuy[p]+rebuy[p]!=observed_after_rebuy[p]:errors.append(f'after_rebuy:{p}')
    return dict(status='DECLARED_SETTLEMENT_MATCH' if not errors else 'SETTLEMENT_MISMATCH',errors=errors,
                rebuy_chips=dict(rebuy),net_chips=replayed['net_chips'] if not errors else None,
                financial_result_verified=False,strategy_authorized=False)
