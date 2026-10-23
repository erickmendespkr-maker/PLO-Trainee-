"""Add a clearly labelled human-review end card to OFFLINE PLO review MP4s.

Consumes only the neutral, manually selected export manifest. Original footage
is left untouched; the explanation is displayed on a separate end card, not
superimposed on poker actions. No OCR, equity, EV or error claims are made.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unicodedata

from video_segments import probe_video

STATUS = 'human_selected_neutral_review_clips_not_video_verified'
OUTPUT_STATUS = 'human_selected_neutral_review_annotated_no_ev'
FILENAME = re.compile(r'review_[0-9]{3}_table_[1-4]\.mp4\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
CARD_SECONDS = 4
CARD_WIDTH, CARD_HEIGHT = 960, 540


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _finite(value, name, low=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < low:
        raise ValueError('Invalid ' + name)
    return float(value)


def _caption(clip):
    explanation = clip['explanation']
    if (not isinstance(explanation, str) or not explanation.strip()
            or len(explanation) > 700
            or any(unicodedata.category(c) in ('Cc', 'Cf') for c in explanation)):
        raise ValueError('Invalid human explanation for end card')
    lines = [
        'REVISÃO HUMANA — SEM CONCLUSÃO DE ERRO',
        f'Mesa {clip["table_id"]} · evento {clip["event_index"]} · '
        f'ação {clip["reviewed_action"]} · PTS {clip["decision_timestamp"]:.2f}s',
        'Equity/EV NÃO verificados; hipótese humana, não diagnóstico.',
        '',
    ]
    lines += textwrap.wrap(' '.join(explanation.split()), width=66,
                           break_long_words=True, break_on_hyphens=False)
    if len(lines) > 15:
        raise ValueError('Explanation too long for legible end card')
    return '\n'.join(lines) + '\n'


def _validate_manifest(manifest, clips_dir):
    if (not isinstance(manifest, dict) or manifest.get('analysis_status') != STATUS
            or manifest.get('ready_for_equity_or_ev') is not False
            or manifest.get('authorized_for_ev_based_ranking') is not False
            or manifest.get('source_visual_content_verified') is not False):
        raise ValueError('Only unverified neutral human review clips are supported')
    clips = manifest.get('clips')
    if (not isinstance(clips, list) or not 1 <= len(clips) <= 20
            or type(manifest.get('clips_generated')) is not int
            or manifest['clips_generated'] != len(clips)):
        raise ValueError('Invalid clip count')
    for field in ('recording_sha256', 'source_queue_sha256',
                  'source_draft_sha256', 'source_selection_sha256'):
        if not isinstance(manifest.get(field), str) or not SHA.fullmatch(manifest[field]):
            raise ValueError('Invalid provenance hash: ' + field)
    seen = set()
    for clip in clips:
        if not isinstance(clip, dict):
            raise ValueError('Invalid clip metadata')
        filename = clip.get('filename')
        if (not isinstance(filename, str) or not FILENAME.fullmatch(filename)
                or filename in seen):
            raise ValueError('Unsafe or duplicate clip filename')
        seen.add(filename)
        if (type(clip.get('table_id')) is not int
                or not 1 <= clip['table_id'] <= 4
                or f'_table_{clip["table_id"]}.mp4' not in filename
                or type(clip.get('event_index')) is not int
                or clip['event_index'] < 0
                or clip.get('reviewed_action') not in ('fold', 'call', 'raise')):
            raise ValueError('Invalid reviewed decision')
        for name in ('start', 'decision_timestamp', 'end'):
            _finite(clip.get(name), name)
        if clip['end'] <= clip['start']:
            raise ValueError('Invalid clip interval')
        if not isinstance(clip.get('mp4_sha256'), str) or not SHA.fullmatch(clip['mp4_sha256']):
            raise ValueError('Invalid original MP4 hash')
        if type(clip.get('mp4_size_bytes')) is not int or clip['mp4_size_bytes'] <= 0:
            raise ValueError('Invalid original MP4 size')
        _caption(clip)
        original = clips_dir / filename
        if original.is_symlink() or not original.is_file():
            raise ValueError('Missing or symlinked original MP4')
        if (original.stat().st_size != clip['mp4_size_bytes']
                or _sha256(original) != clip['mp4_sha256']):
            raise ValueError('Original MP4 integrity mismatch')
        actual = probe_video(original)
        recorded = clip.get('decoded_output')
        if (not isinstance(recorded, dict)
                or actual['width'] != recorded.get('width')
                or actual['height'] != recorded.get('height')
                or abs(actual['duration'] - _finite(recorded.get('duration'), 'duration')) > .15):
            raise ValueError('Original MP4 metadata mismatch')
    return clips


def _render_card_clip(source, target, caption_path):
    filters = (
        '[0:v]scale=960:540:force_original_aspect_ratio=decrease,'
        'pad=960:540:(ow-iw)/2:(oh-ih)/2:color=black,'
        'fps=12,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v0];'
        '[1:v]drawtext=textfile=caption.txt:expansion=none:'
        'fontcolor=white:fontsize=24:line_spacing=7:x=42:y=45,'
        'format=yuv420p,setsar=1,setpts=PTS-STARTPTS[v1];'
        '[v0][v1]concat=n=2:v=1:a=0[v]'
    )
    command = [
        'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
        '-i', str(source.resolve()), '-f', 'lavfi', '-i',
        f'color=c=0x101820:s={CARD_WIDTH}x{CARD_HEIGHT}:r=12:d={CARD_SECONDS}',
        '-filter_complex', filters, '-map', '[v]', '-an', '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(target.resolve()),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=180,
                       cwd=caption_path.parent)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        raise ValueError('FFmpeg could not produce human-review end card') from exc


def annotate_review_clips(manifest_path, clips_dir, output_dir):
    """Produce a NEW atomic directory of annotated MP4s and an audit manifest."""
    manifest_path, clips_dir, output = map(Path, (manifest_path, clips_dir, output_dir))
    if (not manifest_path.is_file() or manifest_path.is_symlink()
            or not clips_dir.is_dir() or clips_dir.is_symlink()
            or output.exists() or output.is_symlink()
            or output.resolve().is_relative_to(clips_dir.resolve())):
        raise ValueError('Inputs must exist and output must be new/outside clips')
    source_manifest_sha256 = _sha256(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    clips = _validate_manifest(manifest, clips_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_annotated_', dir=output.parent) as temp:
        stage = Path(temp)
        results = []
        for clip in clips:
            source = clips_dir / clip['filename']
            caption = stage / 'caption.txt'
            caption.write_text(_caption(clip), encoding='utf-8')
            target = stage / clip['filename']
            _render_card_clip(source, target, caption)
            info = probe_video(target)
            if (info['width'] != CARD_WIDTH or info['height'] != CARD_HEIGHT
                    or abs(info['duration'] - (probe_video(source)['duration'] + CARD_SECONDS)) > .6):
                raise ValueError('Unexpected annotated MP4 dimensions or duration')
            if _sha256(source) != clip['mp4_sha256']:
                raise ValueError('Original MP4 changed during annotation')
            results.append({
                'filename': clip['filename'], 'table_id': clip['table_id'],
                'hand_id': clip['hand_id'], 'event_index': clip['event_index'],
                'original_mp4_sha256': clip['mp4_sha256'],
                'annotated_mp4_sha256': _sha256(target),
                'annotated_mp4_size_bytes': target.stat().st_size,
                'decoded_output': info, 'end_card_seconds': CARD_SECONDS,
                'annotation_type': 'separate_human_review_end_card',
                'explanation_source': 'human_authored_unverified',
            })
            caption.unlink()
        if _sha256(manifest_path) != source_manifest_sha256:
            raise ValueError('Original manifest changed during annotation')
        result = {
            'schema_version': 1, 'analysis_status': OUTPUT_STATUS,
            'source_manifest_sha256': source_manifest_sha256,
            'recording_sha256': manifest['recording_sha256'],
            'ready_for_equity_or_ev': False,
            'authorized_for_ev_based_ranking': False,
            'source_visual_content_verified': False,
            'clips_generated': len(results), 'clips': results,
            'warning': ('Human explanations are shown on separate end cards. '
                        'No visual/OCR evidence, equity, EV or strategic error is verified.'),
        }
        (stage / 'annotated_clip_manifest.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        if output.exists() or output.is_symlink():
            raise ValueError('Output directory already exists')
        stage.rename(output)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('clips_dir')
    parser.add_argument('output_dir')
    args = parser.parse_args(argv)
    result = annotate_review_clips(args.manifest, args.clips_dir, args.output_dir)
    print(json.dumps({'clips_generated': result['clips_generated'],
                      'analysis_status': result['analysis_status']}))


if __name__ == '__main__':
    main()
