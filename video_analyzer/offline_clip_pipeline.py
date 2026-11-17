"""Offline-only candidate clip rendering with fail-closed FFprobe audit.

Rendering does not verify poker hands, source PTS or strategic analysis.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from offline_clip_manifest import build_clip_manifest, ffmpeg_clip_arguments
from offline_clip_render_audit import probe_video, audit_render


def render_candidates(video_path, output_dir, proposals, *, padding_seconds=2.0,
                      max_tables=4, timeout_seconds=120):
    """Render candidate intervals, never treating them as confirmed hands."""
    source = Path(video_path).resolve(strict=True)
    target = Path(output_dir).resolve()
    if not source.is_file() or source.suffix.lower() not in ('.mp4', '.webm'):
        raise ValueError('expected local MP4/WebM recording')
    if source == target or source in target.parents:
        raise ValueError('output directory cannot be within input file')
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValueError('invalid timeout')
    metadata = probe_video(str(source))
    try:
        duration = float(metadata['format']['duration'])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError('invalid source duration') from exc
    digest = hashlib.sha256()
    with source.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            digest.update(chunk)
    manifest = build_clip_manifest(digest.hexdigest(), duration, proposals,
                                   padding_seconds=padding_seconds, max_tables=max_tables)
    # Fail before writing anything if a previous report or candidate exists.
    report_path = target / 'candidate_clip_report.json'
    if report_path.exists():
        raise FileExistsError('refusing to overwrite report')
    planned_outputs = [target / (clip['clip_id'] + '.mp4') for clip in manifest['clips']]
    for output in planned_outputs:
        if output.exists():
            raise FileExistsError('refusing to overwrite clip: ' + str(output))
    target.mkdir(parents=True, exist_ok=True)
    results = []
    created_outputs = []
    try:
        for clip in manifest['clips']:
            output = target / (clip['clip_id'] + '.mp4')
            argv = ffmpeg_clip_arguments(str(source), str(output), clip)
            argv[argv.index('-y')] = '-n'
            try:
                subprocess.run(argv, check=True, capture_output=True, timeout=timeout_seconds)
                created_outputs.append(output)
                audit = audit_render(clip, probe_video(str(output)))
                results.append({'clip': clip, 'file': output.name, 'audit': audit})
            except Exception:
                output.unlink(missing_ok=True)
                raise
        report = {'schema_version': 1, 'video_sha256': digest.hexdigest(),
                  'status': 'candidate_clips_only', 'results': results}
        # Exclusive create: never overwrite a report created concurrently.
        with report_path.open('x', encoding='utf-8') as fh:
            fh.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
        return report
    except Exception:
        for output in created_outputs:
            output.unlink(missing_ok=True)
        raise
