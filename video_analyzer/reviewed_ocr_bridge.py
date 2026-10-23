"""Human-reviewed OCR evidence -> structured, auditable offline observations.

No automatic hand assignment, action inference or claim of calibrated accuracy.
Only an explicitly confirmed annotation can become an Observation. Every
accepted OCR field carries a source index and the reviewed value in provenance.
"""
import json
import math
from dataclasses import asdict
from pathlib import Path

from hand_history import Observation, reconstruct_hands
from observation_audit import audit_observations

FIELDS = {'pot': 'pot', 'bet': 'amount', 'board': 'board', 'hero_cards': 'hero_cards'}


def _confidence(value, label):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 <= value <= 1):
        raise ValueError(f'{label} must be a finite number between 0 and 1')
    return float(value)


def _reviewed_value(field, value):
    if field in ('pot', 'bet'):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            raise ValueError(f'Invalid reviewed {field} amount')
        return float(value)
    if not isinstance(value, list):
        raise ValueError(f'Reviewed {field} must be a list of cards')
    # Observation validates card count, notation and uniqueness.
    return tuple(value)


def bridge_reviewed_ocr(ocr_report, review_manifest, *, max_time_delta=1.0):
    """Validate an explicit human review and build hand observations + audit.

    review_manifest = {"schema_version":1, "events":[{
      "table_id":1,"timestamp":10,"hand_id":"h1","variant":"PLO5",
      "action":"board","human_confirmed":true,"reviewer_confidence":0.95,
      "field_reviews":{"board":{"candidate_index":0,"human_confirmed":true,
                        "reviewer_confidence":0.95,"approved_value":["As","Kd","Qc"]}}
    }]}

    The OCR report is evidence, never a source of confirmed actions or ranges.
    "correction_reason" is required if a reviewer changes an OCR value.
    "reviewer_confidence" is subjective, not a calibrated probability.
    """
    if (isinstance(max_time_delta, bool) or not isinstance(max_time_delta, (int, float))
            or not math.isfinite(max_time_delta) or max_time_delta < 0):
        raise ValueError('Invalid timestamp tolerance')
    if (not isinstance(ocr_report, dict)
            or ocr_report.get('analysis_status') != 'unverified_ocr_candidates_only'
            or not isinstance(ocr_report.get('candidates'), list)):
        raise ValueError('Expected unverified OCR candidate report')
    candidates = ocr_report['candidates']
    if len(candidates) > 100000:
        raise ValueError('Too many OCR candidates')
    if (not isinstance(review_manifest, dict) or review_manifest.get('schema_version') != 1
            or not isinstance(review_manifest.get('events'), list)
            or len(review_manifest['events']) > 10000):
        raise ValueError('Expected version 1 review manifest with at most 10000 events')

    observations = []
    provenance = []
    used_evidence = set()
    for event_index, event in enumerate(review_manifest['events']):
        if not isinstance(event, dict) or event.get('human_confirmed') is not True:
            raise ValueError('Every event must be explicitly human confirmed')
        if not isinstance(event.get('hand_id'), str) or not event['hand_id'].strip():
            raise ValueError('Hand IDs must be manually assigned')
        table_id = event.get('table_id')
        timestamp = event.get('timestamp')
        if isinstance(table_id, bool) or not isinstance(table_id, int) or not 1 <= table_id <= 4:
            raise ValueError('Invalid table ID')
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp < 0):
            raise ValueError('Invalid event timestamp')
        reviewer_confidence = _confidence(event.get('reviewer_confidence'), 'reviewer_confidence')
        field_reviews = event.get('field_reviews', {})
        if not isinstance(field_reviews, dict) or not set(field_reviews).issubset(FIELDS):
            raise ValueError('Unsupported field reviews')
        approved = {}
        confidences = {'action': reviewer_confidence}
        evidence = []
        for field, review in field_reviews.items():
            if not isinstance(review, dict) or review.get('human_confirmed') is not True:
                raise ValueError('Each field must be explicitly human confirmed')
            idx = review.get('candidate_index')
            if isinstance(idx, bool) or not isinstance(idx, int) or not 0 <= idx < len(candidates):
                raise ValueError('Invalid candidate index')
            if idx in used_evidence:
                raise ValueError('OCR candidate reused across events')
            candidate = candidates[idx]
            if not isinstance(candidate, dict) or candidate.get('field') != field:
                raise ValueError('OCR field does not match review')
            if candidate.get('table_id') != table_id or isinstance(candidate.get('table_id'), bool):
                raise ValueError('OCR table does not match review')
            source_time = candidate.get('timestamp')
            if (isinstance(source_time, bool) or not isinstance(source_time, (int, float))
                    or not math.isfinite(source_time) or abs(source_time - timestamp) > max_time_delta):
                raise ValueError('OCR timestamp does not match review')
            if candidate.get('status') not in ('candidate_unverified', 'needs_manual_review'):
                raise ValueError('Unexpected OCR evidence status')
            reviewed = _reviewed_value(field, review.get('approved_value'))
            raw_value = candidate.get('parsed_candidate')
            parsed = tuple(raw_value) if isinstance(raw_value, list) else raw_value
            if parsed != reviewed:
                reason = review.get('correction_reason')
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError('OCR correction requires a reason')
            else:
                reason = None
            reviewer_field_confidence = _confidence(review.get('reviewer_confidence'), 'field reviewer_confidence')
            approved[FIELDS[field]] = reviewed
            confidences[FIELDS[field]] = reviewer_field_confidence
            evidence.append({'field': field, 'candidate_index': idx,
                             'source_timestamp': source_time, 'source_image': candidate.get('source_image'),
                             'ocr_engine_confidence_uncalibrated': candidate.get('mean_engine_confidence'),
                             'raw_ocr_text': candidate.get('raw_text'),
                             'source_timestamp_semantics': candidate.get('timestamp_semantics'),
                             'raw_candidate': raw_value,
                             'approved_value': list(reviewed) if isinstance(reviewed, tuple) else reviewed,
                             'corrected': reason is not None, 'correction_reason': reason,
                             'reviewer_confidence': reviewer_field_confidence})
            used_evidence.add(idx)
        obs = Observation(table_id=table_id, timestamp=float(timestamp),
                          hand_id=event['hand_id'], action=event.get('action'),
                          actor=event.get('actor'), variant=event.get('variant'),
                          confidence=reviewer_confidence, field_confidence=confidences,
                          notes=event.get('notes', ''), **approved)
        observations.append(obs)
        provenance.append({'event_index': event_index, 'table_id': table_id,
                           'timestamp': timestamp, 'hand_id': event['hand_id'],
                           'human_confirmed': True, 'evidence': evidence})
    # Reconstructing enforces time ordering within each table.
    audit = audit_observations(observations)
    hands, unassigned = reconstruct_hands(observations)
    history = {'schema_version': 1, 'hands': [
        {'table_id': table, 'hand_id': hand, 'observations': [asdict(o) for o in events]}
        for (table, hand), events in hands.items()],
        'unassigned': [asdict(o) for o in unassigned]}
    return {'schema_version': 1, 'analysis_status': 'human_reviewed_observations',
            'warning': 'Reviewer confidence is subjective, not calibrated. Hand audit is not proof of correct reconstruction.',
            'observations': [asdict(x) for x in observations],
            'provenance': provenance, 'audit': audit, 'history': history}


def bridge_json(ocr_path, review_path, output_path, *, observations_output=None):
    ocr_report = json.loads(Path(ocr_path).read_text(encoding='utf-8'))
    review = json.loads(Path(review_path).read_text(encoding='utf-8'))
    result = bridge_reviewed_ocr(ocr_report, review)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if observations_output is not None:
        observations_path = Path(observations_output)
        observations_path.parent.mkdir(parents=True, exist_ok=True)
        observations_path.write_text(json.dumps(result['observations'], ensure_ascii=False, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ocr_report')
    parser.add_argument('human_review')
    parser.add_argument('output_json')
    parser.add_argument('--observations-output', help='JSON list for guarded_review_pipeline')
    args = parser.parse_args()
    result = bridge_json(args.ocr_report, args.human_review, args.output_json,
                         observations_output=args.observations_output)
    print(json.dumps({'events': len(result['observations']),
                      'hands': result['audit']['counts']['hands']}, ensure_ascii=False))
