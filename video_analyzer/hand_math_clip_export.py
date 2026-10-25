"""Human-selected offline MP4 clips with explicit *hypothetical* PLO5/PLO6 end cards.

This is a bridge from the Cycle 95–97 mathematical intake/report to the
existing FFmpeg table cropper and end-card renderer. No live poker, automatic
EV ranking, visual truth claims, or automatic diagnosis of strategic errors.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unicodedata

from activity_math_clip_annotate import _render, _safe_lines, CARD_SECONDS, WIDTH, HEIGHT
from hand_math_scenario_run import _load, run
from table_crop import crop_table_clip
from table_regions import Region, validate_regions
from video_segments import probe_video
from video_validator import validate_recording

STATUS = 'human_selected_hypothetical_math_clips_no_video_verification'
MAX_CLIPS = 8
MAX_SECONDS = 45.0
MAX_NOTE = 180
_REGION = {'table_id', 'x', 'y', 'width', 'height'}
_CLIP = {'entry_id', 'table_id', 'timestamp', 'start', 'end', 'reviewer_approved', 'reviewer_note'}
_SELECTION = {'schema_version', 'analysis_status', 'recording_sha256',
              'source_intake_sha256', 'source_filled_sha256', 'source_math_sha256',
              'regions_human_confirmed', 'regions', 'clips'}


def _sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _num(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid ' + name)
    return float(value)


def _verify_sources(video, intake, filled, result, intake_raw, filled_raw, math_raw):
    video_path = Path(video)
    if video_path.is_symlink() or not video_path.is_file():
        raise ValueError('Recording must be a regular file')
    info = validate_recording(video_path)
    video_hash = _sha_file(video_path)
    intake_hash = hashlib.sha256(intake_raw).hexdigest()
    filled_hash = hashlib.sha256(filled_raw).hexdigest()
    math_hash = hashlib.sha256(math_raw).hexdigest()
    if intake.get('recording_sha256') != video_hash:
        raise ValueError('Intake does not refer to these recording bytes')
    if result != run(intake, filled, intake_hash):
        raise ValueError('Mathematical results differ from seeded recomputation')
    return info, (video_hash, intake_hash, filled_hash, math_hash)


def template(video, intake, filled, result, intake_raw, filled_raw, math_raw):
    """Create a deliberately unapproved JSON request; never select clips implicitly."""
    info, hashes = _verify_sources(video, intake, filled, result, intake_raw, filled_raw, math_raw)
    clips = []
    for task, edited, math in zip(intake['tasks'], filled['tasks'], result['results']):
        if math['status'] != 'hypothetical_only_not_video_verified':
            continue
        stamp = edited['manual_scenario_draft']['timestamp']
        if not 0 <= stamp < info['duration_seconds']:
            continue
        clips.append({'entry_id': task['entry_id'], 'table_id': task['table_id'],
                      'timestamp': stamp, 'start': max(0, stamp - 2),
                      'end': min(info['duration_seconds'], stamp + 3),
                      'reviewer_approved': False, 'reviewer_note': ''})
    return {'schema_version': 1, 'analysis_status': STATUS,
            'recording_sha256': hashes[0], 'source_intake_sha256': hashes[1],
            'source_filled_sha256': hashes[2], 'source_math_sha256': hashes[3],
            'regions_human_confirmed': False, 'regions': [],
            'clips': clips[:MAX_CLIPS]}


def plan(video, intake, filled, result, selection, intake_raw, filled_raw, math_raw):
    """Fail closed on changed sources, table regions, timing, or human approval."""
    info, hashes = _verify_sources(video, intake, filled, result, intake_raw, filled_raw, math_raw)
    if (type(selection) is not dict or set(selection) != _SELECTION or
            type(selection['schema_version']) is not int or selection['schema_version'] != 1 or
            selection['analysis_status'] != STATUS or
            selection['regions_human_confirmed'] is not True or
            [selection[k] for k in ('recording_sha256', 'source_intake_sha256',
                                    'source_filled_sha256', 'source_math_sha256')] != list(hashes)):
        raise ValueError('Unapproved selection or source SHA-256 mismatch')
    regions = selection['regions']
    if type(regions) is not list or not 1 <= len(regions) <= 4:
        raise ValueError('Require 1–4 manually approved regions')
    parsed = []
    for r in regions:
        if type(r) is not dict or set(r) != _REGION or any(type(v) is not int for v in r.values()):
            raise ValueError('Invalid region coordinates')
        if not 1 <= r['table_id'] <= 4:
            raise ValueError('Invalid table ID')
        parsed.append(Region(**r))
    validate_regions(parsed, info['width'], info['height'])
    by_region = {r.table_id: r for r in parsed}
    choices = selection['clips']
    if type(choices) is not list or not 1 <= len(choices) <= MAX_CLIPS:
        raise ValueError('Require 1–8 explicit selections')
    by_task = {(t['entry_id'], t['table_id']): (t, f, m)
               for t, f, m in zip(intake['tasks'], filled['tasks'], result['results'])}
    seen, validated = set(), []
    for choice in choices:
        if type(choice) is not dict or set(choice) != _CLIP:
            raise ValueError('Invalid selection fields')
        key = (choice['entry_id'], choice['table_id'])
        if (type(key[0]) is not str or type(key[1]) is not int or
                key not in by_task or key in seen or key[1] not in by_region):
            raise ValueError('Unknown, repeated or unconfigured hand')
        seen.add(key)
        task, edited, math = by_task[key]
        if math['status'] != 'hypothetical_only_not_video_verified':
            raise ValueError('Clip must reference a calculated hypothetical scenario')
        if (math.get('strategic_error_established') is not False or
                math.get('automatic_clip_selection_authorized') is not False or
                math.get('source_hand_reconstruction_verified') is not False):
            raise ValueError('Cannot promote hypothetical math to verified analysis')
        stamp = _num(choice['timestamp'], 'timestamp')
        start = _num(choice['start'], 'start')
        end = _num(choice['end'], 'end')
        if (abs(stamp - edited['manual_scenario_draft']['timestamp']) > 1e-6 or
                not task['span_seconds'][0] <= stamp <= task['span_seconds'][1] or
                not start <= stamp < end <= info['duration_seconds'] + 1e-6 or
                not 0.5 <= end - start <= MAX_SECONDS):
            raise ValueError('Clip timing does not match manual decision')
        note = choice['reviewer_note']
        if (choice['reviewer_approved'] is not True or type(note) is not str or
                not 5 <= len(note.strip()) <= MAX_NOTE or
                any(unicodedata.category(c) in ('Cc', 'Cf') for c in note)):
            raise ValueError('Explicit safe human approval and note required')
        validated.append({'entry_id': key[0], 'table_id': key[1], 'timestamp': stamp,
                          'start': start, 'end': end, 'reviewer_note': note.strip(),
                          'math': math, 'region': by_region[key[1]],
                          'fold_probability': edited['manual_scenario_draft']['fold_probability']})
    return {'video_info': info, 'source_hashes': hashes, 'clips': validated}


def _caption(item):
    math = item['math']
    low, high = math['equity_sampling_ci95']
    ev_low, ev_high = math['ev_sampling_ci95']
    return _safe_lines({'display_card_lines': [
        'PLO Trainee | Revisão offline selecionada por pessoa',
        f'Mesa {item["table_id"]} | {item["entry_id"][:60]} | PTS {item["timestamp"]:.3f}s',
        f'{math["variant"]} | Ação assumida: {math["observed_action_assumed"]}',
        f'Equity: {100*math["equity"]:.2f}% | IC95 amostragem: {100*low:.2f}% a {100*high:.2f}%',
        f'EV vs fold=0: {math["ev_vs_fold_zero"]:.2f} | IC95: {ev_low:.2f} a {ev_high:.2f} fichas',
        f'Monte Carlo: {math["trials"]} simulações | semente: {math["seed"]}',
        f'Range: {math["opponent_range_combinations"]} combinações hipotéticas; fold: '
        + ('não aplicável' if item['fold_probability'] is None else f'{item["fold_probability"]*100:.1f}% assumido'),
        'Modelo simplificado: heads-up all-in; sem rake, side pots ou apostas futuras.',
        'Nota do revisor: ' + item['reviewer_note'],
        'NÃO comprova erro estratégico nem reconstrói a mão automaticamente.',
    ]})


def export(video_path, intake_path, filled_path, math_path, selection_path, output_dir):
    """Recompute, crop, append explanatory cards, verify output, publish new folder."""
    sources = list(map(Path, (intake_path, filled_path, math_path, selection_path)))
    video, output = Path(video_path), Path(output_dir)
    if (output.exists() or output.is_symlink() or
            any(not p.is_file() or p.is_symlink() for p in sources) or
            any(output.resolve() == p.resolve() for p in sources + [video]) or
            output.resolve().is_relative_to(video.resolve())):
        raise ValueError('Sources must be regular files and output a new directory')
    documents, raws = zip(*[_load(p) for p in sources])
    intake, filled, math, selection = documents
    checked = plan(video, intake, filled, math, selection, *raws[:3])
    initial_video_hash = checked['source_hashes'][0]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_hand_math_clips_', dir=output.parent) as temporary:
        stage = Path(temporary)
        generated = []
        for index, item in enumerate(checked['clips'], 1):
            raw_clip = stage / f'_crop_{index:03d}.mp4'
            filename = f'hand_math_{index:03d}_table_{item["table_id"]}.mp4'
            target = stage / filename
            region = item['region']
            crop_table_clip(video, raw_clip, region,
                            checked['video_info']['width'], checked['video_info']['height'],
                            item['start'], item['end'])
            decoded = probe_video(raw_clip)
            if (decoded['width'] != region.width or decoded['height'] != region.height or
                    not 0 < decoded['duration'] <= item['end'] - item['start'] + .5):
                raise ValueError('Unexpected cropped video dimensions/duration')
            caption = stage / 'math_caption.txt'
            caption.write_text(_caption(item), encoding='utf-8')
            _render(raw_clip, target, caption)
            annotated = probe_video(target)
            if (annotated['width'] != WIDTH or annotated['height'] != HEIGHT or
                    abs(annotated['duration'] - decoded['duration'] - CARD_SECONDS) > .7):
                raise ValueError('Unexpected annotated video dimensions/duration')
            raw_clip.unlink()
            caption.unlink()
            math = item['math']
            generated.append({'filename': filename, 'entry_id': item['entry_id'],
                              'table_id': item['table_id'], 'decision_pts_seconds': item['timestamp'],
                              'clip_start_seconds': item['start'], 'clip_end_seconds': item['end'],
                              'reviewer_note': item['reviewer_note'],
                              'mp4_sha256': _sha_file(target), 'size_bytes': target.stat().st_size,
                              'decoded_output': annotated, 'math_status': math['status'],
                              'equity_sampling_ci95': math['equity_sampling_ci95'],
                              'ev_sampling_ci95': math['ev_sampling_ci95'],
                              'hypothetical_equity': math['equity'],
                              'opponent_range_combinations': math['opponent_range_combinations'],
                              'fold_probability_assumed': item['fold_probability'],
                              'hypothetical_ev_vs_fold_zero': math['ev_vs_fold_zero'],
                              'strategic_error_established': False,
                              'video_hand_reconstruction_verified': False})
        if (_sha_file(video) != initial_video_hash or
                any(p.read_bytes() != raw for p, raw in zip(sources, raws))):
            raise ValueError('Inputs changed while generating clips')
        manifest = {'schema_version': 1, 'analysis_status': STATUS,
                    'recording_sha256': initial_video_hash,
                    'source_intake_sha256': checked['source_hashes'][1],
                    'source_filled_sha256': checked['source_hashes'][2],
                    'source_math_sha256': checked['source_hashes'][3],
                    'source_selection_sha256': hashlib.sha256(raws[3]).hexdigest(),
                    'clips_generated': len(generated), 'clips': generated,
                    'automatic_clip_selection_authorized': False,
                    'strategic_error_established': False,
                    'hand_reconstruction_verified': False,
                    'warning': 'Seleção humana; equity e EV hipotéticos. Nenhum erro comprovado.'}
        (stage / 'hand_math_clip_manifest.json').write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
            encoding='utf-8')
        if output.exists() or output.is_symlink():
            raise ValueError('Output already exists')
        stage.rename(output)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('template', 'export'):
        p = sub.add_parser(command)
        for name in ('video', 'intake', 'filled', 'math'):
            p.add_argument(name)
        if command == 'export':
            p.add_argument('selection')
        p.add_argument('output')
    args = parser.parse_args(argv)
    if args.command == 'template':
        paths = list(map(Path, (args.intake, args.filled, args.math)))
        docs, raws = zip(*[_load(p) for p in paths])
        request = template(args.video, *docs, *raws)
        target = Path(args.output)
        if target.exists() or target.is_symlink() or target.resolve() in [p.resolve() for p in paths]:
            raise ValueError('Template must be a new file')
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('x', encoding='utf-8') as f:
            json.dump(request, f, indent=2, ensure_ascii=False)
        print(json.dumps({'unapproved_candidates': len(request['clips']), 'output': str(target)}))
    else:
        result = export(args.video, args.intake, args.filled, args.math,
                        args.selection, args.output)
        print(json.dumps({'clips_generated': result['clips_generated'], 'output': args.output}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
