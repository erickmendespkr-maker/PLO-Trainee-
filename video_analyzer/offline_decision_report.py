"""Build an auditable offline decision report without upgrading uncertain evidence."""
import json
import math
from collections.abc import Mapping


def decision_report(analysis: Mapping, *, video_sha256: str, clip_start_s: float, clip_end_s: float) -> dict:
    """Return a JSON-safe report. No strategic ranking unless evidence is reviewed."""
    if not isinstance(analysis, Mapping):
        raise ValueError('analysis must be a mapping')
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('video_sha256 must be lowercase SHA-256')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (clip_start_s, clip_end_s)):
        raise ValueError('clip timestamps must be finite')
    if not 0 <= clip_start_s < clip_end_s:
        raise ValueError('invalid clip window')
    evidence = analysis.get('evidence')
    if not isinstance(evidence, Mapping):
        raise ValueError('evidence audit required')
    status = analysis.get('status')
    ready = evidence.get('status') == 'READY_FOR_CONDITIONAL_ANALYSIS'
    conditional = status == 'CONDITIONAL_EV_ONLY' and ready
    ev = analysis.get('conditional_ev') if conditional else None
    scenario = analysis.get('scenario_id') if conditional else None
    if conditional:
        if not isinstance(scenario, str) or not scenario.strip() or not isinstance(ev, Mapping):
            raise ValueError('conditional result lacks scenario or EV audit')
        lo, hi = ev.get('ev_low_chips'), ev.get('ev_high_chips')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (lo, hi)) or lo > hi:
            raise ValueError('invalid EV bounds')
    else:
        ev = None
        scenario = None
    report = {
        'schema_version': 1, 'video_sha256': video_sha256,
        'clip': {'start_s': clip_start_s, 'end_s': clip_end_s, 'reviewed': False},
        'status': 'CONDITIONAL_EV_ONLY' if conditional else 'INSUFFICIENT_DATA',
        'scenario_id': scenario, 'conditional_ev': dict(ev) if ev is not None else None,
        'evidence': {'status': evidence.get('status'),
                     'missing_fields': list(evidence.get('missing_fields') or []),
                     'invalid_fields': list(evidence.get('invalid_fields') or []),
                     'unverified_fields': list(evidence.get('unverified_fields') or [])},
        'strategic_conclusion': None, 'is_gto_solution': False,
        'disclaimer': 'Conditional model only; no GTO claim or verified strategic mistake.'
    }
    json.dumps(report, allow_nan=False)
    return report
