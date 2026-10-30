"""Build a synthetic MP4 example. Requires ffmpeg/ffprobe; never reads poker accounts."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

import offline_reviewed_hand_math_queue as q
import offline_reviewed_math_runner as runner
import offline_reviewed_math_clip_gallery as bridge
from test_offline_reviewed_hand_math_queue import fixture


def ff(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def dump(p, obj):
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main(destination):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    original = root / 'synthetic_source.mp4'
    ff('ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
       'testsrc2=size=320x180:rate=10:duration=30', '-an', '-c:v','libx264',
       '-preset','ultrafast','-pix_fmt','yuv420p',str(original))
    plan, ann = fixture()
    plan['source_video_sha256'] = q.digest(original)
    pp, ap, qp = (root / s for s in ('plan.json','annotations.json','queue.json'))
    dump(pp, plan)
    ann['source_plan_sha256'] = q.digest(pp)
    dump(ap, ann)
    queued = q.build(plan, ann, q.digest(pp), q.digest(ap))
    dump(qp, queued)
    workspace = root/'workspace'
    clips = workspace/'clips'
    clips.mkdir(parents=True)
    runner.run(pp,ap,qp,workspace/'math')
    clip_entries = []
    for entry in plan['clips']:
        hand = entry['hand_id']
        start = entry['start_seconds']
        duration = entry['end_seconds'] - start
        path = clips/(hand+'.mp4')
        ff('ffmpeg','-hide_banner','-loglevel','error','-ss',str(start),'-i',str(original),
           '-t',str(duration),'-an','-c:v','libx264','-preset','ultrafast',
           '-pix_fmt','yuv420p',str(path))
        sha = q.digest(path)
        sidecar = {'schema_version':1,'analysis_status':'manually_selected_offline_clip',
                   'hand_id':hand,'start_seconds':start,'end_seconds':entry['end_seconds'],
                   'explanation':'Quadros artificiais FFmpeg, sem cartas ou decisões reais.',
                   'clip_sha256':sha,'source_video_sha256':q.digest(original),
                   'video_evidence_verified':False,
                   'automatic_clip_selection_authorized':False}
        dump(clips/(hand+'.mp4.json'),sidecar)
        clip_entries.append({'hand_id':hand,'file':hand+'.mp4',
                             'clip_sha256':sha,'sidecar':hand+'.mp4.json',
                             'source_table_id':entry['table_id']})
        probe = subprocess.check_output(['ffprobe','-v','error','-show_entries',
                'format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],text=True)
        assert abs(float(probe)-duration) <= 0.2, (hand,probe,duration)
    dump(clips/'manifest.json', {'schema_version':1,
        'status':'human_reviewed_clips_not_verified_hands',
        'source_video_sha256':q.digest(original),
        'source_plan_sha256':q.digest(pp),
        'automatic_hand_detection':False,'equity_or_ev_calculated':False,
        'clips':clip_entries})
    summary = bridge.process(pp,ap,qp,workspace)
    verified = bridge.process(pp,ap,qp,workspace,verify=True)
    print(json.dumps({'summary':summary,'verified':verified,
                      'source_video_sha256':q.digest(original),
                      'ffprobe_clips':len(clip_entries)}))


if __name__ == '__main__':
    main(sys.argv[1])
