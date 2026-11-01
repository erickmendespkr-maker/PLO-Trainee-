"""Reproducible offline synthetic 1280x720 four-table pixel audit benchmark."""
from pathlib import Path
import json
import subprocess
import tempfile
import time
from offline_video_ingest_probe import build
from offline_ingest_roi_pixel_audit import verify as legacy_verify
from offline_ingest_roi_batch_pixel_audit import verify as batch_verify


def main():
    with tempfile.TemporaryDirectory(prefix='plo_batch_bench_') as tmp:
        root = Path(tmp)
        video = root / 'synthetic_720p_60s.mp4'
        boxes = ','.join(f'drawbox=x={x}:y={y}:w=640:h=360:color={c}:t=fill'
                         for x, y, c in [(0, 0, 'red'), (640, 0, 'green'),
                                         (0, 360, 'blue'), (640, 360, 'yellow')])
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=10:duration=60',
                        '-vf', boxes, '-c:v', 'mpeg4', '-q:v', '8', str(video)],
                       capture_output=True, check=True, timeout=120)
        regions = root / 'regions.json'
        regions.write_text(json.dumps({'tables': [
            {'table_id': i, 'x': x, 'y': y, 'width': 640, 'height': 360}
            for i, (x, y) in enumerate([(0, 0), (640, 0),
                                        (0, 360), (640, 360)], 1)]}))
        ingest = root / 'ingest'
        manifest = build(video, regions, ingest, interval_seconds=5)
        t0 = time.perf_counter()
        old = legacy_verify(video, ingest)
        legacy_seconds = time.perf_counter() - t0
        t1 = time.perf_counter()
        new = batch_verify(video, ingest)
        batch_seconds = time.perf_counter() - t1
        assert old['results'] == new['results']
        result = {'source': 'synthetic_testsrc2_four_colored_quadrants',
                  'video_resolution': '1280x720', 'duration_seconds': 60,
                  'frame_rate': 10, 'video_bytes': video.stat().st_size,
                  'tables': 4, 'samples': len(manifest['samples']),
                  'unique_frames': old['unique_source_frames_decoded'],
                  'legacy_seconds': round(legacy_seconds, 3),
                  'batch_seconds': round(batch_seconds, 3),
                  'speedup_observed': round(legacy_seconds / batch_seconds, 2),
                  'same_pixel_results': True,
                  'batch_ffmpeg_decode_passes': new['ffmpeg_decode_passes'],
                  'limitation': 'One synthetic local run; not a real-video or Windows benchmark.'}
        print(json.dumps(result, indent=2))
        return result

if __name__ == '__main__':
    main()
