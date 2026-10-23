"""Append auditable, *hypothetical* math end cards to manually selected OFFLINE clips.

Recomputes the Monte Carlo report from source inputs, checks original MP4 hashes,
and writes only new files. Never diagnoses strategic mistakes or ranks hands.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unicodedata

from activity_math_explanation import build_explanations
from activity_review_clip_annotate import _validate_manifest, _sha256
from video_segments import probe_video

STATUS = 'human_selected_math_end_cards_hypothetical_unverified'
CARD_SECONDS = 8
WIDTH, HEIGHT = 960, 540


def _safe_lines(explanation):
    """Display only the revalidated explanation, never untrusted FFmpeg syntax."""
    lines = explanation['display_card_lines']
    if not isinstance(lines, list) or not 4 <= len(lines) <= 10:
        raise ValueError('Unexpected structured explanation')
    wrapped = []
    for line in lines:
        if (not isinstance(line, str) or len(line) > 250
                or any(unicodedata.category(ch) in ('Cc', 'Cf') for ch in line)):
            raise ValueError('Unsafe explanation text')
        wrapped.extend(textwrap.wrap(line, width=67, break_long_words=True,
                                     break_on_hyphens=False) or [''])
    if len(wrapped) > 16:
        raise ValueError('Explanation will not fit on end card')
    return '\n'.join(wrapped) + '\n'


def _render(source, destination, caption):
    """Keep original action footage separate from an 8-second explanatory card."""
    filters = (
        '[0:v]scale=960:540:force_original_aspect_ratio=decrease,'
        'pad=960:540:(ow-iw)/2:(oh-ih)/2:color=black,'
        'fps=12,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v0];'
        '[1:v]drawtext=textfile=math_caption.txt:expansion=none:'
        'fontcolor=white:fontsize=20:line_spacing=7:x=35:y=35,'
        'format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v1];'
        '[v0][v1]concat=n=2:v=1:a=0[v]'
    )
    command = [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', str(source.resolve()), '-f', 'lavfi', '-i',
        f'color=c=0x101820:s={WIDTH}x{HEIGHT}:r=12:d={CARD_SECONDS}',
        '-filter_complex', filters, '-map', '[v]', '-an', '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(destination.resolve()),
    ]
    try:
        subprocess.run(command, cwd=caption.parent, check=True,
                       capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        raise ValueError('FFmpeg could not render mathematical end card') from exc


def annotate_math_clips(manifest_path, clips_dir, worksheet_path,
                        request_path, report_path, output_dir):
    """Validate the entire provenance chain before and after encoding each MP4."""
    inputs = [Path(p) for p in (manifest_path, worksheet_path,
                                request_path, report_path)]
    clips_dir, output = Path(clips_dir), Path(output_dir)
    if (any(not p.is_file() or p.is_symlink() for p in inputs)
            or not clips_dir.is_dir() or clips_dir.is_symlink()
            or output.exists() or output.is_symlink()
            or output.resolve().is_relative_to(clips_dir.resolve())
            or any(p.resolve().is_relative_to(output.resolve())
                   for p in inputs)):
        raise ValueError('Inputs must be regular and output new/outside input directories')
    source_hashes = [_sha256(p) for p in inputs]
    manifest, worksheet, request, report = [
        json.loads(p.read_text(encoding='utf-8')) for p in inputs]
    # Replays the seeded mathematical model and checks all clip/decision bindings.
    explanations = build_explanations(manifest, clips_dir, worksheet, request, report)
    originals = _validate_manifest(manifest, clips_dir)
    if len(explanations['clips']) != len(originals):
        raise ValueError('Clip count mismatch')
    by_name = {item['filename']: item for item in explanations['clips']}
    if len(by_name) != len(originals):
        raise ValueError('Duplicate explanation filename')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_math_cards_', dir=output.parent) as temp:
        stage = Path(temp)
        rendered = []
        for clip in originals:
            name = clip['filename']
            item = by_name[name]
            if (item['original_mp4_sha256'] != clip['mp4_sha256']
                    or item['strategic_error_established'] is not False
                    or item['eligible_for_ev_ranking'] is not False
                    or item['video_evidence_verified'] is not False):
                raise ValueError('Unverified original clip/explanation mismatch')
            source = clips_dir / name
            caption = stage / 'math_caption.txt'
            caption.write_text(_safe_lines(item), encoding='utf-8')
            target = stage / name
            _render(source, target, caption)
            info = probe_video(target)
            original_info = probe_video(source)
            if (info['width'] != WIDTH or info['height'] != HEIGHT
                    or abs(info['duration'] - original_info['duration'] - CARD_SECONDS) > .7):
                raise ValueError('Unexpected rendered MP4 duration/dimensions')
            if _sha256(source) != clip['mp4_sha256']:
                raise ValueError('Original clip modified during render')
            rendered.append({
                'filename': name, 'table_id': item['table_id'],
                'hand_id': item['hand_id'], 'event_index': item['event_index'],
                'original_mp4_sha256': clip['mp4_sha256'],
                'annotated_mp4_sha256': _sha256(target),
                'annotated_mp4_size_bytes': target.stat().st_size,
                'decoded_output': info,
                'math_card_seconds': CARD_SECONDS,
                'math_status': ('conditional_heads_up_all_in_what_if_only'
                                if item['conditional_result'] is not None
                                else 'no_hypothetical_calculation'),
                'strategic_error_established': False,
            })
            caption.unlink()
        if [_sha256(p) for p in inputs] != source_hashes:
            raise ValueError('Source JSON modified during rendering')
        result = {
            'schema_version': 1, 'analysis_status': STATUS,
            'source_manifest_file_sha256': source_hashes[0],
            'source_worksheet_file_sha256': source_hashes[1],
            'source_request_file_sha256': source_hashes[2],
            'source_report_file_sha256': source_hashes[3],
            'recording_sha256': manifest['recording_sha256'],
            'ready_for_equity_or_ev': False,
            'authorized_for_ev_based_ranking': False,
            'source_visual_content_verified': False,
            'clips_generated': len(rendered), 'clips': rendered,
            'warning': ('End cards show manually reviewed observations and hypothetical '
                        'Monte Carlo only. Opponent ranges and real-hand EV are NOT '
                        'verified. No strategic-error diagnosis or automatic ranking.'),
        }
        (stage / 'math_clip_manifest.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        (stage / 'math_explanations.json').write_text(
            json.dumps(explanations, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        if output.exists() or output.is_symlink():
            raise ValueError('Output already exists')
        stage.rename(output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('clip_manifest_json', 'clips_dir', 'worksheet_json',
                 'request_json', 'hypothetical_report_json', 'output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = annotate_math_clips(args.clip_manifest_json, args.clips_dir,
                                 args.worksheet_json, args.request_json,
                                 args.hypothetical_report_json, args.output_dir)
    print(json.dumps({'clips_generated': result['clips_generated'],
                      'analysis_status': STATUS, 'ev_ranking_authorized': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
