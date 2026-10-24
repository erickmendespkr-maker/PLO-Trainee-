"""Conservative hand-transition review queue from Cycle 81 temporal OCR hints.

No hand is reconstructed or verified. All outputs require manual review and are
prohibited from feeding equity, EV or automatic clip selection.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_CARD = re.compile(r'[2-9TJQKA][cdhs]\Z')
_FIELDS = {'board', 'hero_cards', 'pot', 'bet'}
_UNCERTAIN = {'decoded_pts_unverified', 'duplicate_decoded_pts_ambiguous',
              'ocr_uncertain_or_unparsed', 'nonmonotonic_decoded_pts',
              'gap_exceeds_comparison_window'}


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _digest(value):
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _cards(value, field):
    count = (5, 6) if field == 'hero_cards' else (3, 4, 5)
    return (isinstance(value, list) and len(value) in count
            and all(isinstance(card, str) and _CARD.fullmatch(card) for card in value)
            and len(set(value)) == len(value))


def _validate(report):
    if (not isinstance(report, dict) or type(report.get('schema_version')) is not int
            or report['schema_version'] != 1
            or report.get('analysis_status') != 'unverified_temporal_ocr_review_hints'
            or not _digest(report.get('recording_sha256'))
            or not _digest(report.get('roi_profile_sha256'))
            or report.get('requires_manual_review') is not True
            or any(report.get(key) is not False for key in (
                'hand_boundaries_verified', 'cards_or_actions_verified',
                'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                'strategic_error_established'))):
        raise ValueError('Invalid or falsely authoritative temporal report')
    sources = report.get('source_report_sha256s')
    items = report.get('review_items')
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 64
            or any(not _digest(s) for s in sources)
            or not isinstance(items, list) or len(items) > 4096):
        raise ValueError('Invalid source provenance or item budget')
    for item in items:
        if (not isinstance(item, dict) or type(item.get('table_id')) is not int
                or item['table_id'] not in (1, 2, 3, 4)
                or item.get('field') not in _FIELDS
                or item.get('requires_manual_review') is not True):
            raise ValueError('Invalid review item')
        kind = item.get('kind')
        if kind == 'possible_visual_value_change':
            a, b = item.get('from_decoded_pts_seconds'), item.get('at_decoded_pts_seconds')
            if not _number(a) or not _number(b) or b <= a:
                raise ValueError('Invalid change window')
            old, new = item.get('from_candidate'), item.get('to_candidate')
            if item['field'] in ('board', 'hero_cards'):
                if not _cards(old, item['field']) or not _cards(new, item['field']):
                    raise ValueError('Invalid card candidates')
            elif not _number(old) or not _number(new):
                raise ValueError('Invalid amount candidates')
            if old == new:
                raise ValueError('No actual OCR change')
            evidence = item.get('source_evidence')
            if (not isinstance(evidence, list) or len(evidence) != 2
                    or any(not isinstance(e, dict) or not _digest(e.get('report_sha256'))
                           or e['report_sha256'] not in sources
                           or type(e.get('candidate_index')) is not int
                           or e['candidate_index'] < 0
                           or not _digest(e.get('roi_sha256')) for e in evidence)
                    or len({(e['report_sha256'], e['candidate_index']) for e in evidence}) != 2):
                raise ValueError('Invalid change evidence')
        elif kind in _UNCERTAIN:
            pts = item.get('at_decoded_pts_seconds')
            if pts is not None and not _number(pts):
                raise ValueError('Invalid uncertainty timestamp')
            if kind == 'gap_exceeds_comparison_window':
                a = item.get('from_decoded_pts_seconds')
                if not _number(a) or not _number(pts) or pts <= a:
                    raise ValueError('Invalid gap interval')
        else:
            raise ValueError('Unknown review kind')
    counts = report.get('counts')
    if (not isinstance(counts, dict) or type(counts.get('review_items')) is not int
            or counts['review_items'] != len(items)
            or type(counts.get('possible_changes')) is not int
            or counts['possible_changes'] != sum(x['kind'] == 'possible_visual_value_change' for x in items)):
        raise ValueError('Inconsistent upstream counts')
    return items


def build_ocr_boundary_triage(temporal_report, *, source_sha256=None, max_windows=2048):
    """Build candidate *review windows*, never verified hand boundaries."""
    if source_sha256 is not None and not _digest(source_sha256):
        raise ValueError('Invalid temporal report SHA-256')
    if type(max_windows) is not int or not 1 <= max_windows <= 2048:
        raise ValueError('Invalid window budget')
    items = _validate(temporal_report)
    windows = defaultdict(list)
    uncertainties = defaultdict(list)
    for index, item in enumerate(items):
        if item['kind'] == 'possible_visual_value_change':
            key = (item['table_id'], item['from_decoded_pts_seconds'],
                   item['at_decoded_pts_seconds'])
            windows[key].append((index, item))
        else:
            uncertainties[item['table_id']].append((index, item))
    if len(windows) > max_windows:
        raise ValueError('Window budget exceeded')
    candidates = []
    for (table, start, end), changes in sorted(windows.items()):
        signals = []
        field_counts = defaultdict(int)
        for index, item in changes:
            field = item['field']
            old, new = item['from_candidate'], item['to_candidate']
            if field == 'hero_cards':
                kind = 'private_cards_changed_candidate'
            elif field == 'board':
                # Ordinary flop -> turn -> river extension is not a new hand.
                if len(new) > len(old) and new[:len(old)] == old:
                    continue
                kind = 'board_nonextension_candidate'
            elif field == 'pot' and new < old:
                kind = 'pot_decrease_context_only'
            else:
                continue
            field_counts[field] += 1
            signals.append({'kind': kind, 'field': field, 'review_item_index': index,
                            'source_evidence': item['source_evidence']})
        strong = [s for s in signals if s['field'] in ('hero_cards', 'board')]
        if not strong:
            continue  # Pot fluctuations alone never suggest a hand transition.
        flags = ['conflicting_same_field_hints'] if any(n > 1 for n in field_counts.values()) else []
        for index, uncertain in uncertainties[table]:
            pts = uncertain.get('at_decoded_pts_seconds')
            if pts is not None and start <= pts <= end:
                flags.append('uncertain_ocr_or_timing_inside_window')
                break
        corroborated = (len({s['field'] for s in strong}) >= 2 or
                        any(s['kind'] == 'pot_decrease_context_only' for s in signals))
        candidates.append({
            'table_id': table, 'review_window_start_seconds': start,
            'review_window_end_seconds': end,
            'kind': 'possible_hand_transition_for_manual_review_only',
            'priority': 'review_first' if corroborated and not flags else 'review',
            'signals': signals, 'ambiguity_flags': flags,
            'requires_manual_review': True, 'hand_boundary_verified': False,
        })
    return {
        'schema_version': 1, 'analysis_status': 'unverified_ocr_hand_transition_review_queue',
        'recording_sha256': temporal_report['recording_sha256'],
        'roi_profile_sha256': temporal_report['roi_profile_sha256'],
        'source_temporal_report_sha256': source_sha256,
        'source_ocr_report_sha256s': temporal_report['source_report_sha256s'],
        'review_windows': candidates,
        'counts': {'review_windows': len(candidates),
                   'review_first': sum(x['priority'] == 'review_first' for x in candidates)},
        'requires_manual_review': True, 'hand_boundaries_verified': False,
        'cards_or_actions_verified': False, 'ready_for_equity_or_ev': False,
        'automatic_clip_selection_authorized': False,
        'strategic_error_established': False,
        'warning': 'OCR change windows are not hand boundaries. Human annotation and video validation required.',
    }


def export_ocr_boundary_triage(input_json, output_json, *, max_windows=2048):
    source, output = Path(input_json), Path(output_json)
    if (source.is_symlink() or not source.is_file() or output.exists() or output.is_symlink()
            or source.resolve() == output.resolve()):
        raise ValueError('Require a regular input and new output')
    original_sha = _sha256(source)
    report = json.loads(source.read_text(encoding='utf-8'))
    result = build_ocr_boundary_triage(report, source_sha256=original_sha,
                                       max_windows=max_windows)
    if _sha256(source) != original_sha:
        raise ValueError('Input changed during processing')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent,
                                         prefix='.plo_boundary_', suffix='.json',
                                         delete=False) as stream:
            stage = Path(stream.name)
            json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write('\n')
        os.link(stage, output)  # Atomic, refuses overwrite including symlinks.
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('temporal_ocr_json')
    parser.add_argument('--output', required=True)
    parser.add_argument('--max-windows', type=int, default=2048)
    args = parser.parse_args(argv)
    result = export_ocr_boundary_triage(args.temporal_ocr_json, args.output,
                                        max_windows=args.max_windows)
    print(json.dumps(result['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
