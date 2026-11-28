"""Conservative visual continuity and exact effective OCR input keys."""
from fractions import Fraction


def continuity_flags(previous, current, max_gap):
    """Missing dealer is deferable; a positive contradiction is not."""
    flags = []
    delta = Fraction(current['pts']) - Fraction(previous['pts'])
    if not 0 < delta <= max_gap:
        flags.append('PTS_GAP')
    if current['platform'] != previous['platform']:
        flags.append('PLATFORM_CHANGE')
    if current['profile'] != previous['profile']:
        flags.append('PROFILE_CHANGE')
    if current['button'] is not None and current['button'] != previous['button']:
        flags.append('DEALER_CONFLICT')
    if current['holding'] is not None and current['holding'] != previous['holding']:
        flags.append('HOLDING_CONFLICT')
    return tuple(flags)


def seat_ocr_key(patch, platform, field, *, effective_gray=False):
    """Only opt in for decoders that consume this exact grayscale interior."""
    if effective_gray:
        interior = patch.convert('L').crop((3, 1, patch.width-3, patch.height-2))
        return (platform, field, 'gray-interior-v1', interior.size, interior.tobytes())
    return (platform, field, 'raw-v1', patch.mode, patch.size, patch.tobytes())
