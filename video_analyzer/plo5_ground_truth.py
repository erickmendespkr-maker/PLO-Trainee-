"""Offline PLO5 annotation template and sampled-frame recognition benchmark."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import json

from plo5_ingest_job import read_bound_evidence
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest
from offline_omaha_showdown import _cards
from offline_video_ingest_probe import sha256
from plo5_session_export import load, write
from plo5_leak_review import aggregate, identity, need, identifier

ACTIONS={'fold','check','call','bet','raise','all_in'}
POSITIONS={'UTG','MP','CO','BTN','SB','BB','BTN/SB','EP'}
FIELDS={'visible','hero_seat','hero_cards','board','position','pot_bb','hero_stack_bb','hero_action_label','hand_id','decision_action'}
UNKNOWN=object()


def frames(binding, manifest, drafts):
    expected={**binding,'manifest_sha256':binding['reports']['evidence/ingest/manifest.json']}
    need(type(drafts.get('variant')) is int and drafts.get('variant')==5 and all(drafts.get(k)==expected[k] for k in ('job_id','source_sha256','manifest_sha256')) and drafts.get('status')=='unverified_hand_timeline_drafts' and all(drafts.get(k) is False for k in ('hands_reconstructed','actions_verified','equity_ev_authorized','automatic_clip_selection_authorized')),'Invalid drafts')
    need(manifest['source_sha256']==binding['source_sha256'],'Manifest source mismatch')
    samples={s['file']:s for s in manifest['samples']};need(len(samples)==len(manifest['samples']),'Duplicate sample')
    out={};ids=set()
    def add(f,t,d):
        name=f['file'];s=samples.get(name)
        need(s is not None and name not in out and s['table_id']==t and s['actual_frame_timestamp_seconds']==f['pts'] and s['sha256']==f['crop_sha256'],'Frame evidence mismatch')
        out[name]=(f,t,d)
    for d in drafts['drafts']:
        did=d['draft_id'];need(identifier(did) and did not in ids and d['hand_id'] is None and d['complete_hand_verified'] is False,'Invalid draft segment');ids.add(did)
        for f in d['frames']:add(f,d['table_id'],did)
    for f in drafts['unassigned']:add(f,f['table_id'],None)
    need(set(out)==set(samples),'Incomplete draft coverage')
    return out,ids


def template(binding, manifest):
    return {'variant':5,'job_id':binding['job_id'],'source_sha256':binding['source_sha256'],
            'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],
            'dataset_kind':'real_recording','reviewer':'','independent_review':False,
            'annotations':[{'file':s['file'],'crop_sha256':s['sha256'],'table_id':s['table_id'],
                            'pts':s['actual_frame_timestamp_seconds'],'truth':{}} for s in manifest['samples']]}


def canonical(key,v):
    if v is None:
        need(key not in ('visible','hero_seat','position','pot_bb','hero_stack_bb','board'),'Omit unknown field instead of null')
        return None
    if key=='visible':need(type(v) is bool,'Invalid visibility');return v
    if key=='hero_seat':need(type(v) is int and 1<=v<=6,'Invalid seat');return v
    if key in ('hero_cards','board'):
        need(type(v) is list and len(v) in ((5,) if key=='hero_cards' else (0,3,4,5)),'Invalid cards')
        c=_cards(v,len(v));return tuple(sorted(c)) if key=='hero_cards' else tuple(c)
    if key=='position':need(v in POSITIONS,'Invalid position');return v
    if key in ('hero_action_label','decision_action'):need(v in ACTIONS,'Invalid action');return v
    if key=='hand_id':need(identifier(v),'Invalid hand ID');return v
    if key in ('pot_bb','hero_stack_bb'):
        import re
        need(type(v) is str and re.fullmatch(r'\d{1,10}(?:\.\d{1,8})?',v),'Use explicit decimal BB')
        return Fraction(v)
    raise ValueError('Unknown annotation field')


def predictions(f):
    c=f['context'];seat=f['hero_seat_declared'];a=[r['reading'] for r in f['actions'] if r['seat']==seat]
    need(len(a)==1,'Invalid hero action row');a=a[0]
    label=(a.get('candidate') or {}).get('action',UNKNOWN)
    if label is UNKNOWN and a.get('status')=='uniform_blank_candidate':label=None
    values={'visible':f['visible'],'hero_seat':seat if f['hero_cards'] is not None and f['board']==[] else UNKNOWN,
            'hero_cards':f['hero_cards'] if f['hero_cards'] is not None else UNKNOWN,'board':f['board'],
            'position':c.get('hero_position_candidate'),'pot_bb':c.get('pot_bb'),
            'hero_stack_bb':(c.get('remaining_stacks_bb') or {}).get(str(seat),(c.get('remaining_stacks_bb') or {}).get(seat)),
            'hero_action_label':label}
    return {k:canonical(k,v) if v is not UNKNOWN and (v is not None or k=='hero_action_label') else UNKNOWN for k,v in values.items()}


def score(pairs):
    counts=Counter();n=len(pairs)
    for truth,pred in pairs:
        if pred is UNKNOWN:counts['abstain']+=1;counts['fn']+=truth is not None and truth is not False;continue
        positive=truth is not None and truth is not False; predicted=pred is not None and pred is not False
        if truth==pred:counts['tp' if positive else 'tn']+=1
        else:counts['fp']+=predicted;counts['fn']+=positive;counts['wrong']+=1
    tp,tn,fp,fn,ab=(counts[k] for k in ('tp','tn','fp','fn','abstain'))
    def rate(a,b):return a/b if b else None
    return {'annotated':n,'predicted':n-ab,'abstained':ab,'exact_matches':tp+tn,'tp':tp,'tn':tn,'fp':fp,'fn':fn,
            'coverage':rate(n-ab,n),'accuracy_all_annotated':rate(tp+tn,n),'accuracy_when_predicted':rate(tp+tn,n-ab),
            'precision':rate(tp,tp+fp),'recall':rate(tp,tp+fn)}


def evaluate(binding, manifest, drafts, draft_sha, annotations, bundle=None):
    indexed,ids=frames(binding,manifest,drafts);base=template(binding,manifest)
    need(type(annotations) is dict and set(annotations)==set(base) and type(annotations['variant']) is int and all(annotations[k]==base[k] for k in ('variant','job_id','source_sha256','manifest_sha256')),'Annotation identity mismatch')
    need(annotations['dataset_kind'] in ('synthetic_fixture','real_recording') and identifier(annotations['reviewer']) and annotations['independent_review'] is True,'Independent reviewer declaration required')
    rows=annotations['annotations'];need(type(rows) is list and 0<len(rows)<=len(indexed),'Invalid annotation count')
    truth_by_file={};metrics=defaultdict(list);per_table=defaultdict(lambda:defaultdict(list));errors=[];money=defaultdict(list)
    for row in rows:
        need(type(row) is dict and set(row)=={'file','crop_sha256','table_id','pts','truth'},'Invalid annotation row')
        name=row['file'];need(name in indexed and name not in truth_by_file,'Duplicate or unknown annotation')
        f,t,d=indexed[name];need(row['table_id']==t and row['pts']==f['pts'] and row['crop_sha256']==f['crop_sha256'],'Annotation evidence mismatch')
        fields=row['truth'];need(type(fields) is dict and set(fields)<=FIELDS,'Unknown truth field')
        truth={k:canonical(k,v) for k,v in fields.items()};truth_by_file[name]=truth
        if truth.get('hero_cards') and truth.get('board'):need(not set(truth['hero_cards'])&set(truth['board']),'Overlapping annotated cards')
        p=predictions(f)
        for k,v in truth.items():
            if k not in p:continue
            pred=p[k];metrics[k].append((v,pred));per_table[t][k].append((v,pred))
            if k in ('pot_bb','hero_stack_bb') and pred is not UNKNOWN:money[k].append(abs(v-pred))
            if pred is UNKNOWN or pred!=v:errors.append({'file':name,'table_id':t,'field':k,'kind':'abstained' if pred is UNKNOWN else 'mismatch'})
    # Adjacent sampled frames only: no timing/complete-hand claim.
    tables=defaultdict(list)
    for name,(f,t,d) in indexed.items():tables[t].append((f['pts'],name,d))
    boundaries=[]
    for t,items in tables.items():
        items.sort()
        for (p,a,x),(q,b,y) in zip(items,items[1:]):
            u=truth_by_file.get(a,{}).get('hand_id');v=truth_by_file.get(b,{}).get('hand_id')
            if p>=q or u is None or v is None:continue
            pred=UNKNOWN if x is None or y is None else x!=y
            boundaries.append((u!=v,pred));per_table[t]['sampled_boundary'].append((u!=v,pred))
    reports={};comparable=set()
    if bundle is not None:
        identity(bundle,{**binding,'manifest_sha256':base['manifest_sha256'],'draft_sha256':draft_sha})
        need(set(bundle['draft_ids'])==ids,'Decision bundle draft roster mismatch');summary=aggregate(bundle)
        for e in bundle['expected_decisions']:
            need(e['action_file'] in indexed and indexed[e['action_file']][2]==e['draft_id'],'Unbound expected decision')
        for r in bundle['reports']:
            for k in ('context','action'):
                name=r[k+'_file'];need(name in indexed and indexed[name][2]==r['draft_id'] and indexed[name][0]['pts']==r[k+'_pts'],'Unbound report')
            reports[r['action_file']]=r
        comparable={r['action_file'] for r in summary['decisions'] if r['loss_bounds_bb'] is not None}
    decisions=[(f,t['decision_action']) for f,t in truth_by_file.items() if t.get('decision_action') is not None]
    matched=[f for f,a in decisions if f in reports and reports[f]['chosen_action_declared']['action']==a]
    return {'variant':5,'status':'SAMPLED_ANNOTATION_COMPARISON','dataset_kind_declared':annotations['dataset_kind'],
            'source_sha256':binding['source_sha256'],'manifest_sha256':base['manifest_sha256'],'draft_sha256':draft_sha,
            'sampled_frames':len(indexed),'annotated_frames':sum(bool(t) for t in truth_by_file.values()),'metrics':{k:score(metrics[k]) for k in sorted(FIELDS-{'hand_id','decision_action'})},
            'by_table':{str(t):{k:score(v) for k,v in m.items()} for t,m in per_table.items()},'sampled_boundary':score(boundaries),
            'money_error_bb':{k:{'compared':len(v),'mae':float(sum(v)/len(v)) if v else None,'max_error':float(max(v)) if v else None} for k in ('pot_bb','hero_stack_bb') for v in [money[k]]},
            'decision_coverage':{'annotated_decision_frames':len(decisions),'matching_action_reports':len(matched),'conditionally_comparable':sum(f in comparable for f in matched),'scope':'sampled_declared_action_class_only_not_sizing_or_full_history'},
            'errors':errors,'reviewer_declared':annotations['reviewer'],'reviewer_authenticated':False,'real_session_validated':False,'complete_hands_verified':False,'gto_solution':False,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database');p.add_argument('job_id');p.add_argument('output');p.add_argument('--drafts');p.add_argument('--annotations');p.add_argument('--bundle');a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    b=read_bound_evidence(a.database,a.job_id);job=OfflineJobStore(a.database).get(a.job_id);m=read_manifest(Path(job['result_path']).parent/'evidence/ingest/manifest.json')
    if a.annotations:
        need(a.drafts,'Drafts required');d,dh=load(a.drafts);ann,ah=load(a.annotations);bundle,bh=load(a.bundle) if a.bundle else (None,None)
        result=evaluate(b,m,d,dh,ann,bundle);result.update(annotation_sha256=ah,decision_bundle_sha256=bh)
        need(sha256(a.drafts)==dh and sha256(a.annotations)==ah and (not a.bundle or sha256(a.bundle)==bh),'Input changed')
    else:
        need(not a.drafts and not a.bundle,'Template mode does not accept predictions');result=template(b,m)
    need(read_bound_evidence(a.database,a.job_id)==b,'Evidence changed');write(out,result);return 0


if __name__=='__main__':raise SystemExit(main())
