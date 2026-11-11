"""Offline, audit-only link between a manually claimed call and hypothetical EV.

No source video is opened. Numerical agreement does not verify a hand, ranges,
equity, or a strategic error. Requires the preexisting conditional EV module.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from offline_conditional_call_sensitivity import compute

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def read(path):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=1024*1024,'invalid JSON source')
    def unique(pairs):
        out={}
        for k,v in pairs:
            require(k not in out,'duplicate JSON key')
            out[k]=v
        return out
    return json.loads(p.read_text('utf-8'),object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def number(v,lo,hi):
    return type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi

def audit(annotation,scenario,annotation_sha,scenario_sha):
    require(type(annotation) is dict and
            type(annotation.get('schema_version')) is int and annotation['schema_version']==1 and
            annotation.get('status')=='human_annotation_template_not_approved' and
            annotation.get('hands_reconstructed') is False and
            annotation.get('ready_for_equity_or_ev') is False and
            type(annotation.get('source_video_sha256')) is str and
            re.fullmatch('[a-f0-9]{64}',annotation['source_video_sha256']) and
            type(annotation.get('annotations')) is list,'untrusted annotation envelope')
    calculated=compute(scenario)
    selected=[a for a in annotation['annotations'] if type(a) is dict and
              a.get('review_status')=='reviewed_complete' and a.get('hero_action')=='call']
    require(len(selected)==1,'require exactly one manually claimed complete call')
    a=selected[0]
    require(type(a.get('hand_id')) is str and re.fullmatch('[A-Za-z0-9_.-]{1,80}',a['hand_id']) and
            a.get('variant') in ('PLO5','PLO6') and
            type(a.get('table_id')) is int and 1<=a['table_id']<=4 and
            number(a.get('hand_start_seconds'),0,3900) and
            number(a.get('hand_end_seconds'),0,3900) and
            a['hand_start_seconds']<a['hand_end_seconds'] and
            number(a.get('pot_before_action_bb'),0,1e6) and
            number(a.get('to_call_bb'),0,1e6),'invalid manually claimed hand')
    hole,board=a.get('hero_cards'),a.get('board_cards')
    require(type(hole) is list and len(hole)==(5 if a['variant']=='PLO5' else 6) and
            type(board) is list and len(board) in (0,3,4,5) and
            all(type(c) is str and re.fullmatch('[2-9TJQKA][cdhs]',c) for c in hole+board) and
            len(set(hole+board))==len(hole+board),'invalid or duplicate cards')
    require(math.isclose(a['pot_before_action_bb'],scenario['pot_before_call_bb'],
                         abs_tol=1e-7,rel_tol=0) and
            math.isclose(a['to_call_bb'],scenario['call_cost_bb'],
                         abs_tol=1e-7,rel_tol=0),'pot/call mismatch between claims')
    return {'schema_version':1,'status':'matching_claims_not_independently_verified',
            'annotation_sha256':annotation_sha,'scenario_sha256':scenario_sha,
            'source_video_sha256_claim':annotation['source_video_sha256'],
            'hand_id_claim':a['hand_id'],'table_id_claim':a['table_id'],
            'variant_claim':a['variant'],
            'hand_interval_seconds_claim':[a['hand_start_seconds'],a['hand_end_seconds']],
            'scenario_id':scenario['scenario_id'],'pot_call_values_match':True,
            'conditional_ev_result':calculated,'source_hand_reconstruction_verified':False,
            'equity_ranges_observed_from_video':False,'ready_for_strategic_verdict':False,
            'automatic_clip_selection_authorized':False,
            'warning':'Numerical agreement between unverified hand claim and hypothetical range/EV scenario; no GTO or real-hand verdict.'}

def run(annotation_path,scenario_path,output_path):
    a,s,out=map(Path,(annotation_path,scenario_path,output_path))
    require(out.suffix=='.json' and out.parent.is_dir() and not out.parent.is_symlink() and
            not out.exists() and not out.is_symlink() and
            len({p.resolve() for p in (a,s,out)})==3,'new distinct JSON output required')
    ah,sh=sha(a),sha(s)
    result=audit(read(a),read(s),ah,sh)
    require(sha(a)==ah and sha(s)==sh,'input changed during audit')
    with tempfile.TemporaryDirectory(prefix='.plo_evidence_',dir=out.parent) as d:
        stage=Path(d)/'result.json'
        stage.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+'\n','utf-8')
        os.link(stage,out)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('manual_annotations_json')
    p.add_argument('hypothetical_scenario_json')
    p.add_argument('new_audit_json')
    a=p.parse_args()
    print(json.dumps({'status':run(a.manual_annotations_json,a.hypothetical_scenario_json,
                                   a.new_audit_json)['status']}))

if __name__=='__main__':
    main()
