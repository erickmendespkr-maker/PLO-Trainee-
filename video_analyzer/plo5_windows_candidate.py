"""Local PLO5 review candidate: preflight, audited ingestion and recovery."""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import os

from plo5_regression_runner import snapshot
from plo5_real_session_audit import run, summarize
from offline_video_ingest_probe import regions_from_json, sample_times
from video_validator import validate_recording
from plo5_session_export import write


def check(equity_db):
    if sys.version_info < (3, 11):
        raise ValueError('Python 3.11 or later is required')
    import PIL
    db=snapshot(equity_db)
    tools={}
    for name,flag in [('ffmpeg','-version'),('ffprobe','-version'),('tesseract','--version')]:
        path=shutil.which(name)
        if not path:raise ValueError('Missing executable on PATH: '+name)
        result=subprocess.run([path,flag],capture_output=True,text=True,timeout=15,check=True)
        tools[name]=result.stdout.splitlines()[0]
    enc=subprocess.run([shutil.which('ffmpeg'),'-hide_banner','-encoders'],capture_output=True,text=True,timeout=15,check=True)
    if not any('libx264' in line.split() for line in enc.stdout.splitlines()):raise ValueError('FFmpeg must include libx264')
    return {'status':'DEPENDENCIES_AVAILABLE','variant':5,'python':sys.version.split()[0],'pillow':PIL.__version__,'tools':tools,'equity_db':db,'windows_verified':False,'mvp_certified':False}


def recover(database,job_id,interval,output):
    """Recover summary + blank annotation template without copying the video again."""
    db=Path(database);out=Path(output)
    if not db.is_file() or db.is_symlink():raise ValueError('Existing jobs database required')
    if not out.parent.is_dir() or out.exists() or out.is_symlink():raise ValueError('New output directory required')
    report,annotations=summarize(db,job_id,interval)
    with tempfile.TemporaryDirectory(prefix='.plo5-recover-',dir=out.parent) as tmp:
        stage=Path(tmp)/'report';stage.mkdir()
        write(stage/'media_audit.json',report);write(stage/'annotations.json',annotations)
        if out.exists() or out.is_symlink():raise ValueError('Output already exists')
        os.rename(stage,out)
    return report


def audit(recording,regions,output,*,interval=120,pixel_checks=8):
    src=Path(recording);out=Path(output)
    if src.suffix.lower()!='.mp4' or not src.is_file() or src.is_symlink():raise ValueError('Local recorded MP4 required')
    if not out.parent.is_dir() or out.exists() or out.is_symlink():raise ValueError('New output directory required')
    if type(pixel_checks) is not int or not 1<=pixel_checks<=512:raise ValueError('Invalid pixel check budget')
    if type(interval) not in (int,float) or not math.isfinite(interval) or not 5<=interval<=120:raise ValueError('Invalid sample interval')
    meta=validate_recording(src)
    if meta['width']>3840 or meta['height']>2160:raise ValueError('Recording exceeds audited geometry limit')
    regions_from_json(regions,meta['width'],meta['height'])
    sample_times(meta['duration_seconds'],None,interval)
    # Conservative initial guard, not a disk-space guarantee.
    if shutil.disk_usage(out.parent).free < 2*meta['size_bytes']+256*1024**2:raise ValueError('Insufficient initial disk budget')
    return run(src,regions,out,interval=interval,pixel_checks=pixel_checks)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('check');c.add_argument('equity_db')
    a=sub.add_parser('audit');a.add_argument('recording');a.add_argument('regions');a.add_argument('output');a.add_argument('--interval',type=float,default=120);a.add_argument('--pixel-checks',type=int,default=8)
    r=sub.add_parser('recover');r.add_argument('database');r.add_argument('job_id');r.add_argument('output');r.add_argument('--interval',type=float,default=120)
    args=p.parse_args(argv)
    if args.command=='check':result=check(args.equity_db)
    elif args.command=='audit':result=audit(args.recording,args.regions,args.output,interval=args.interval,pixel_checks=args.pixel_checks)
    else:result=recover(args.database,args.job_id,args.interval,args.output)
    print(json.dumps(result,ensure_ascii=True,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
