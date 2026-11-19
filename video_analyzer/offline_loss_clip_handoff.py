"""Conservative handoff from reviewed losses to offline clip plans."""
import math
import re

_SHA = re.compile(r'[0-9a-f]{64}\Z')

def build_loss_clip_plan(handoff, reviews, video_sha256, *, threshold_bb=30):
    if not isinstance(video_sha256, str) or not _SHA.fullmatch(video_sha256):
        raise ValueError('invalid video hash')
    if not isinstance(handoff, dict) or handoff.get('analysis_verified') is not False or handoff.get('is_gto') is not False:
        raise ValueError('untrusted queue')
    queue = handoff.get('review_queue')
    if not isinstance(queue, list) or not isinstance(reviews, list):
        raise ValueError('invalid queue or reviews')
    if type(threshold_bb) not in (int, float) or not math.isfinite(threshold_bb) or threshold_bb < 0:
        raise ValueError('invalid threshold')
    index = {}
    for item in queue:
        if not isinstance(item, dict) or item.get('strategy_verified') is not False:
            raise ValueError('untrusted item')
        key = (item.get('hand_id'), item.get('table_id'))
        if key in index or not isinstance(key[0], str) or type(key[1]) is not int or key[1] not in range(1, 5):
            raise ValueError('invalid or duplicate queue identity')
        index[key] = item
    seen = set()
    plans = []
    for review in reviews:
        if not isinstance(review, dict):
            raise ValueError('invalid review')
        key = (review.get('hand_id'), review.get('table_id'))
        if key in seen or key not in index:
            raise ValueError('duplicate or unknown review')
        seen.add(key)
        item = index[key]
        if review.get('boundaries_verified') is not True or review.get('crop_verified') is not True or review.get('strategy_verified') is not False:
            raise ValueError('unverified boundaries, crop or strategy')
        if item.get('loss_over_30bb') is not True:
            raise ValueError('loss not confirmed')
        loss = item.get('loss_evidence')
        if not isinstance(loss, dict) or loss.get('hand_id') != key[0] or loss.get('table_id') != key[1] or loss.get('strategy_verified') is not False:
            raise ValueError('invalid loss provenance')
        bb = loss.get('confirmed_loss_bb')
        if type(bb) not in (int, float) or not math.isfinite(bb) or bb <= max(30, threshold_bb):
            raise ValueError('loss below threshold')
        start, end = review.get('clip_start_seconds'), review.get('clip_end_seconds')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or not 0 <= start < end or end-start > 180:
            raise ValueError('invalid clip interval')
        if start > item.get('start_seconds') or end < item.get('end_seconds'):
            raise ValueError('clip does not contain proposed hand')
        crop = review.get('crop_xywh')
        if not isinstance(crop, (list, tuple)) or len(crop) != 4 or any(type(v) is not int or v < 0 or v % 2 for v in crop) or min(crop[2:]) < 2:
            raise ValueError('invalid crop')
        plans.append({'hand_id': key[0], 'table_id': key[1], 'clip_start_seconds': start,
                      'clip_end_seconds': end, 'crop_xywh': list(crop),
                      'boundaries_verified': True, 'strategy_verified': False,
                      'analysis_label': 'INSUFFICIENT_DATA'})
    return {'schema_version': 1, 'source_video_sha256': video_sha256,
            'analysis_verified': False, 'is_gto': False, 'clip_plans': plans}
