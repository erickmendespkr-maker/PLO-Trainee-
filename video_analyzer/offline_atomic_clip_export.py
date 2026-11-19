"""Failure-safe offline batch publication of reviewed MP4 clips (not a GTO solver).

All clips are rendered into a private staging directory before any final clip is
published. Exclusive hard links prevent accidental overwrite, and a failure
rolls back only the files created by this invocation. This is not a guarantee
against power loss or other processes manipulating output files concurrently.
"""
import json
import os
from pathlib import Path
import tempfile
from offline_batch_clip_export import export_reviewed_clips


def export_atomic(video_path, plan_path, output_dir):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_stage_', dir=out) as scratch:
        stage = Path(scratch)
        manifest = export_reviewed_clips(video_path, plan_path, stage)
        names = [c['clip'] for c in manifest['clips']]
        if len(names) != len(set(names)) or any(Path(n).name != n or not n.endswith('.mp4') for n in names):
            raise ValueError('unsafe clip manifest')
        destinations = [out / n for n in names] + [out / 'clip_manifest.json']
        if any(p.exists() for p in destinations):
            raise FileExistsError('output already exists; refusing to overwrite')
        published = []
        try:
            # Hard links fail if the destination appears after preflight.
            # The manifest is published last, as the completion marker.
            for name in names:
                destination = out / name
                os.link(stage / name, destination)
                published.append(destination)
            destination = out / 'clip_manifest.json'
            os.link(stage / 'clip_manifest.json', destination)
            published.append(destination)
        except BaseException:
            for p in reversed(published):
                p.unlink(missing_ok=True)
            raise
    return manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Offline atomic export of reviewed clips')
    parser.add_argument('video')
    parser.add_argument('plan_json')
    parser.add_argument('output_dir')
    args = parser.parse_args()
    result = export_atomic(args.video, args.plan_json, args.output_dir)
    print(json.dumps({'clips': len(result['clips']), 'analysis_verified': False}))


if __name__ == '__main__':
    main()
