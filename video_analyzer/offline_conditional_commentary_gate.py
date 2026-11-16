"""Fail-closed eligibility for conditional EV commentary on offline recorded hands.

Separate from the existing boundary-only clip gate. No strategy conclusions.
"""
import math
import re

_CARD = re.compile(r'^[2-9TJQKA][cdhs]$')

def assess_conditional_commentary(hand, comparison):
    """Require human-reviewed evidence and a conservative multi-range comparison."""
    reasons = []
    if not isinstance(hand, dict):
        return {'status': 'REVIEW_ONLY', 'reasons': ['hand_not_object'], 'verified_error': False}
    if not isinstance(comparison, dict):
        comparison = {}
    for key in ('table_id', 'hand_id', 'video_sha256', 'hero_cards', 'board_cards',
                'action', 'pot', 'call_cost', 'range_sources'):
        value = hand.get(key)
        if value is None or isinstance(value, str) and not value.strip() or isinstance(value, (list, dict)) and not value:
            reasons.append('missing_' + key)
    if hand.get('human_reviewed') is not True:
        reasons.append('human_review_required')
    variant = hand.get('variant')
    if type(variant) is not str or variant not in ('PLO5', 'PLO6'):
        reasons.append('invalid_variant')
    sha = hand.get('video_sha256')
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
        reasons.append('invalid_video_sha256')
    for key in ('start_pts', 'end_pts', 'pot', 'call_cost'):
        v = hand.get(key)
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
            reasons.append('invalid_' + key)
    if 'invalid_start_pts' not in reasons and 'invalid_end_pts' not in reasons and hand['end_pts'] <= hand['start_pts']:
        reasons.append('invalid_pts_order')
    for key in ('hero_cards', 'board_cards'):
        cards = hand.get(key)
        if not isinstance(cards, list) or not all(isinstance(c, str) and c.strip() for c in cards):
            reasons.append('invalid_' + key)
    hero, board = hand.get('hero_cards'), hand.get('board_cards')
    if isinstance(hero, list) and isinstance(board, list):
        expected = {'PLO5': 5, 'PLO6': 6}.get(variant, -1) if type(variant) is str else -1
        if len(hero) != expected or len(board) > 5:
            reasons.append('invalid_card_count')
        if not all(isinstance(c, str) and _CARD.fullmatch(c) for c in hero + board):
            reasons.append('invalid_card_notation')
        if len(set(map(str, hero + board))) != len(hero + board):
            reasons.append('duplicate_cards')
    sources = hand.get('range_sources')
    if not isinstance(sources, list) or len(sources) < 2 or any(not isinstance(s, str) or not s.strip() for s in sources) or len(set(s.strip() for s in sources if isinstance(s, str))) != len(sources):
        reasons.append('invalid_range_sources')
    if not isinstance(hand.get('action'), str) or hand['action'] not in ('fold', 'call', 'raise', 'bet', 'check'):
        reasons.append('invalid_action')
    if comparison.get('status') != 'CONDITIONAL_ONLY' or comparison.get('cross_range_comparison_available') is not True:
        reasons.append('scenario_comparison_required')
    if comparison.get('hand_error_verified') is not False or comparison.get('gto_solution') is not False:
        reasons.append('unsupported_strategy_claim')
    if reasons:
        return {'status': 'REVIEW_ONLY', 'reasons': sorted(set(reasons)), 'verified_error': False}
    return {'status': 'CONDITIONAL_EXPLANATION_ALLOWED', 'reasons': [], 'verified_error': False,
            'stable_action': comparison.get('stable_action'),
            'range_sensitive_or_inconclusive': comparison.get('range_sensitive_or_inconclusive') is not False}
