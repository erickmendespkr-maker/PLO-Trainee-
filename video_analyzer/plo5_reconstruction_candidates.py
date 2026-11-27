"""Conservative offline evidence adapter for mixed-review frames, not a hand history."""
from fractions import Fraction
from decimal import Decimal, InvalidOperation
from plo5_pre_gto_context import need, cards
from plo5_post_gto_context import DECK


def money(v):
    if v is None:return None
    need(type(v) is str and 0<len(v)<=32,'Invalid money display')
    try:d=Decimal(v)
    except InvalidOperation as e:raise ValueError('Invalid money display') from e
    need(d.is_finite() and 0<=d<=10**12 and abs(d.as_tuple().exponent)<=6,'Invalid money display')
    return d


def state(row):
    if row is None:return None
    h,b=row.get('hero_cards'),row.get('board_cards')
    if h is None or b is None:return None
    h=cards(h);need(type(b) is list and len(b) in (0,3,4,5) and all(type(x) is str and x in DECK for x in b) and len(set(b+h))==len(b+h),'Invalid card candidate')
    return h,b


def collect(frames):
    need(type(frames) is list and len(frames)<=100000,'Invalid frame roster')
    prev=None;seen=set();last={};segments=[];changes=[];gaps=[];samples=0
    for frame in frames:
        t=Fraction(frame['pts']);f=frame['file'];need(t>=0 and (prev is None or t>prev) and type(f) is str and f not in seen,'Unordered frames');seen.add(f)
        contiguous=prev is not None and 0<t-prev<=Fraction(3,2) and t//1-prev//1==1
        if not contiguous:last.clear()
        prev=t
        observations=frame['observations'];need(type(observations) is list and len(observations)==8,'Incomplete money roster')
        fields={(r['table_id'],r['field']):r for r in observations}
        need(set(fields)=={(i,k) for i in range(1,5) for k in ('stack','pot')},'Duplicate or missing money field')
        cardrows=frame.get('cards');bycard={} if cardrows is None else {r['table_id']:r for r in cardrows}
        need(cardrows is None or len(cardrows)==4 and set(bycard)=={1,2,3,4},'Incomplete card roster')
        for i in range(1,5):
            a,b=fields[i,'stack'],fields[i,'pot'];p=a['platform'];samples+=1
            need(p==b['platform'] and p in ('pppoker','suprema',None),'Layout conflict')
            need(a['layout_candidate_active']==b['layout_candidate_active']==(p is not None),'Invalid visibility')
            old=last.pop(i,None)
            if p is None:
                if old:gaps.append(dict(table_id=i,file=f,reason='layout_absent'))
                continue
            x,y=money(a['value_bb']),money(b['value_bb']);c=bycard.get(i)
            need(c is None or c['platform']==p,'Card layout conflict')
            s=state(c);profile=c.get('rank_profile') if c else None
            if old and (p,profile)!=(old['platform'],old['profile']):
                gaps.append(dict(table_id=i,file=f,reason='profile_change'));old=None
            boundary='window_or_unknown_start'
            if old and s is not None and old['state'] is not None:
                oh,ob=old['state'];nh,nb=s
                if oh!=nh or nb[:len(ob)]!=ob:
                    boundary='possible_new_hand' if oh!=nh and not nb else 'card_conflict_or_reset';old=None
                elif len(nb)>len(ob):boundary='street_advance_candidate'
                else:boundary='same_card_state'
            elif old:boundary='unresolved_card_continuity'
            if old and old['state'] is not None and s is None:
                gaps.append(dict(table_id=i,file=f,reason='unknown_cards'));old=None
            # Money changes are display deltas, not betting payments or net results.
            if old:
                d={}
                for name,before,after in (('stack',old['stack'],x),('pot',old['pot'],y)):
                    if before is not None and after is not None and before!=after:d[name+'_delta_bb']=str(after-before)
                if d:changes.append(dict(table_id=i,platform=p,before_file=old['file'],after_file=f,before_pts=old['pts'],after_pts=str(t),**d,kind='UNRESOLVED_DISPLAY_CHANGE',net_bb=None,financial_result_verified=False))
            # Only complete compatible card observations form segments. Unknowns split.
            seg=None
            if s is not None:
                seg=old['segment'] if old and old['state'] is not None else None
                if seg is None:
                    seg=dict(table_id=i,platform=p,hero_cards=s[0],first_file=f,first_pts=str(t),observations=[],hand_verified=False,financial_result_verified=False);segments.append(seg)
                seg['observations'].append(dict(file=f,pts=str(t),board=s[1],transition=boundary))
            last[i]=dict(platform=p,profile=profile,state=s,stack=x,pot=y,file=f,pts=str(t),segment=seg)
    return dict(status='RECONSTRUCTION_EVIDENCE_ONLY',samples=samples,card_segments=segments,display_changes=changes,breaks=gaps,
                hands_reconstructed=False,positions_verified=False,financial_result_verified=False,strategy_authorized=False)


def main(argv=None):
    import argparse
    import json
    from pathlib import Path
    from hashlib import sha256
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('output');a=p.parse_args(argv)
    source=Path(a.manifest);out=Path(a.output)
    need(source.is_file() and not source.is_symlink() and 0<source.stat().st_size<=64*1024**2,'Invalid manifest')
    need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    raw=source.read_bytes();report=json.loads(raw)
    need(report.get('variant')==5 and report.get('hands_reconstructed') is False,'Unsupported manifest')
    result=dict(collect(report['frames']),manifest_sha256=sha256(raw).hexdigest(),source_sha256=report.get('source_sha256'))
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    return 0

if __name__=='__main__':raise SystemExit(main())
