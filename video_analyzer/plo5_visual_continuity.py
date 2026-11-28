"""Conservative visual continuity and exact effective OCR input keys."""
from fractions import Fraction


def continuity_flags(previous, current, max_gap):
    """Missing metadata is deferable; positive contradictions are not."""
    flags = []
    delta = Fraction(current['pts']) - Fraction(previous['pts'])
    if not 0 < delta <= max_gap:
        flags.append('PTS_GAP')
    if current['platform'] != previous['platform']:
        flags.append('PLATFORM_CHANGE')
    if previous['profile'] is not None and current['profile'] is not None and current['profile'] != previous['profile']:
        flags.append('PROFILE_CHANGE')
    if previous['button'] is not None and current['button'] is not None and current['button'] != previous['button']:
        flags.append('DEALER_CONFLICT')
    if previous['holding'] is not None and current['holding'] is not None and current['holding'] != previous['holding']:
        flags.append('HOLDING_CONFLICT')
    return tuple(flags)


def continuity_chain_flags(anchor, previous, current, max_gap):
    """Use adjacent PTS for gaps, while retaining identity at the last accepted anchor.

    Partial snapshots establish temporal continuity but cannot overwrite the
    anchored dealer, profile or cards. Never infer missing evidence as a change.
    """
    adjacent = continuity_flags(previous, current, max_gap)
    anchored = continuity_flags(anchor, current, max_gap)
    return tuple(dict.fromkeys((*adjacent, *(f for f in anchored if f != 'PTS_GAP'))))


def seat_ocr_key(patch, platform, field, *, effective_gray=False):
    """Only opt in for decoders that consume this exact grayscale interior."""
    if effective_gray:
        interior = patch.convert('L').crop((3, 1, patch.width-3, patch.height-2))
        if interior.width and interior.height:
            lo, hi = interior.getextrema()
            if hi - lo < 15:
                return (platform, field, 'gray-low-contrast-v1', b'')
        return (platform, field, 'gray-interior-v1', interior.size, interior.tobytes())
    return (platform, field, 'raw-v1', patch.mode, patch.size, patch.tobytes())
