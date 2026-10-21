"""Export nominally timestamped image evidence from recorded videos."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import tempfile
from table_regions import Region, grid_regions, validate_regions
from video_segments import _run
from video_validator import validate_recording

def export_evidence(video_path, output_dir, *, regions=None,
                    interval_seconds=30, max_frames_per_table=150):
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds,(int,float)) or not math.isfinite(interval_seconds) or interval_seconds <= 0:
        raise ValueError('interval_seconds must be finite and positive')
    if isinstance(max_frames_per_table,bool) or not isinstance(max_frames_per_table,int) or not 1 <= max_frames_per_table <= 10000:
        raise ValueError('max_frames_per_table must be an integer 1..10000')
    video_path = Path(video_path)
    metadata = validate_recording(video_path)
    width,height = metadata['width'],metadata['height']
    if regions is None:
        regions = grid_regions(width,height)
    else:
        if not isinstance(regions,(list,tuple)) or not 1 <= len(regions) <= 4:
            raise ValueError('Provide 1..4 table regions')
        regions = list(regions)
    validate_regions(regions,width,height)
    if any(not isinstance(r,Region) or isinstance(r.table_id,bool) or not 1 <= r.table_id <= 4 for r in regions):
        raise ValueError('Invalid table region IDs')
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError('Output directory already exists')
    output_dir.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='plo_evidence_',dir=output_dir.parent) as tmp:
        tmpdir = Path(tmp)
        n = len(regions)
        labels = ''.join(f'[in{i}]' for i in range(n))
        filters = [f'[0:v]fps=1/{interval_seconds},split={n}{labels}']
        for i,region in enumerate(regions):
            filters.append(f'[in{i}]crop={region.width}:{region.height}:{region.x}:{region.y}[out{i}]')
        cmd = ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
               '-i',str(video_path),'-filter_complex',';'.join(filters)]
        for i,region in enumerate(regions):
            table_dir = tmpdir / f'table_{region.table_id:02d}'
            table_dir.mkdir()
            cmd.extend(['-map',f'[out{i}]','-frames:v',str(max_frames_per_table),
                        '-threads:v','1','-start_number','0',str(table_dir/'frame_%05d.png')])
        _run(cmd)
        frames = []
        for region in regions:
            table_dir = tmpdir / f'table_{region.table_id:02d}'
            for index,path in enumerate(sorted(table_dir.glob('frame_*.png'))):
                frames.append({'table_id':region.table_id,
                               'nominal_timestamp_seconds':index*float(interval_seconds),
                               'image':f'{table_dir.name}/{path.name}',
                               'status':'unverified_visual_evidence'})
        if not frames:
            raise RuntimeError('FFmpeg produced no frames')
        report = {'schema_version':1,'analysis_status':'unverified_visual_evidence_only',
                  'recording':{'filename':video_path.name,**metadata},
                  'regions':[asdict(r) for r in regions],
                  'interval_seconds':float(interval_seconds),
                  'timestamp_semantics':'nominal_sampling_grid_not_exact_source_pts',
                  'requires_manual_review':True,'frames':frames,
                  'warning':'Frames do not establish poker cards, actions or hand boundaries.'}
        (tmpdir/'manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        tmpdir.rename(output_dir)
    return report
