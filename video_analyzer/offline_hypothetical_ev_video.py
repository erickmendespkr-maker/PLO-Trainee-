"""Render an explicitly hypothetical, offline EV report to MP4 using FFmpeg.

This is NOT a clip from a poker recording and cannot verify a poker decision.
Usage: python offline_hypothetical_ev_video.py RESULT.json NEW_REPORT.mp4
"""
from __future__ import annotations
import argparse
import io
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_text(value):
    need(type(value) is str and 1 <= len(value) <= 80 and
         all(c.isascii() and (c.isalnum() or c in '._-') for c in value),
         'unsafe identifier')
    return value


def valid_number(v, lo, hi):
    return type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi


def validate(result):
    need(type(result) is dict and result.get('schema_version') == 1 and
         type(result['schema_version']) is int and
         result.get('analysis_status') == 'hypothetical_range_sensitivity_not_video_verified' and
         result.get('source_hand_reconstruction_verified') is False and
         result.get('strategic_error_established') is False and
         result.get('automatic_clip_selection_authorized') is False,
         'only unverified hypothetical reports allowed')
    safe_text(result.get('scenario_id'))
    p, c, be = (result.get(k) for k in
                ('pot_before_call_bb', 'call_cost_bb', 'break_even_equity'))
    need(valid_number(p, 0, 1e6) and valid_number(c, 1e-6, 1e6) and
         valid_number(be, 0, 1) and abs(be - c/(p+c)) <= 1e-7,
         'invalid pot odds')
    rows = result.get('range_results')
    need(type(rows) is list and 2 <= len(rows) <= 12, 'invalid range count')
    names = set()
    for row in rows:
        need(type(row) is dict and
             {'range_id','equity','equity_ci95','ev_call_bb','ev_call_ci95_bb',
              'conditional_label','iterations','seed'} <= set(row), 'invalid range')
        name = safe_text(row['range_id'])
        need(name not in names, 'duplicate range')
        names.add(name)
        q, interval, ev, ev_ci = (row[k] for k in
                                ('equity','equity_ci95','ev_call_bb','ev_call_ci95_bb'))
        need(valid_number(q,0,1) and type(interval) is list and len(interval)==2 and
             all(valid_number(x,0,1) for x in interval) and
             interval[0] <= q <= interval[1] and
             type(ev_ci) is list and len(ev_ci)==2 and
             all(valid_number(x,-1e6,1e6) for x in ev_ci) and
             abs(ev-(q*(p+c)-c)) < 1e-5 and
             all(abs(x-(y*(p+c)-c)) < 1e-5 for x,y in zip(ev_ci,interval)) and
             row['conditional_label'] in ('positive_under_interval',
                                          'negative_under_interval','uncertain_or_break_even') and
             type(row['iterations']) is int and row['iterations'] >= 100 and
             type(row['seed']) is int and 0 <= row['seed'] <= 2**32-1,
             'inconsistent conditional EV')
        expected = ('positive_under_interval' if ev_ci[0] > 0 else
                    'negative_under_interval' if ev_ci[1] < 0 else
                    'uncertain_or_break_even')
        need(row['conditional_label'] == expected, 'inconsistent EV label')
    labels = {r['conditional_label'] for r in rows}
    robust = labels in ({'positive_under_interval'}, {'negative_under_interval'})
    need(result.get('range_sensitive') is (not robust), 'range sensitivity mismatch')
    return rows


def text_lines(result, rows):
    lines = ['PLO TRAINEE | EXEMPLO HIPOTETICO',
             'NAO E ANALISE DE VIDEO OU SOLUCAO GTO',
             f"Cenario: {result['scenario_id']}",
             f"Pote antes do call: {result['pot_before_call_bb']:.2f} BB",
             f"Custo do call: {result['call_cost_bb']:.2f} BB",
             f"Equity minima: {100*result['break_even_equity']:.2f}%",
             'Modelo: heads-up, showdown, sem rake/side pots',
             'Sem apostas futuras; fold = 0 BB']
    for r in rows[:6]:
        lines.append(f"Range {r['range_id']}: equity {100*r['equity']:.2f}%  EV {r['ev_call_bb']:+.2f} BB")
        lines.append(f"IC95 condicional EV: {r['ev_call_ci95_bb'][0]:+.2f} a {r['ev_call_ci95_bb'][1]:+.2f} BB")
    if len(rows)>6:
        lines.append(f'Mais {len(rows)-6} ranges no JSON associado')
    lines.extend(['SENSIVEL AO RANGE' if result['range_sensitive'] else 'MESMA DIRECAO NOS RANGES INFORMADOS',
                  'Estimativas fornecidas; ranges nao verificados',
                  'Nenhum erro estrategico real comprovado'])
    return lines


def render(source, output):
    src, dst = Path(source), Path(output)
    sidecar = Path(str(dst)+'.json')
    need(src.is_file() and not src.is_symlink() and 0 < src.stat().st_size <= 65536,
         'invalid source')
    need(dst.suffix.lower()=='.mp4' and dst.parent.is_dir() and
         not dst.parent.is_symlink() and not dst.exists() and not dst.is_symlink() and
         not sidecar.exists() and not sidecar.is_symlink() and
         len({src.resolve(),dst.resolve(),sidecar.resolve()})==3,
         'new distinct MP4 and JSON paths required')
    source_sha = sha(src)
    def unique(pairs):
        result={}
        for k,v in pairs:
            need(k not in result,'duplicate JSON key')
            result[k]=v
        return result
    data=json.loads(src.read_text('utf-8'),object_pairs_hook=unique,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    rows=validate(data)
    with tempfile.TemporaryDirectory(prefix='.plo_ev_card_',dir=dst.parent) as temp:
        tmp=Path(temp)
        card=tmp/'card.txt'
        card.write_text('\n'.join(text_lines(data,rows))+'\n','utf-8')
        video=tmp/'card.mp4'
        # The textfile path is generated internally, never from untrusted JSON.
        vf=f"drawtext=textfile='{card}':expansion=none:fontcolor=white:fontsize=22:line_spacing=9:x=32:y=28"
        cmd=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
             '-f','lavfi','-i','color=c=0x142437:s=1280x720:r=15:d=7',
             '-vf',vf,'-an','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
             '-movflags','+faststart',str(video)]
        try:
            proc=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ValueError('FFmpeg unavailable or timed out') from exc
        need(proc.returncode==0 and video.is_file() and video.stat().st_size>0,
             'FFmpeg render failed: '+proc.stderr[-400:])
        probe=subprocess.run(['ffprobe','-v','error','-show_entries',
            'format=duration:stream=codec_type,width,height','-of','json',str(video)],
            capture_output=True,text=True,timeout=20,check=True)
        details=json.loads(probe.stdout)
        need(6.5 <= float(details['format']['duration']) <= 7.5 and
             any(s.get('codec_type')=='video' and s.get('width')==1280 and
                 s.get('height')==720 for s in details.get('streams',[])),
             'unexpected video output')
        # FFmpeg can finish successfully while drawtext silently draws nothing
        # (for example, when '%' in equity values is expanded as a directive).
        frame = subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
                                '-ss','1','-i',str(video),'-frames:v','1',
                                '-f','image2pipe','-vcodec','png','-'],
                               capture_output=True,timeout=20,check=True)
        with Image.open(io.BytesIO(frame.stdout)) as image:
            pixels = image.convert('RGB')
            # White lettering must occupy a visible area; the card background
            # itself has no bright pixels. This is a visibility check, not OCR.
            pixel_data = (pixels.get_flattened_data() if hasattr(pixels, 'get_flattened_data')
                          else pixels.getdata())
            bright = sum(max(rgb)>180 for rgb in pixel_data)
        need(bright >= 100, 'explanatory card text is not visible in decoded frame')
        need(sha(src)==source_sha,'input changed during export')
        meta={'schema_version':1,'analysis_status':'synthetic_hypothetical_ev_video_only',
              'source_report_sha256':source_sha,'mp4_sha256':sha(video),
              'scenario_id':data['scenario_id'],'range_count':len(rows),
              'range_sensitive':data['range_sensitive'],
              'rendered_text_bright_pixels':bright,
              'visual_text_verified_from_decoded_frame':True,
              'source_hand_reconstruction_verified':False,
              'strategic_error_established':False,
              'real_video_clip':False,'audio_included':False,
              'warning':'Synthetic explanatory card only; no real poker footage or GTO solution.'}
        meta_path=tmp/'card.json'
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n','utf-8')
        os.link(video,dst)
        try:
            os.link(meta_path,sidecar)
        except OSError:
            dst.unlink(missing_ok=True)
            raise
    return meta


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('hypothetical_result_json');p.add_argument('new_mp4')
    a=p.parse_args()
    print(json.dumps(render(a.hypothetical_result_json,a.new_mp4)))

if __name__=='__main__':main()
