"""Offline-only bridge from reviewed video evidence to conditional call EV.

The equity interval must be justified by an external documented range model.
This module does not calculate equity, establish range confidence or solve GTO.
"""
from collections.abc import Mapping

try:
    from .offline_review_gate import review_gate
    from .offline_ev_call_bounds import call_ev_bounds
except ImportError:
    from offline_review_gate import review_gate
    from offline_ev_call_bounds import call_ev_bounds


def analyze_reviewed_call(hand: Mapping, *, video_duration_s: float, variant: str,
                          equity_low: float, equity_high: float, scenario_id: str) -> dict:
    """Require individually reviewed evidence before a river call EV estimate."""
    gate = review_gate(hand, video_duration_s=video_duration_s, variant=variant)
    result = {'status': 'INSUFFICIENT_DATA', 'evidence': gate,
              'conditional_ev': None, 'is_gto_solution': False}
    if gate['status'] != 'READY_FOR_CONDITIONAL_ANALYSIS':
        return result
    if hand['action'].strip().lower() != 'call':
        return {**result, 'reason': 'ONLY_REVIEWED_CALL_SUPPORTED'}
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        return {**result, 'reason': 'MISSING_RANGE_SCENARIO'}
    if len(hand['board']) != 5:
        return {**result, 'reason': 'FUTURE_BETTING_NOT_MODELED'}
    try:
        ev = call_ev_bounds(pot_before=hand['pot_before'],
                            call_cost=hand['cost_to_call'],
                            equity_low=equity_low, equity_high=equity_high)
    except (TypeError, ValueError, OverflowError):
        return {**result, 'reason': 'INVALID_CONDITIONAL_EQUITY_OR_POT'}
    return {'status': 'CONDITIONAL_EV_ONLY', 'evidence': gate,
            'scenario_id': scenario_id.strip(), 'conditional_ev': ev,
            'range_confidence_established': False, 'is_gto_solution': False,
            'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
            'start_s': hand['start_s'], 'end_s': hand['end_s']}
