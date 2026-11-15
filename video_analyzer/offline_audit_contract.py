"""Strict post-export audit contract for unreviewed offline PLO clips."""
import math
import re

_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


def validate_audit_result(verification, exporter_sha256=None):
    """Validate an auditor's response before elevating *artifact* status.

    This does not validate cards, actions, equities or poker strategy.
    """
    if not isinstance(verification, dict):
        raise ValueError('audit response must be an object')
    if (verification.get('verified_artifacts') is not True
            or verification.get('strategic_verdict_allowed') is not False
            or verification.get('human_review_required') is not True):
        raise ValueError('unsafe or incomplete audit')
    digest = verification.get('clip_sha256')
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise ValueError('invalid audited SHA-256')
    if exporter_sha256 is not None:
        if not isinstance(exporter_sha256, str) or _SHA256.fullmatch(exporter_sha256) is None:
            raise ValueError('invalid exporter SHA-256')
        if exporter_sha256 != digest:
            raise ValueError('exporter and auditor hashes disagree')
    duration = verification.get('duration_seconds')
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('invalid audited duration')
    return {'clip_sha256': digest, 'duration_seconds': duration}
