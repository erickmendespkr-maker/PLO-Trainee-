"""Offline PLO5 video-only beta candidate. Recognition fragments are not hands.
The optional annotated replay route is a validation aid, not automatic truth.
"""
import argparse
from collections import Counter
from fractions import Fraction
import html
import json
from math import ceil
import os
from pathlib import Path
import subprocess
import tempfile
from plo5_pre_gto_context import need, cards
from plo5_bounded_session import run as scan_session, load_interval
from plo5_video_stream import digest, SIZE
from plo5_error_prints import read, stamp
from plo5_reconstruction_candidates import state, collect, money
from plo5_snapshot_replay import replay, chips
from plo5_decision_math import snapshot_metrics, review_snapshots
from plo5_selective_review import STREETS, street_filter, VERSION
from plo5_selective_study_report import build


def probe(source):
    p=Path(source);need(p.is_file() and not p.is_symlink() and p.suffix.lower()=='.mp4','Selecione um MP4 local.')
    r=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,start_time,duration','-of','json',str(p)],capture_output=True,timeout=30,check=True)
    need(len(r.stdout)<=65536,'Invalid probe size');s=json.loads(r.stdout)['streams'][0]
    need((s['width'],s['height'])==SIZE,'Geometria ainda não suportada: use 1504x696.')
    need(Fraction(s['start_time'])==0,'Nonzero source start not supported')
    seconds=ceil(Fraction(s['duration']));need(2<=seconds<=86400,'Invalid video duration');return seconds


class Fragments:
    """Track compatible candidate card fragments across windows, bounded memory.
    Never identify a hand from cards alone, or bridge an unknown/gap/reset.
    """
    def __init__(self,emit):
        self.last={};self.prev=None;self.counts=Counter();self.platforms=Counter();self.emit=emit
    def close(self,t,reason):
        old=self.last.pop(t,None)
        if old is not None:
            self.counts['fragments']+=1;self.counts['end_'+reason]+=1
            if old['board_lengths']==[0,3,4,5]:self.counts['all_streets_candidates']+=1
            self.emit(dict(old,ended_by=reason,hand_verified=False))
    def add(self,f):
        pts=stamp(f['pts']);need(self.prev is None or pts>self.prev,'Unordered session frames')
        if self.prev is not None and not (pts-self.prev<=Fraction(3,2) and pts//1-self.prev//1==1):
            for t in list(self.last):self.close(t,'gap')
        self.prev=pts;self.counts['frames']+=1
        by={(r['table_id'],r['field']):r for r in f['observations']}
        cr={c['table_id']:c for c in f.get('cards',[])}
        for t in range(1,5):
            a,b=by[t,'stack'],by[t,'pot'];p=a['platform'];old=self.last.get(t)
            if p is None:self.close(t,'inactive');continue
            self.platforms[p]+=1;self.counts['active_samples']+=1
            if money(a['value_bb']) is not None and money(b['value_bb']) is not None:self.counts['complete_money_samples']+=1
            c=cr.get(t);s=state(c)
            if s is None:self.counts['unknown_card_samples']+=1;self.close(t,'unknown_cards');continue
            h,board=s;self.counts['complete_card_samples']+=1
            profile=c.get('rank_profile')
            if old is not None:
                prior=old['last_board'];reason=None
                if (p,profile)!=(old['platform'],old['profile']):reason='profile'
                elif h!=old['holding'] or board[:len(prior)]!=prior:reason='reset_or_conflict'
                elif len(board)!=len(prior) and len(board)!=(3 if not prior else len(prior)+1):reason='skipped_street'
                if reason:self.close(t,reason);old=None
            if old is None:
                old=dict(table_id=t,platform=p,profile=profile,holding=h,first_pts=str(pts),first_rgb_sha256=f['rgb_sha256'],board_lengths=[len(board)],samples=0)
                self.last[t]=old
            elif len(board)!=len(old['last_board']):old['board_lengths'].append(len(board));self.counts['street_advances']+=1
            old.update(last_pts=str(pts),last_rgb_sha256=f['rgb_sha256'],last_board=board,samples=old['samples']+1)
    def finish(self):
        for t in list(self.last):self.close(t,'session_end')
        return dict(counts=dict(self.counts),platforms=dict(self.platforms),hands_verified=0,automatic_decisions_verified=0)


def write_json(p,v):
    with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,allow_nan=False,indent=2)


def diagnostics(session_path,dest):
    m=read(session_path);need(m.get('version')=='plo5-windowed-candidates-v1' and m.get('variant')==5,'Invalid session')
    windows=m['windows'];need(type(windows) is list and 1<=len(windows)<=43200,'Invalid windows')
    missing=0
    with dest.open('x',encoding='utf-8') as f:
        tr=Fragments(lambda row:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n'))
        for w in windows:
            # Read only one bounded interval; verifies file integrity and scope.
            r=load_interval(session_path,w['start'],w['seconds']);collect(r['frames']);missing+=len(r['missing_sample_seconds'])
            for frame in r['frames']:tr.add(frame)
        result=tr.finish()
    need(result['counts'].get('frames',0)==m['frames'] and missing==m['missing_sample_seconds'],'Session totals mismatch')
    return dict(result,missing_sample_seconds=missing,windows=len(windows),source_sha256=m['source_sha256'])


def compare_snapshots(manifest,seed,snapshots):
    """Compare candidates with declared references; not independent ground truth."""
    from plo5_error_prints import frame_index
    frames=frame_index(manifest);t=seed['table_id'];bb=seed['bb'];counts={k:Counter() for k in ('hero_stack','pot','holding','board')}
    def record(k,v,expected):counts[k]['missing' if v is None else 'match' if v==expected else 'mismatch']+=1
    for r in snapshots:
        f=frames[stamp(r['pts'])];obs={x['field']:x['value_bb'] for x in f['observations'] if x['table_id']==t}
        for key,field,expected in [('hero_stack','stack',r['remaining']['hero_bottom']),('pot','pot',r['pot'])]:
            try:value=chips(obs[field],bb) if obs.get(field) is not None else None
            except ValueError:counts[key]['unrepresentable']+=1;continue
            record(key,value,expected)
        c=next((x for x in f.get('cards',[]) if x['table_id']==t),{})
        h=c.get('hero_cards');record('holding',cards(h) if h is not None else None,cards(r['holding']));record('board',c.get('board_cards'),r['board'])
    return {k:dict(v) for k,v in counts.items()}


def annotated(source,session_path,annotation,streets,stage,*,cache=None,native=None,rank=None):
    a=read(annotation);need(type(a) is dict and {'version','source_sha256','hands'}==set(a) and a['version']=='plo5-annotated-validation-v1','Invalid annotation contract')
    need(a['source_sha256']==digest(source)==read(session_path)['source_sha256'],'Annotation source mismatch')
    need(type(a['hands']) is list and len(a['hands'])<=64,'Annotation budget');records=[];details=[];seen=set()
    from contextlib import ExitStack
    with ExitStack() as stack:
        worker=None
        if rank:
            from plo5_rank_worker import RankWorker
            from plo5_rank_lru import CachedRankWorker
            worker=CachedRankWorker(stack.enter_context(RankWorker(rank)))
        for h in a['hands']:
            need(type(h) is dict and {'seed','snapshots'}<=set(h)<={'seed','snapshots','model'},'Invalid annotated hand');seed=h['seed'];snapshots=h['snapshots'];ident=seed['hand_id'];need(ident not in seen,'Duplicate annotated hand');seen.add(ident)
            need(type(snapshots) is list and 1<=len(snapshots)<=512,'Invalid snapshots');first=int(stamp(snapshots[0]['pts'])//1);last=int(stamp(snapshots[-1]['pts'])//1);m=load_interval(session_path,first,last-first+1)
            r=replay(m,seed,snapshots);metrics=snapshot_metrics(m,seed,snapshots,streets)
            if 'model' in h:
                need(cache is not None,'Model cache required');cfg=h['model'];need(type(cfg) is dict and {'ranges','rake_bps','rake_cap','rake_on_fold'}<=set(cfg)<={'ranges','rake_bps','rake_cap','rake_on_fold','iterations','pot_bps','joint','max_runouts'},'Invalid annotated model')
                metrics=review_snapshots(cache,m,seed,snapshots,streets=streets,cfr_executable=native,rank_worker=worker,**cfg)
            records.extend(r['decision_records']);details.append(dict(hand_id=ident,replay=r,math=metrics,comparison=compare_snapshots(m,seed,snapshots)))
    write_json(stage/'annotated_validation.json',details)
    return records,len(details)


def landing(stage,summary):
    def e(x):return html.escape(str(x),quote=True)
    c=summary['diagnostics']['counts'];r=summary['report'];p=summary['diagnostics']['platforms']
    body=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PLO Trainee — Candidato de vídeo</title><style>body{font:16px system-ui;background:#f4f6f8;color:#172334;max-width:860px;margin:auto;padding:24px}section{background:white;border:1px solid #dce1e8;border-radius:12px;padding:16px;margin:14px 0}a{color:#164a9c}dt{font-weight:bold}dd{margin:0 0 12px}</style><h1>PLO Trainee — PLO5</h1><p><strong>Candidato de desenvolvimento, não beta validado.</strong> Revisão offline de vídeo encerrado.</p><section><h2>Relatório de estudos</h2>',f'<p>Erros demonstrados: {r["errors"]} · Decisões pendentes: {r["unresolved"]}</p><p>Não significa ausência de erros. Ainda não há reconstrução autônoma certificada nem estratégia GTO validada.</p><p><a href="study/index.html">Abrir relatório seletivo</a></p></section><section><h2>Diagnóstico do reconhecimento</h2><dl>']
    for label,value in [('Frames amostrados',c.get('frames',0)),('Segundos sem amostra',summary['diagnostics']['missing_sample_seconds']),('Observações de mesas ativas',c.get('active_samples',0)),('Cartas completas candidatas',c.get('complete_card_samples',0)),('Fragmentos compatíveis (não mãos)',c.get('fragments',0)),('Fragmentos candidatos nas quatro streets',c.get('all_streets_candidates',0)),('PPPoker / Suprema',str(p.get('pppoker',0))+' / '+str(p.get('suprema',0))),('Mãos anotadas para validação',summary['annotated_hands'])]:body.append('<dt>'+e(label)+'</dt><dd>'+e(value)+'</dd>')
    body.append('</dl><p>Assentos efetivamente distribuídos, ordem e valores das ações, continuidade e ranges ainda requerem validação. Nenhum print para decisões adequadas ou indeterminadas.</p><p><a href="fragments.jsonl">Fragmentos candidatos</a> · <a href="summary.json">Resumo técnico</a></p>')
    if summary['annotated_hands']:body.append('<p><a href="annotated_validation.json">Validação com anotações declaradas (não automática)</a></p>')
    body.append('</section><footer>DriveHUD fora do beta. Sem assistência durante jogo.</footer></html>')
    (stage/'index.html').write_text(''.join(body),encoding='utf-8')


def run(source,output,*,start=0,seconds=None,streets=STREETS,workers=2,backend='cli',ppp=None,suprema=None,session=None,annotation=None,cache=None,native=None,rank=None,progress=None):
    selected=street_filter(streets);out=Path(output);need(not out.exists() and not out.is_symlink() and out.parent.is_dir(),'Escolha uma pasta nova.')
    source=Path(source);duration=probe(source);source_hash=digest(source)
    with tempfile.TemporaryDirectory(prefix='.plo23-',dir=out.parent) as tmp:
        stage=Path(tmp)/'result';stage.mkdir()
        if session is None:
            n=duration-start if seconds is None else seconds;need(type(start) is int and type(n) is int and 0<=start<duration and 2<=n<=duration-start,'Invalid scan interval')
            scan_session(source,stage/'recognition',start,n,workers=workers,backend=backend,ppp=ppp,suprema=suprema,progress=progress);session=stage/'recognition'/'session.json'
        else:need(start==0 and seconds is None,'Existing session defines its own range')
        d=diagnostics(session,stage/'fragments.jsonl');need(d['source_sha256']==source_hash,'Session source mismatch')
        records,n=[],0
        if annotation:records,n=annotated(source,session,annotation,selected,stage,cache=cache,native=native,rank=rank)
        # Candidate replay records do not authorize prints or assert strategy truth.
        report=build(records,stage/'study',selected);need(report['errors']==0 and report['unique_crops']==0,'Uncertified beta input cannot authorize error prints')
        write_json(stage/'decisions.json',dict(version=VERSION,decisions=records));need(digest(source)==source_hash,'Source changed')
        summary=dict(version='plo5-video-beta-candidate-v1',source_sha256=source_hash,streets=list(selected),diagnostics=d,annotated_hands=n,report=report,beta_ready=False,windows_certified=False,drivehud_beta=False)
        write_json(stage/'summary.json',summary);landing(stage,summary);need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('output');p.add_argument('--start',type=int,default=0);p.add_argument('--seconds',type=int);p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));p.add_argument('--workers',type=int,choices=(1,2,3),default=2);p.add_argument('--backend',choices=('cli','native'),default='cli');p.add_argument('--ppp');p.add_argument('--suprema');p.add_argument('--session');p.add_argument('--annotation');p.add_argument('--cache');p.add_argument('--native');p.add_argument('--rank');a=p.parse_args(argv)
    r=run(a.video,a.output,start=a.start,seconds=a.seconds,streets=a.streets,workers=a.workers,backend=a.backend,ppp=a.ppp,suprema=a.suprema,session=a.session,annotation=a.annotation,cache=a.cache,native=a.native,rank=a.rank,progress=lambda w:print(json.dumps(dict(progress=w),ensure_ascii=False),flush=True));print(json.dumps(r,ensure_ascii=False),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
