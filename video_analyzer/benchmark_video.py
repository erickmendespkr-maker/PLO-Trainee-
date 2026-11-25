import tempfile,subprocess,time,json,os
from pathlib import Path
from plo5_session_export import render, frame_hashes
from offline_ingest_pts_audit import decoded_pts
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);source=root/'source.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=640x360:r=20:d=20','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(source)],check=True)
    pts=decoded_pts(source);p={'region':{'width':320,'height':360,'x':0,'y':0},'start_frame':20,'end_frame_inclusive':119}
    for preset in ['ultrafast','superfast','veryfast','fast']:
        import plo5_session_export as m
        original=m.command
        def replacement(args,timeout=180):
            if '-preset' in args:args=list(args);args[args.index('-preset')+1]=preset
            return original(args,timeout)
        m.command=replacement
        out=root/(preset+'.mp4');t=time.perf_counter();r=render(source,out,p,pts);print(json.dumps({'preset':preset,'seconds':time.perf_counter()-t,'bytes':out.stat().st_size,'frames':r['frames'],'verified':r['decoded_yuv420p_pixels_match']}),flush=True)
        m.command=original
