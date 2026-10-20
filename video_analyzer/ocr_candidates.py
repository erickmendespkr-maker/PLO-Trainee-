"""Strict OCR *candidates* from recorded poker videos; never confirmed facts.

Requires manual ROI annotations. A Tesseract confidence is NOT calibrated
probability of correct card, amount or poker action recognition.
"""
import json
import math
from pathlib import Path
import re

from ocr_probe import read_video_text
from table_regions import Region

SUITS = {'c': 'c', 'd': 'd', 'h': 'h', 's': 's',
         '♣': 'c', '♦': 'd', '♥': 'h', '♠': 's'}
RANKS = set('23456789TJQKA')
FIELDS = {'pot', 'bet', 'board', 'hero_cards'}


def parse_visible_cards(text, *, field):
    """Parse exact printed card tokens only; never guess illegible symbols."""
    if field not in {'board', 'hero_cards'}:
        raise ValueError('Invalid card field')
    if not isinstance(text, str) or not text.strip():
        return None
    tokens = [part for part in re.split(r'[\s,;|/]+', text.strip()) if part]
    result = []
    for token in tokens:
        match = re.fullmatch(r'(10|[2-9TJQKA])([cdhsCDHS♣♦♥♠])', token)
        if match is None:
            return None
        rank = 'T' if match[1] == '10' else match[1].upper()
        suit = SUITS.get(match[2].lower())
        if rank not in RANKS or suit is None:
            return None
        result.append(rank + suit)
    if len(result) != len(set(result)):
        return None
    if field == 'board' and len(result) not in (3, 4, 5):
        return None
    if field == 'hero_cards' and len(result) not in (5, 6):
        return None
    return result


def parse_visible_amount(text, *, field):
    """Read unambiguous nonnegative pot/bet strings; return None otherwise.

    A single 3-digit group after ',' or '.' (e.g. '1,234') is ambiguous
    between thousands and decimal conventions and is deliberately rejected.
    """
    if field not in {'pot', 'bet'}:
        raise ValueError('Invalid amount field')
    if not isinstance(text, str):
        return None
    s = text.strip()
    label = r'(?:Pot|Pote)' if field == 'pot' else r'(?:Bet|Aposta|Call|Raise)'
    s = re.sub(rf'^(?:{label})\s*:?\s*', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^\s*(?:R\$|\$)\s*', '', s)
    s = re.sub(r'\s*(?:BB|chips|fichas)\s*$', '', s, flags=re.IGNORECASE).strip()
    if not re.fullmatch(r'\d[\d.,]*', s):
        return None
    if not ('.' in s or ',' in s):
        return float(s)
    separators = [(i, c) for i, c in enumerate(s) if c in '.,']
    last_sep = separators[-1][1]
    integer, fractional = s.rsplit(last_sep, 1)
    if 1 <= len(fractional) <= 2 and fractional.isdigit():
        if any(c in integer for c in '.,'):
            other = ',' if last_sep == '.' else '.'
            if last_sep in integer:
                return None
            groups = integer.split(other)
            if not (groups[0].isdigit() and 1 <= len(groups[0]) <= 3 and
                    all(len(group) == 3 and group.isdigit() for group in groups[1:])):
                return None
            integer = ''.join(groups)
        return float(integer + '.' + fractional) if integer.isdigit() else None
    if len(separators) >= 2 and all(sep == last_sep for _, sep in separators):
        groups = s.split(last_sep)
        if groups[0].isdigit() and 1 <= len(groups[0]) <= 3 and all(
                len(g) == 3 and g.isdigit() for g in groups[1:]):
            return float(''.join(groups))
    return None


def candidate_from_ocr(ocr_result, *, field, min_engine_confidence=0.75):
    """Return a non-authoritative candidate with explicit review status."""
    if field not in FIELDS:
        raise ValueError('Unknown OCR field')
    if isinstance(min_engine_confidence, bool) or not isinstance(min_engine_confidence, (float, int)) or not math.isfinite(min_engine_confidence) or not 0 <= min_engine_confidence <= 1:
        raise ValueError('Invalid confidence threshold')
    raw = ocr_result['text']
    value = (parse_visible_cards(raw, field=field) if field in {'board', 'hero_cards'}
             else parse_visible_amount(raw, field=field))
    confidence = ocr_result['mean_engine_confidence']
    confidence_ok = (isinstance(confidence, (float, int)) and not isinstance(confidence, bool)
                     and math.isfinite(confidence) and confidence >= min_engine_confidence)
    status = 'candidate_unverified' if value is not None and confidence_ok else 'needs_manual_review'
    return {'table_id': ocr_result['table_id'], 'timestamp': ocr_result['timestamp'],
            'field': field, 'raw_text': raw, 'parsed_candidate': value,
            'mean_engine_confidence': confidence,
            'status': status,
            'source': 'tesseract_manually_selected_roi',
            'warning': 'OCR confidence is not a calibrated probability; human review required before poker analysis.'}


def scan_ocr_manifest(video_path, manifest_path, output_path):
    """Scan explicitly selected ROIs/timestamps from a *recorded* video."""
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    tasks = manifest.get('tasks') if isinstance(manifest, dict) else None
    if not isinstance(tasks, list) or not 1 <= len(tasks) <= 1000:
        raise ValueError('Manifest requires 1..1000 OCR tasks')
    candidates = []
    for task in tasks:
        if not isinstance(task, dict) or task.get('field') not in FIELDS:
            raise ValueError('Task requires a supported field')
        region = Region(**task['region'])
        result = read_video_text(video_path, task['timestamp'], region)
        candidates.append(candidate_from_ocr(result, field=task['field'],
                       min_engine_confidence=manifest.get('min_engine_confidence', 0.75)))
    report = {'schema_version': 1, 'analysis_status': 'unverified_ocr_candidates_only',
              'candidates': candidates,
              'requires_manual_review': True,
              'warning': 'Do not feed OCR candidates directly into mathematical decision reviews.'}
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('tasks_json')
    parser.add_argument('output_json')
    args = parser.parse_args()
    result = scan_ocr_manifest(args.video, args.tasks_json, args.output_json)
    print(json.dumps({'candidates': len(result['candidates'])}, ensure_ascii=False))
