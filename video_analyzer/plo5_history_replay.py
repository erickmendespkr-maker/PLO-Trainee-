"""Strict offline PokerStars-style USD PLO5 hand replay. No DriveHUD DB access.
Only declared records with supported grammar, full showdown ranks or fold endings.
Rake is observed in summary, never guessed from a room preset.
"""
import re
from fractions import Fraction
from plo5_pre_gto_context import ORDERS, cards, need, integer
from plo5_reconstruct_ledger import replay

M=r'\$([0-9]+(?:\.[0-9]{1,2})?)'
HEADER=re.compile(r'^PokerStars Hand #(\d+): (?:5 Card Omaha|Omaha 5 Cards) Pot Limit \('+M+'/'+M+r' USD\)(?: - .*)?$',re.I)
TABLE=re.compile(r"^Table '.+' (?:[2-6]-max) Seat #(\d+) is the button$")
SEAT=re.compile(r'^Seat (\d+): (.+) \('+M+r' in chips\)$')
TOTAL=re.compile(r'^Total pot '+M+r' \| Rake '+M+r'$')
RETURN=re.compile(r'^Uncalled bet \('+M+r'\) returned to (.+)$')
COLLECT=re.compile(r'^(.+) collected '+M+r' from (?:pot|main pot|side pot(?:-\d+)?)$')


def money(s):
    whole,_,frac=s.partition('.');return integer(int(whole)*100+int((frac+'00')[:2]))


def reconstruct(record):
    lines=record['raw'].splitlines();m=HEADER.fullmatch(lines[0]);need(m is not None,'UNSUPPORTED_HEADER')
    ident,sb,bb=m.groups();sb,bb=money(sb),money(bb)
    need(ident==record['id'],'ID mismatch');need(len(lines)<=1024,'Too many lines')
    need(len(lines)>2,'Missing table');t=TABLE.fullmatch(lines[1]);need(t is not None,'UNSUPPORTED_TABLE')
    button=int(t[1]);seat={};i=2
    while i<len(lines) and (m:=SEAT.fullmatch(lines[i])):
        n,name,amount=m.groups();n=int(n);need(1<=n<=6 and n not in seat and name not in [x[0] for x in seat.values()],'Duplicate seat')
        seat[n]=(name,money(amount));i+=1
    need(len(seat) in ORDERS and button in seat,'Invalid seat roster')
    physical=sorted(seat);k=physical.index(button);after=physical[k+1:]+physical[:k+1]
    order=ORDERS[len(seat)]
    # HU button is SB; multiway seats clockwise from button are SB,BB,...,BTN.
    positions=('BB','SB') if len(seat)==2 else ('SB','BB',*order[:-2])
    names={seat[n][0]:p for n,p in zip(after,positions)};stacks={names[name]:v for name,v in seat.values()}
    paid={p:0 for p in order};total=paid.copy();known={};events=[];board=[];awards=paid.copy();returns=paid.copy();blindset=set();phase='blinds';summary=None;returned=False;shown=False;dealt=False
    def payment(p,v):
        need(v>0 and total[p]+v<=stacks[p],'Invalid payment');paid[p]+=v;total[p]+=v
    for line in lines[i:]:
        if not line:continue
        if phase=='summary':
            m=TOTAL.fullmatch(line)
            if m:
                need(summary is None,'Duplicate summary');summary=tuple(map(money,m.groups()));continue
            if line.startswith('Board ['):
                need(line=='Board ['+' '.join(board)+']','Summary board mismatch');continue
            # Seat summary lines are redundant annotations, not source of payouts.
            if re.fullmatch(r'Seat \d+: .+',line):continue
            raise ValueError('UNSUPPORTED_SUMMARY_LINE')
        if line=='*** HOLE CARDS ***':
            need(phase=='blinds' and blindset=={'SB','BB'},'Missing blinds');phase='preflop';continue
        if line=='*** SHOW DOWN ***':
            need(phase in ('preflop','flop','turn','river') and dealt,'Invalid showdown');phase='showdown';shown=True;continue
        if line=='*** SUMMARY ***':
            need(phase!='blinds' and dealt,'Invalid summary');phase='summary';continue
        m=re.fullmatch(r'Dealt to (.+) \[([^\]]+)\]',line)
        if m:
            name,h=m.groups();need(phase=='preflop' and not dealt and not events and name==record['hero'] and name in names,'Unexpected hero deal')
            known[names[name]]=cards(h.split());need(known[names[name]]==record['holding'],'Hero holding mismatch');dealt=True;continue
        m=re.fullmatch(r'\*\*\* (FLOP|TURN|RIVER) \*\*\* \[([^\]]+)\](?: \[([^\]]+)\])?',line)
        if m:
            st,a,b=m.groups();want={'FLOP':('preflop',0),'TURN':('flop',3),'RIVER':('turn',4)}[st]
            need((phase,len(board))==want and dealt and not any(awards.values()),'Unexpected street')
            if st=='FLOP':need(b is None and len(a.split())==3,'Invalid flop');new=a.split()
            else:need(a.split()==board and b is not None and len(b.split())==1,'Invalid board prefix');new=b.split()
            board+=new;events.append(dict(cards=new));paid={p:0 for p in order};phase=st.lower();continue
        m=RETURN.fullmatch(line)
        if m:
            v,name=m.groups();need(phase not in ('blinds','summary') and name in names and not returned and not any(awards.values()),'Invalid return')
            returns[names[name]]=money(v);returned=True;continue
        m=COLLECT.fullmatch(line)
        if m:
            name,v=m.groups();need(name in names and dealt and phase!='blinds','Invalid payout');awards[names[name]]+=money(v);continue
        # Identify names by exact prefix; ambiguity is rejected, never guessed.
        matches=[name for name in names if line.startswith(name+': ')]
        need(len(matches)==1,'UNSUPPORTED_LINE');name=matches[0];p=names[name];a=line[len(name)+2:]
        m=re.fullmatch(r'posts (small|big) blind '+M,a)
        if m:
            kind,v=m.groups();v=money(v);need(phase=='blinds' and p==('SB' if kind=='small' else 'BB') and p not in blindset and v==(sb if p=='SB' else bb),'Invalid blind')
            payment(p,v);blindset.add(p);continue
        m=re.fullmatch(r'shows \[([^\]]+)\](?: \(.+\))?',a)
        if m:
            need(shown and phase=='showdown','Show outside showdown');h=cards(m[1].split());need(p not in known or known[p]==h,'Holding mismatch');known[p]=h;continue
        need(phase in ('preflop','flop','turn','river') and dealt and not returned and not any(awards.values()),'Action outside betting')
        allin=a.endswith(' and is all-in');a=a.removesuffix(' and is all-in')
        if a in ('folds','checks'):act={'folds':'fold','checks':'check'}[a];v=0
        elif (m:=re.fullmatch(r'(calls|bets) '+M,a)):
            act={'calls':'call','bets':'bet'}[m[1]];v=money(m[2])
        elif (m:=re.fullmatch(r'raises '+M+r' to '+M,a)):
            increment,to=map(money,m.groups());need(to-max(paid.values())==increment,'Raise increment mismatch');act='raise';v=to-paid[p]
        else:raise ValueError('UNSUPPORTED_ACTION')
        if v:payment(p,v)
        need(not allin or total[p]==stacks[p],'All-in mismatch')
        events.append(dict(position=p,action=act,amount=v))
    need(phase=='summary' and summary is not None,'Missing summary totals')
    # Replay gross zero-rake settlement; observed rake allocation is not inferred.
    r=replay(stacks,sb,bb,events,known,rake_bps=0,rake_cap=0,rake_on_fold=False)
    gross,rake=summary
    need(r['contributions']==total and r['returned']==returns,'Contribution/return mismatch')
    need(gross==sum(total.values())-sum(returns.values()) and 0<=rake<=gross,'Summary pot mismatch')
    need(sum(awards.values())+rake==gross,'Award conservation mismatch')
    need(all(awards[p]<=r['awards'][p] for p in order),'Award eligibility mismatch')
    hero=names[record['hero']];net={p:awards[p]+returns[p]-total[p] for p in order}
    need(sum(net.values())==-rake,'Net conservation mismatch')
    decisions=[]
    for e in r['history']:
        if e.get('position')==hero:
            odds=Fraction(e['amount'],e['pot_after']) if e['action']=='call' else None
            decisions.append(dict(e,pot_odds_gross=None if odds is None else [odds.numerator,odds.denominator]))
    return dict(status='CONSISTENT_TEXT_REPLAY',id=ident,positions=names,hero_position=hero,stacks_cents=stacks,bb_cents=bb,board=board,events=events,contributions_cents=total,awards_cents=awards,returns_cents=returns,rake_cents=rake,net_cents=net,hero_net_bb=float(Fraction(net[hero],bb)),hero_decisions=decisions,rebuy_observed=False,rake_allocation_verified=False,source_truth_verified=False,strategy_authorized=False)
