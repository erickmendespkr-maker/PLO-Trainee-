"""Combine human-reviewed video evidence with PLO5/PLO6 card consistency.

No hidden cards, strategic certainty, or GTO claims are inferred.
"""
try:
    from .offline_hand_evidence_gate import assess_hand_evidence
    from .offline_card_consistency import validate_visible_cards
except ImportError:
    from offline_hand_evidence_gate import assess_hand_evidence
    from offline_card_consistency import validate_visible_cards


def assess_reviewed_hand(hand, variant, *, minimum_confidence=0.90):
    """Allow conditional analysis only if every required field and card is valid."""
    evidence = assess_hand_evidence(hand, minimum_confidence=minimum_confidence)
    hero = hand.get('hero_cards')
    board = hand.get('board')
    cards = validate_visible_cards(
        hero.get('value') if isinstance(hero, dict) else None,
        board.get('value') if isinstance(board, dict) else None,
        variant,
    )
    ready = evidence['status'] == 'EVIDENCE_REVIEWED' and cards['status'] == 'CONSISTENT'
    return {
        'status': 'READY_FOR_CONDITIONAL_ANALYSIS' if ready else 'INSUFFICIENT_DATA',
        'evidence': evidence,
        'cards': cards,
        'conditional_analysis_allowed': ready,
        'strategic_verification': False,
        'ev_is_conditional': True,
        'hidden_cards_inferred': False,
    }
