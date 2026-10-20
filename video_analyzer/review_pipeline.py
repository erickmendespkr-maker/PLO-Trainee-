"""Offline human-reviewed video -> cropped MP4 clips + provenance JSON.

This deliberately does not detect tables, infer hands, or claim strategic errors.
"""
import json
from dataclasses import asdict
from pathlib import Path
from clip_planner import ReviewCandidate, select_clips
from table_regions import Region, validate_regions
from table_crop import crop_table_clip
from video_segments import probe_video


def run_review_pipeline(video_path, manifest_path, output_dir):
    """Run only on explicitly provided recorded video and annotation manifest.

    Manifest: {"regions": [{table_id,x,y,width,height}], "candidates":
    [{table_id,hand_id,decision_time,impact_estimate,confidence,explanation,hypotheses}]}
    """
    video_path = Path(video_path)
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    if not video_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError('Video and manifest must exist')
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    info = probe_video(video_path)
    if info['duration'] <= 0:
        raise ValueError('Invalid video duration')
    regions = [Region(**item) for item in data['regions']]
    validate_regions(regions, info['width'], info['height'])
    region_by_id = {r.table_id: r for r in regions}
    candidates = [ReviewCandidate(**item) for item in data['candidates']]
    clips = select_clips(candidates, video_duration=info['duration'],
                         min_confidence=data.get('min_confidence', .75),
                         max_clips=data.get('max_clips', 10))
    for clip in clips:
        if clip['table_id'] not in region_by_id:
            raise ValueError(f"No region for table {clip['table_id']}")
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for index, clip in enumerate(clips, start=1):
        filename = f"review_{index:03d}_table_{clip['table_id']}.mp4"
        crop_table_clip(video_path, output_dir / filename,
                        region_by_id[clip['table_id']], info['width'], info['height'],
                        clip['start'], clip['end'])
        generated.append({**clip, 'filename': filename})
    result = {'schema_version': 1, 'analysis_status': 'manual_annotations_only',
              'video': {'filename': video_path.name, **info},
              'regions': [asdict(r) for r in regions], 'clips': generated}
    (output_dir / 'review_manifest.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', help='Recorded MP4/WebM input')
    parser.add_argument('annotations', help='Human-reviewed JSON annotations')
    parser.add_argument('output_dir', help='Directory for MP4 clips and metadata')
    args = parser.parse_args()
    print(json.dumps(run_review_pipeline(args.video, args.annotations, args.output_dir), indent=2))
