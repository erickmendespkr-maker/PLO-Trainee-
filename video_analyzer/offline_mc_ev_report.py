"""Reproducible offline provenance for conditional EV samples; not a poker solver."""
import hashlib
import json
import math
from offline_mc_ev_uncertainty import conditional_mc_call_ev

def build_mc_ev_report(*, video_sha256, hand_id, reviewed, variant, pot_before_call,
                       call_cost, scenarios, rake=0.0, confidence=0.95):
    """Scenario values contain seed, shares, and range_description; no sampling here."""
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('invalid video SHA256')
    if not isinstance(hand_id, str) or not hand_id.strip() or type(reviewed) is not bool:
        raise ValueError('invalid hand identification or review state')
    if variant not in ('PLO5', 'PLO6') or not isinstance(scenarios, dict) or not scenarios:
        raise ValueError('invalid variant or scenarios')
    samples, provenance = {}, {}
    for name, item in scenarios.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(item, dict) or set(item) != {'seed', 'shares', 'range_description'}:
            raise ValueError('invalid scenario schema')
        seed, shares, description = item['seed'], item['shares'], item['range_description']
        if type(seed) is not int or not 0 <= seed < 2**64:
            raise ValueError('invalid seed')
        if not isinstance(description, str) or not description.strip():
            raise ValueError('range description required')
        if not isinstance(shares, (list, tuple)) or not shares or any(type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1 for x in shares):
            raise ValueError('invalid shares')
        normalized = [float(x) for x in shares]
        samples[name] = normalized
        canonical = json.dumps(normalized, separators=(',', ':'), allow_nan=False)
        provenance[name] = {'seed': seed, 'range_description': description,
                            'sample_count': len(normalized),
                            'samples_sha256': hashlib.sha256(canonical.encode()).hexdigest()}
    calculation = conditional_mc_call_ev(pot_before_call, call_cost, samples, rake=rake, confidence=confidence)
    return {'schema_version': 1, 'video_sha256': video_sha256, 'hand_id': hand_id,
            'variant': variant, 'human_reviewed': reviewed,
            'evidence_status': 'reviewed' if reviewed else 'pending_review',
            'sampling_provenance': provenance, 'calculation': calculation,
            'model_scope': 'hypothetical_heads_up_single_call',
            'equity_engine_executed': False,
            'strategic_verdict_allowed': False, 'gto_solution': False}
