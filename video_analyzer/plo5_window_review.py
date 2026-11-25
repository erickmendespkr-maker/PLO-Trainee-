"""Merge adjacent offline PLO5 observations into review candidates, not hand histories."""
from collections import Counter, defaultdict
from decimal import Decimal
import math
import re

HEX = re.compile(r'[0-9a-f]{64}\Z')
CROP = re.compile(r'table_\d{2}_\d{3}\.png\Z')
FLAGS = ('hands_reconstructed', 'actions_verified', 'video_verified',
         'equity_ev_authorized', 'automatic_clip_selection_authorized')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def cards(value, lengths):
    need(value is None or (type(value) is list and len(value) in lengths
         and all(type(c) is str and re.fullmatch('[2-9TJQKA][cdhs]', c) for c in value)
         and len(set(value)) == len(value)), 'Invalid candidate cards')
    return value


def amount(value):
    if value is None:
        return None
    need(type(value) is str and re.fullmatch(r'\d{1,9}(?:\.\d{1,2})?', value), 'Invalid BB amount')
    return Decimal(value)


def build(windows, *, max_gap=1.5):
    """Pure candidate fusion. The caller must independently bind each window to media."""
    need(type(windows) is list and 1 <= len(windows) <= 8, 'Invalid window count')
    need(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0 < max_gap <= 2.5, 'Invalid gap')
    groups = defaultdict(list); identity = None; keys = set(); total = 0; roster = None
    for item in windows:
        need(type(item) is dict and set(item) == {'window','timeline','money'}, 'Invalid window entry')
        name, t, m = (item[k] for k in ('window','timeline','money'))
        need(type(name) is str and re.fullmatch(r'window_\d{2}', name) and name not in keys, 'Duplicate or invalid window name')
        keys.add(name)
        ident = tuple(t[k] for k in ('job_id','source_sha256','sparse_manifest_sha256','annotation_sha256'))
        need(all(type(x) is str and HEX.fullmatch(x) for x in ident[1:]) and type(ident[0]) is str and re.fullmatch('[0-9a-f]{32}',ident[0]), 'Invalid source identity')
        need(identity is None or identity == ident, 'Mixed job or calibration'); identity = ident
        need(type(t['variant']) is int and t['variant'] == 5 and all(t.get(k) is False for k in FLAGS), 'Untrusted timeline status')
        start, seconds = t['start'], t['seconds']
        need(type(start) is int and start >= 0 and type(seconds) is int and 2 <= seconds <= 60, 'Invalid window bounds')
        obs=t['observations']; total+=len(obs); need(0 < len(obs) <= 240 and total <= 512, 'Observation budget exceeded')
        ix={r['file']:r for r in obs}; need(len(ix)==len(obs), 'Duplicate window crop')
        money={}
        if m is not None:
            need(m.get('variant')==5 and m.get('job_id')==ident[0] and m.get('source_sha256')==ident[1] and m.get('financial_result_verified') is False, 'Money identity mismatch')
            money={r['file']:r for r in m['observations']}; need(len(money)==len(m['observations']) and set(money)==set(ix), 'Incomplete money coverage')
        schedule=defaultdict(set)
        for r in obs:
            f,tid,p=r['file'],r['table_id'],r['pts']; h,b=cards(r['hero_cards'],(5,)),cards(r['board_cards'],(0,3,4,5))
            need(type(f) is str and CROP.fullmatch(f) and type(tid) is int and 1<=tid<=4 and int(f[6:8])==tid and type(p) in (int,float) and math.isfinite(p) and start<=p<start+seconds, 'Invalid observation identity')
            need(type(r['sha256']) is str and HEX.fullmatch(r['sha256']) and (r['visible'] is None or type(r['visible']) is bool), 'Invalid crop status')
            need(h is None or b is None or not set(h)&set(b), 'Conflicting cards')
            need(math.floor(p) not in schedule[tid], 'Duplicate sampled second'); schedule[tid].add(math.floor(p))
            mr=money.get(f)
            if mr is not None:
                need(mr['table_id']==tid and mr['pts']==p and mr['crop_sha256']==r['sha256'], 'Money crop mismatch')
            label=((r.get('action_reading') or {}).get('candidate') or {}).get('action')
            groups[tid].append(dict(file=name+'/'+f,pts=p,sha256=r['sha256'],visible=r['visible'],hero=h,board=b,label=label,
                                    stack_bb=amount(mr.get('stack_bb')) if mr else None,pot_bb=amount(mr.get('pot_bb')) if mr else None))
        need(all(v==set(range(start,start+seconds)) for v in schedule.values()), 'Incomplete window schedule')
        need(roster is None or roster==set(schedule), 'Table roster changed'); roster=set(schedule)
    output=[]; unassigned=[]
    for tid,rows in sorted(groups.items()):
        rows.sort(key=lambda r:r['pts']); need(len({math.floor(r['pts']) for r in rows})==len(rows), 'Overlapping windows')
        segment=None; previous=None; hero=None; board=None
        for r in rows:
            if r['visible'] is not True:
                unassigned.append({'table_id':tid,'file':r['file'],'reason':'visibility_uncertain'}); segment=previous=hero=board=None; continue
            h,b=r['hero'],r['board']; reason=None
            if segment is None: reason='start_or_visibility_gap'
            elif r['pts']-previous['pts']>max_gap: reason='sampling_gap'
            elif hero is not None and h is not None and set(h)!=hero: reason='private_cards_conflict'
            elif board is not None and b is not None and b[:len(board)]!=board: reason='board_reset_or_conflict'
            if reason:
                segment={'candidate_id':f't{tid}_{len(output)+1:04d}','table_id':tid,'start_reason':reason,'frames':[]}; output.append(segment);hero=board=None
            # Cross-frame contradictions (including when one field is temporarily unreadable) are not silently accepted.
            if ((h is not None and board is not None and set(h)&set(board)) or
                (b is not None and hero is not None and set(b)&hero)):
                unassigned.append({'table_id':tid,'file':r['file'],'reason':'cross_frame_card_conflict'});segment=previous=hero=board=None;continue
            if h is not None: hero=set(h)
            if b is not None: board=b
            segment['frames'].append(r);previous=r
    output=[s for s in output if s['frames']]
    for s in output:
        frames=s['frames']; holdings=Counter(tuple(sorted(r['hero'])) for r in frames if r['hero'] is not None)
        preflop=[r['file'] for r in frames if r['hero'] is not None and r['board']==[]]
        board_evidence={str(n):[r['file'] for r in frames if r['board'] is not None and len(r['board'])==n] for n in (0,3,4,5)}
        s.update(start_pts=frames[0]['pts'],end_pts=frames[-1]['pts'],windows=sorted({r['file'].split('/')[0] for r in frames}),
                 corroborated_hero_candidates=[{'cards':list(h),'observations':n} for h,n in sorted(holdings.items()) if n>=2],
                 preflop_evidence=preflop,board_evidence=board_evidence,fold_label_files=[r['file'] for r in frames if r['label']=='fold'],
                 stack_observations=sum(r['stack_bb'] is not None for r in frames),pot_observations=sum(r['pot_bb'] is not None for r in frames),
                 complete_hand_verified=False,financial_result_bb=None,position_verified=False,hero_identity_verified=False)
        for r in frames:
            for k in ('stack_bb','pot_bb'):
                if r[k] is not None:r[k]=str(r[k])
    need(sum(len(s['frames']) for s in output)+len(unassigned)==total, 'Coverage mismatch')
    return {'variant':5,'status':'CROSS_WINDOW_REVIEW_CANDIDATES','job_id':identity[0],'source_sha256':identity[1],
            'manifest_sha256':identity[2],'annotation_sha256':identity[3],'observations':total,'segments':output,'unassigned':unassigned,
            'financial_result_verified':False,'ev_loss_bb':None,**{k:False for k in FLAGS}}


def run(job, paths, output, *, max_gap=1.5):
    """Use the existing independent dense-window media recheck before fusion."""
    from pathlib import Path
    from plo5_financial_observations import bound_window
    from plo5_session_export import load, write
    from offline_video_ingest_probe import sha256
    items=[]; refs=[]; binding=None
    for entry in paths:
        need(type(entry) is dict and set(entry)=={'timeline','money'}, 'Invalid path entry')
        p=Path(entry['timeline']); t,th,b,crops=bound_window(job,p)
        need(binding is None or binding==b,'Job binding changed');binding=b
        m=None
        if entry['money'] is not None:
            mp=Path(entry['money']);m,mh=load(mp);need(m.get('timeline_sha256')==th,'Money timeline mismatch');refs.append((mp,mh))
        refs.append((p,th));refs.extend((crops[r['file']],r['sha256']) for r in t['observations'])
        items.append({'window':p.parent.name,'timeline':t,'money':m})
    result=build(items,max_gap=max_gap)
    from plo5_ingest_job import read_bound_evidence
    need(read_bound_evidence(job['database'],job['job_id'])==binding and sha256(job['annotations'])==result['annotation_sha256'] and all(sha256(p)==h for p,h in refs),'Evidence changed')
    out=Path(output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required');write(out,result);return result


if __name__=='__main__':
    import argparse
    from plo5_session_export import load
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job');p.add_argument('windows');p.add_argument('output');p.add_argument('--max-gap',type=float,default=1.5);a=p.parse_args();run(load(a.job)[0],load(a.windows)[0],a.output,max_gap=a.max_gap)
