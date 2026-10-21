"""Create unapproved OCR review forms. Never infer or approve a poker hand."""
import json
import math
from pathlib import Path

def build_review_packet(report):
    if (not isinstance(report, dict)
            or report.get('analysis_status') != 'unverified_ocr_candidates_only'
            or report.get('requires_manual_review') is not True
            or not isinstance(report.get('candidates'), list)):
        raise ValueError('Expected unverified OCR candidates requiring review')
    candidates = report['candidates']
    if len(candidates) > 10000:
        raise ValueError('Review packet limited to 10000 OCR candidates')
    groups = {}
    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError('Invalid OCR candidate')
        table, timestamp, field = (candidate.get(k) for k in ('table_id', 'timestamp', 'field'))
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= 4:
            raise ValueError('Invalid OCR table ID')
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp < 0):
            raise ValueError('Invalid OCR timestamp')
        if field not in ('pot', 'bet', 'board', 'hero_cards') or candidate.get('status') not in ('candidate_unverified', 'needs_manual_review'):
            raise ValueError('Unexpected OCR field or verification status')
        fields = groups.setdefault((table, float(timestamp)), {})
        if field in fields:
            raise ValueError('Duplicate OCR field for table/timestamp')
        fields[field] = (idx, candidate)
    events = []
    for (table, timestamp), fields in sorted(groups.items()):
        reviews, hints = {}, {}
        for field, (idx, candidate) in sorted(fields.items()):
            reviews[field] = {'candidate_index': idx, 'human_confirmed': False,
                              'reviewer_confidence': None, 'approved_value': None,
                              'correction_reason': None}
            hints[field] = {'ocr_hint_unverified': candidate.get('parsed_candidate'),
                            'ocr_status': candidate['status'],
                            'source_image': candidate.get('source_image')}
        events.append({'table_id': table, 'timestamp': timestamp, 'hand_id': None,
                       'variant': None, 'action': None, 'actor': None,
                       'human_confirmed': False, 'reviewer_confidence': None,
                       'field_reviews': reviews, 'evidence_context_unverified': hints,
                       'notes': 'Review source frames; assign hand, variant and action.'})
    return {'schema_version': 1, 'analysis_status': 'unapproved_human_review_template',
            'requires_manual_review': True,
            'warning': 'All confirmations false; OCR hints are not verified facts.',
            'events': events}

def write_review_packet(ocr_path, output_path):
    packet = build_review_packet(json.loads(Path(ocr_path).read_text(encoding='utf-8')))
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(packet, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    return packet

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ocr_report')
    parser.add_argument('review_template')
    args = parser.parse_args()
    packet = write_review_packet(args.ocr_report, args.review_template)
    print(json.dumps({'unapproved_events': len(packet['events'])}))
