"""Audit the integrated candidate without promoting it to a validated beta."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from plo5_pre_gto_context import need
from plo5_error_prints import frame_index, bind, stamp
from plo5_selective_review import VERSION, select, street_filter, identity
from plo5_terminal_bounds import prefix
from plo5_video_stream import digest
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post

KEYS=('coarse_frames','refined_frames','decoded_frames','table_observations','candidate_hands','candidate_decisions','selected_pending','errors','prints')


def load(root,relative):
    p=root/relative
    need(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root.resolve()) and 0<p.stat().st_size<=64*1024**2,'Invalid audit artifact')
    return json.loads(p.read_text('utf-8'))


def audit(source,folder):
    root=Path(folder);source=Path(source);need(root.is_dir() and not root.is_symlink() and source.is_file(),'Local report and video required')
    summary=load(root,'summary.json');h=digest(source)
    need(summary.get('version')=='plo5-integrated-candidate-v1' and summary.get('source_sha256')==h,'Source or report version mismatch')
    need(all(summary.get(k) is False for k in ('beta_ready','strategy_verified','drivehud_beta')),'Unexpected readiness claim')
    streets=street_filter(summary['streets']);tables=summary['tables'];need(type(tables) is list and 1<=len(tables)<=4 and len(set(tables))==len(tables) and all(type(t) is int and 1<=t<=4 for t in tables),'Invalid tables')
    rows=summary['windows'];need(type(rows) is list and 1<=len(rows)<=43200,'Invalid window roster');totals=Counter();previous=None;seen=set();ends=Counter();metrics_count=0
    for i,w in enumerate(rows,1):
        name=f'window_{i:05d}';a,n=w['start'],w['seconds'];need(w['window']==name and type(a) is int and a>=0 and type(n) is int and 2<=n<=60 and (previous is None or previous==a),'Invalid window sequence');previous=a+n
        v=load(root,name+'/candidates.json');m=v['observations'];need(m.get('source_sha256')==h and m.get('actions_verified') is False and m.get('strategy_authorized') is False and v.get('strategic_certification') is False,'Unexpected observation status');frames=frame_index(m);need(all(a<=p<a+n for p in frames),'Out-of-window observation')
        for f in frames.values():
            ids=[c['table_id'] for c in f['cards']];need(len(ids)==len(set(ids)) and set(ids)<=set(tables),'Unexpected table observation')
        hands=v['hands'];idx={x['seed']['hand_id']:x for x in hands};need(len(idx)==len(hands) and not seen&set(idx),'Duplicate candidate hands');seen.update(idx)
        for x in hands:
            need(x.get('hand_verified') is False and x['seed']['table_id'] in tables,'Unexpected hand verification');ends[x['end_reason']]+=1
        contract=v['decision_contract'];need(contract.get('version')==VERSION,'Invalid decision contract');records=contract['decisions'];sel=select(records,streets)
        need(not sel['errors'] and not sel['adequate_count'] and not sel['print_requests'],'Candidate selection cannot authorize errors')
        metrics={identity(x):x for x in v['metrics']};need(len(metrics)==len(v['metrics']),'Duplicate metrics')
        expected_metrics=set()
        for d in records:
            need(all(d.get(k) is False for k in ('reconstruction_verified','strategy_verified','action_set_complete')),'Unexpected verified decision')
            hand=idx[d['hand_id']];s,holding,actual=prefix(hand['seed'],hand['events'],int(d['decision_id']));board=[] if isinstance(s,pre.State) else list(s.board);street={0:'preflop',3:'flop',4:'turn',5:'river'}[len(board)];b=(pre if isinstance(s,pre.State) else post).bounds(s);call=b['call_payment'];odds=call/(s.pot+call) if call else None
            need(d['action']==actual and d['street']==street and d.get('pot_odds')==odds,'Decision math mismatch')
            if d.get('evidence') is not None:
                e=d['evidence'];need(e['table_id']==hand['seed']['table_id'],'Decision table mismatch');expected=bind(m,d,e['pts'],e['table_id'],e['phase'],index=frames);need(e==expected,'Decision frame binding mismatch')
            if street in streets:
                key=identity(d);expected_metrics.add(key);r=metrics[key]
                need(r['position']==s.actor and r['board']==board and r['pot_bb']==s.pot/s.bb and r['call_bb']==call/s.bb and r['pot_odds_gross']==odds,'Metric mismatch')
        need(set(metrics)==expected_metrics,'Metric roster mismatch');metrics_count+=len(metrics)
        cap=load(root,name+'/capture/manifest.json');rep=load(root,name+'/study/summary.json')
        need(cap.get('source_sha256')==h and cap.get('streets')==list(streets) and cap.get('unresolved')==sel['unresolved'] and cap.get('errors')==[] and cap.get('decision_prints')==[] and cap.get('unique_crops')==0,'Capture selection mismatch')
        need(rep.get('streets')==list(streets) and rep.get('unresolved')==len(sel['unresolved']) and rep.get('errors')==rep.get('adequate')==rep.get('unique_crops')==0 and rep.get('demo') is False,'Report selection mismatch')
        html=root/name/'study/index.html';need(html.is_file() and not html.is_symlink() and html.stat().st_size==rep['html_bytes'],'Report size mismatch');need(not any((root/name/'study/prints').iterdir()) and not list((root/name/'capture').glob('*.png')),'Unexpected print')
        actual_counts=dict(decoded_frames=len(frames),table_observations=sum(len(f['cards']) for f in frames.values()),candidate_hands=len(hands),candidate_decisions=len(records),selected_pending=len(sel['unresolved']),errors=0,prints=0,refined_frames=len(v['refinement']['frames']) if v['refinement'] else 0)
        need(all(w.get(k)==q for k,q in actual_counts.items()),'Window count mismatch')
        for k in KEYS:need(type(w[k]) is int and w[k]>=0,'Invalid count');totals[k]+=w[k]
    need(dict(totals)==summary['counts'] and digest(source)==h,'Session count or source mismatch')
    return dict(version='plo5-candidate-audit-v1',source_sha256=h,windows=len(rows),counts=dict(totals),metric_records_replayed=metrics_count,end_reasons=dict(ends),structural_audit_passed=True,pixels_independently_redecoded=False,semantic_truth_verified=False,beta_ready=False,remaining_gates=['independent_complete_real_hands','real_range_and_ev_validation','semantic_print_binding','end_to_end_runtime','windows10_acceptance','full_repository_regression'])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('report');p.add_argument('output');a=p.parse_args(argv);out=Path(a.output);need(not out.exists() and not out.is_symlink() and out.suffix=='.json','New JSON required');r=audit(a.video,a.report)
    with out.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,indent=2)
    print(json.dumps(r,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
