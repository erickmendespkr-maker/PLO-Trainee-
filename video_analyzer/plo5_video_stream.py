"""Bounded offline RGB sampling with source timestamp audit, no intermediate PNGs.
Recognition rows are candidates. This mode does not produce screenshot evidence.
"""
import hashlib
import json
import re
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from threading import Timer
from PIL import Image
from plo5_pre_gto_context import need
from plo5_visual_codes import MixedReader

SIZE=(1504,696)
FRAME_BYTES=SIZE[0]*SIZE[1]*3


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def roster(source,start,seconds):
    p=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-read_intervals',f'{start}%{start+seconds+1}',
        '-show_entries','stream=time_base,width,height:frame=best_effort_timestamp','-of','json',str(source)],
        stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60,check=True)
    need(len(p.stdout)<=32*1024**2,'Probe output budget exceeded')
    d=json.loads(p.stdout);s=d['streams'][0];need((s['width'],s['height'])==SIZE,'Unsupported geometry')
    tb=Fraction(s['time_base']);need(tb>0,'Invalid time base')
    known={int(r['best_effort_timestamp']) for r in d['frames'] if 'best_effort_timestamp' in r}
    expected=sorted({int(t*tb//1) for t in known if start<=t*tb<start+seconds})
    need(expected,'No source frames in window');return tb,known,expected


def scan(source,start,seconds,*,capacity=512,workers=2,timeout=120,reader=None):
    need(type(start) is int and start>=0 and type(seconds) is int and 2<=seconds<=120,'Invalid window')
    need(type(timeout) is int and 1<=timeout<=300,'Invalid timeout')
    source=Path(source);need(source.is_file() and not source.is_symlink() and source.suffix.lower()=='.mp4','Local MP4 required')
    t=time.perf_counter();h=digest(source);tb,known,expected=roster(source,start,seconds);probe_s=time.perf_counter()-t
    if reader is None:reader=MixedReader(capacity,workers)
    command=['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-ss',str(start),'-t',str(seconds+1),'-copyts','-i',str(source),'-map','0:v:0','-vf',f"select='lt(t,{start+seconds})*(isnan(prev_selected_t)+gt(floor(t),floor(prev_selected_t)))',showinfo",'-frames:v',str(len(expected)),'-fps_mode','passthrough','-pix_fmt','rgb24','-c:v','rawvideo','-threads:v','1','-an','-sn','-dn','-f','rawvideo','pipe:1']
    rows=[];recognition=0.;begin=time.perf_counter()
    with tempfile.TemporaryFile() as log:
        with subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log) as p:
            timer=Timer(timeout,p.kill);timer.daemon=True;timer.start()
            try:
                for _ in expected:
                    raw=p.stdout.read(FRAME_BYTES);need(len(raw)==FRAME_BYTES,'Incomplete RGB frame')
                    a=time.perf_counter();image=Image.frombytes('RGB',SIZE,raw)
                    rows.append(dict(rgb_sha256=hashlib.sha256(raw).hexdigest(),observations=reader.scan(image)))
                    recognition+=time.perf_counter()-a
                need(p.stdout.read(1)==b'','Extra RGB data');need(p.wait()==0,'FFmpeg failed')
            finally:
                timer.cancel();timer.join()
                if p.poll() is None:p.kill()
                p.wait()
        need(log.tell()<=8*1024**2,'Media log budget exceeded');log.seek(0);logs=log.read().decode('utf-8',errors='strict')
    bases=re.findall(r'config in time_base: (\d+/\d+)',logs);need(bases and all(Fraction(x)==tb for x in bases),'PTS time base mismatch')
    stamps=[(int(n),int(v)) for n,v in re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:',logs)]
    need(len(stamps)==len(expected) and [n for n,v in stamps]==list(range(len(expected))) and all(v in known for n,v in stamps),'Unbound frame PTS')
    need([int(v*tb//1) for n,v in stamps]==expected,'Sample roster mismatch')
    for i,(row,(_,v)) in enumerate(zip(rows,stamps),1):row.update(file=f'sample_{i:05d}.rgb',pts=str(v*tb))
    pipeline_s=time.perf_counter()-begin;need(digest(source)==h,'Source changed')
    from plo5_reconstruction_candidates import collect
    evidence=collect(rows)
    return dict(variant=5,status='STREAM_DISPLAY_CANDIDATES_ONLY',source_sha256=h,frames=rows,evidence=evidence,
                probe_seconds=probe_s,pipeline_seconds=pipeline_s,recognition_seconds=recognition,wall_seconds=time.perf_counter()-t,
                cache=reader.cache.stats(),layout_cache=reader.layout.stats(),png_evidence_written=False,
                hands_reconstructed=False,financial_result_verified=False,strategy_authorized=False)
