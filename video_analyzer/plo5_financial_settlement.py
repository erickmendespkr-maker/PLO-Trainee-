"""PLO5 conditional multiway settlement in integer chips, no inferred poker results."""
from fractions import Fraction
from plo5_evaluator import evaluate
from offline_omaha_showdown import _cards
from plo5_leak_review import need, identifier


def chips(v, positive=False):
    need(type(v) is int and int(positive)<=v<=10**9,'Invalid integer chips')
    return v


def bb(v, blind):
    q=Fraction(v,blind)
    return {'numerator':q.numerator,'denominator':q.denominator}


def settle(review):
    """Complete declared accounting; external transfers occur AFTER settlement.

    Gross commitments include blinds and all bets; no ante/straddle inference.
    Rake, final stack, return and awards must be explicitly declared. No event
    order, bet legality or complete video hand is inferred from conservation.
    """
    need(type(review) is dict and set(review)=={'variant','reviewer','complete','hero_seat','bb_chips','seats','board','pots'},'Invalid settlement review')
    need(type(review['variant']) is int and review['variant']==5 and identifier(review['reviewer']) and review['complete'] is True,'Complete PLO5 review declaration required')
    blind=chips(review['bb_chips'],True);seats=review['seats'];need(type(seats) is list and 2<=len(seats)<=6,'Expected 2–6 dealt seats')
    rows={};all_cards=[];board=review['board']
    need(type(board) is list and len(board) in (0,3,4,5),'Invalid board');all_cards.extend(_cards(board,len(board)))
    for s in seats:
        need(type(s) is dict and set(s)=={'seat','before','after','committed','returned','rebuy','withdrawal','folded','cards'},'Invalid seat row')
        i=s['seat'];need(type(i) is int and 1<=i<=6 and i not in rows and type(s['folded']) is bool,'Invalid seat identity')
        for k in ('before','after','committed','returned','rebuy','withdrawal'):chips(s[k])
        need(s['committed']<=s['before'] and s['returned']<=s['committed'],'Commitment or return exceeds available chips')
        if s['cards'] is not None:all_cards.extend(_cards(s['cards'],5))
        rows[i]=s
    need(len(all_cards)==len(set(all_cards)),'Conflicting physical cards')
    hero=review['hero_seat'];need(type(hero) is int and hero in rows,'Invalid Hero seat')
    amounts=sorted((s['committed'] for s in seats),reverse=True)
    need(amounts[0]>0 and amounts[1]>0,'No contested pot')
    # Only the unmatched top commitment is returned; never count it as winnings.
    excess=amounts[0]-amounts[1]
    for s in seats:need(s['returned']==(excess if s['committed']==amounts[0] else 0),'Unmatched commitment return mismatch')
    net={i:s['committed']-s['returned'] for i,s in rows.items()}
    need(any(not s['folded'] for s in seats),'No remaining eligible seat')
    need(all(s['folded'] or net[i]==max(net.values()) or (s['committed']==s['before'] and s['returned']==0) for i,s in rows.items()),'Lower eligible contribution requires all-in')
    tiers=[];prev=0
    for cap in sorted(set(net.values())-{0}):
        contributors=sorted(i for i,v in net.items() if v>=cap)
        eligible=[i for i in contributors if not rows[i]['folded']]
        need(len(contributors)>=2 and eligible,'Uncontested or ineligible pot tier')
        tiers.append({'pot_id':'main' if not tiers else f'side_{len(tiers)}','cap_chips':cap,'gross_chips':(cap-prev)*len(contributors),'contributors':contributors,'eligible':eligible});prev=cap
    pots=review['pots'];need(type(pots) is list and len(pots)==len(tiers),'Pot tier count mismatch')
    received={i:0 for i in rows};results=[]
    for tier,p in zip(tiers,pots):
        need(type(p) is dict and set(p)=={'pot_id','rake','awards'} and p['pot_id']==tier['pot_id'],'Invalid pot review')
        rake=chips(p['rake']);distributable=tier['gross_chips']-rake;need(distributable>0,'Rake exceeds distributable pot')
        awards=p['awards'];need(type(awards) is list and 1<=len(awards)<=len(tier['eligible']),'Missing awards');paid={}
        for a in awards:
            need(type(a) is dict and set(a)=={'seat','chips'} and type(a['seat']) is int and a['seat'] in tier['eligible'] and a['seat'] not in paid,'Invalid award recipient')
            paid[a['seat']]=chips(a['chips'],True)
        need(sum(paid.values())==distributable,'Payout/rake conservation mismatch')
        eligible=tier['eligible'];winners=None
        if len(eligible)==1:winners=eligible
        elif len(board)==5 and all(rows[i]['cards'] is not None for i in eligible):
            ranks={i:evaluate(rows[i]['cards'],board)['rank'] for i in eligible};winners=[i for i in eligible if ranks[i]==max(ranks.values())]
        if winners is not None:
            # Exact equal split up to integer odd chips. If pot is smaller than
            # number of tied winners, zero awards are represented by omission.
            lo,odd=divmod(distributable,len(winners))
            need(set(paid)<=set(winners) and all(paid.get(i,0) in (lo,lo+bool(odd)) for i in winners),'Award disagrees with declared eligible showdown')
        for i,v in paid.items():received[i]+=v
        results.append({**tier,'rake_chips':rake,'awards':awards,'eligible_winners_from_declared_cards_or_fold':winners})
    balances=[]
    for i,s in sorted(rows.items()):
        pnl=received[i]-net[i];external=s['rebuy']-s['withdrawal'];expected=s['before']+pnl+external
        need(s['withdrawal']<=s['before']+pnl+s['rebuy'],'Withdrawal exceeds final available balance')
        balances.append({'seat':i,'net_committed_chips':net[i],'received_chips':received[i],'net_chips':pnl,'external_adjustment_chips':external,'residual_chips':s['after']-expected})
    ok=all(x['residual_chips']==0 for x in balances);hero_net=next(x['net_chips'] for x in balances if x['seat']==hero)
    need(sum(x['net_chips'] for x in balances)==-sum(p['rake_chips'] for p in results),'Global conservation failure')
    return {'variant':5,'status':'CONDITIONAL_SETTLEMENT' if ok else 'UNRESOLVED_BALANCE','pots':results,'balances':balances,'hero_net_chips':hero_net if ok else None,'hero_net_bb_fraction':bb(hero_net,blind) if ok else None,'hero_loss_over_30bb':hero_net < -30*blind if ok else None,'reviewer_authenticated':False,'financial_result_verified':False,'complete_hand_verified':False,'ev_loss_bb':None,'automatic_clip_selection_authorized':False}


def main(argv=None):
    import argparse
    from pathlib import Path
    from plo5_session_export import load,write
    from offline_video_ingest_probe import sha256
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('review');p.add_argument('output');a=p.parse_args(argv)
    review,h=load(a.review);result=settle(review);result['review_sha256']=h
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink() and sha256(a.review)==h,'New JSON output and unchanged review required');write(out,result);return 0


if __name__=='__main__':raise SystemExit(main())
