"""Bounded, lossless compaction of repeated PLO5 observation constraints.

An identical unresolved checkpoint must not consume another search slot simply
because the same screen state was decoded again. Time is bounded independently:
no sequence of duplicate observations is allowed to bridge arbitrarily long
periods without a new legal action anchor.
"""
from fractions import Fraction

_FIELDS = ('remaining', 'pot', 'active', 'actor')


def defer_checkpoint(pending, candidate, *, max_count=6, max_span=Fraction(4)):
    """Update pending in place; return ADDED, DUPLICATE, LIMIT or TIMEOUT.

    Preserve the *first* PTS for identical constraints, so the replay retains
    the earliest evidence and the absolute unresolved time bound. Distinct
    actor, active roster, chip or pot evidence is never discarded.
    """
    if type(pending) is not list or type(candidate) is not dict:
        raise ValueError('Invalid checkpoint input')
    if type(max_count) is not int or not 1 <= max_count <= 6:
        raise ValueError('Invalid checkpoint budget')
    limit = Fraction(max_span)
    if not 0 < limit <= 30:
        raise ValueError('Invalid checkpoint time budget')
    ts = Fraction(candidate['pts'])
    if pending:
        first = Fraction(pending[0]['pts'])
        if ts <= Fraction(pending[-1]['pts']):
            raise ValueError('Checkpoint PTS must increase')
        if ts - first > limit:
            return 'TIMEOUT'
        if all(pending[-1][field] == candidate[field] for field in _FIELDS):
            return 'DUPLICATE'
    if len(pending) >= max_count:
        return 'LIMIT'
    pending.append(candidate)
    return 'ADDED'
