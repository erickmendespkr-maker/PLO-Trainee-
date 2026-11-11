"""Bind an unverified offline EV gate to an independently selected clip sidecar.

Checks SHA-256 provenance claims, table/hand IDs and timestamp containment.
Never opens the original recording or establishes poker facts or a verdict.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

HEX = re.compile(r'[0-9a-f]{64}\Z')

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 1024*1024, 'invalid JSON source')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    return json.loads(p.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite JSON')))

def number(v):
    return type(v) in (int, float) and math.isfinite(v)

def verify(gate, clip, gate_hash, clip_hash):
    require(type(gate) is dict and type(gate.get('schema_version')) is int and
            gate['schema_version'] == 1 and
            gate.get('status') == 'matching_claims_not_independently_verified' and
            gate.get('source_hand_reconstruction_verified') is False and
            gate.get('equity_ranges_observed_from_video') is False and
            gate.get('ready_for_strategic_verdict') is False and
            gate.get('automatic_clip_selection_authorized') is False and
            gate.get('pot_call_values_match') is True, 'invalid unverified math gate')
    require(type(clip) is dict and type(clip.get('schema_version')) is int and
            clip['schema_version'] == 1 and
            clip.get('analysis_status') == 'manually_selected_offline_clip' and
            clip.get('video_evidence_verified') is False and
            clip.get('automatic_clip_selection_authorized') is False and
            clip.get('audio_included') is False, 'invalid offline clip metadata')
    for key in ('annotation_sha256', 'scenario_sha256', 'source_video_sha256_claim'):
        require(type(gate.get(key)) is str and HEX.fullmatch(gate[key]),
                'missing gate provenance')
    for key in ('source_video_sha256', 'source_request_sha256', 'clip_sha256'):
        require(type(clip.get(key)) is str and HEX.fullmatch(clip[key]),
                'missing clip provenance')
    require(gate['source_video_sha256_claim'] == clip['source_video_sha256'],
            'different source recording')
    require(type(gate.get('hand_id_claim')) is str and
            gate['hand_id_claim'] == clip.get('hand_id'), 'hand ID mismatch')
    require(type(gate.get('table_id_claim')) is int and
            gate['table_id_claim'] == clip.get('table_id') and
            1 <= gate['table_id_claim'] <= 4, 'table mismatch')
    interval = gate.get('hand_interval_seconds_claim')
    require(type(interval) is list and len(interval) == 2 and
            all(number(x) for x in interval) and
            0 <= interval[0] < interval[1] <= 5400, 'invalid hand interval')
    start, end = clip.get('start_seconds'), clip.get('end_seconds')
    require(number(start) and number(end) and 0 <= start < end <= 5400,
            'invalid clip interval')
    require(start <= interval[0] and end >= interval[1],
            'clip does not fully contain claimed hand interval')
    require(type(gate.get('scenario_id')) is str and
            1 <= len(gate['scenario_id']) <= 80, 'invalid scenario ID')
    return {
        'schema_version': 1, 'status': 'matching_unverified_claims_only',
        'gate_sha256': gate_hash, 'clip_metadata_sha256': clip_hash,
        'source_video_sha256_claim': clip['source_video_sha256'],
        'source_clip_sha256_claim_not_recomputed': clip['clip_sha256'],
        'hand_id_claim': gate['hand_id_claim'], 'table_id_claim': gate['table_id_claim'],
        'hand_interval_seconds_claim': interval,
        'clip_interval_seconds_claim': [start, end],
        'scenario_id': gate['scenario_id'],
        'clip_contains_claimed_hand_interval': True,
        'source_video_opened': False, 'video_evidence_verified': False,
        'source_hand_reconstruction_verified': False,
        'equity_ranges_observed_from_video': False,
        'ready_for_strategic_verdict': False,
        'automatic_clip_selection_authorized': False,
        'warning': 'Only metadata agreement; no original recording, visual hand, equity or strategic decision verified.'
    }

def run(gate_path, clip_metadata_path, output_path):
    gate_path, clip_metadata_path, output_path = map(
        Path, (gate_path, clip_metadata_path, output_path))
    require(output_path.suffix == '.json' and output_path.parent.is_dir() and
            not output_path.parent.is_symlink() and not output_path.exists() and
            not output_path.is_symlink() and
            len({p.resolve() for p in (gate_path, clip_metadata_path, output_path)}) == 3,
            'output must be new and distinct')
    gate_hash, clip_hash = digest(gate_path), digest(clip_metadata_path)
    report = verify(read(gate_path), read(clip_metadata_path), gate_hash, clip_hash)
    require(digest(gate_path) == gate_hash and
            digest(clip_metadata_path) == clip_hash, 'source changed during audit')
    with tempfile.TemporaryDirectory(prefix='.plo_binding_', dir=output_path.parent) as tmp:
        stage = Path(tmp) / 'binding.json'
        stage.write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                    allow_nan=False)+'\n', encoding='utf-8')
        os.link(stage, output_path)
    return report

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('math_gate_json')
    p.add_argument('clip_sidecar_json')
    p.add_argument('new_binding_json')
    args = p.parse_args()
    print(json.dumps({'status': run(args.math_gate_json, args.clip_sidecar_json,
                                    args.new_binding_json)['status']}))

if __name__ == '__main__':
    main()
