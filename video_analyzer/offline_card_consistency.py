"""Validate only visible PLO5/PLO6 cards; never fill unknowns."""
import re

CARD = re.compile(r'^[2-9TJQKA][cdhs]$')


def validate_visible_cards(hero_cards, board, variant):
    """Return an auditable verdict; incomplete boards are allowed, unknown cards are not."""
    problems = []
    if variant not in ('PLO5', 'PLO6'):
        problems.append('unsupported_variant')
    expected = {'PLO5': 5, 'PLO6': 6}.get(variant)
    if not isinstance(hero_cards, (list, tuple)) or expected is None or len(hero_cards) != expected:
        problems.append('hero_card_count')
    if not isinstance(board, (list, tuple)) or len(board) not in (0, 3, 4, 5):
        problems.append('board_card_count')
    cards = list(hero_cards) + list(board) if isinstance(hero_cards, (list, tuple)) and isinstance(board, (list, tuple)) else []
    if any(not isinstance(card, str) or CARD.fullmatch(card) is None for card in cards):
        problems.append('invalid_card')
    if len(cards) != len(set(cards)) if all(isinstance(card, str) for card in cards) else True:
        problems.append('duplicate_card')
    return {'status': 'CONSISTENT' if not problems else 'INSUFFICIENT_DATA',
            'problems': sorted(set(problems)), 'board_complete': isinstance(board, (list, tuple)) and len(board) == 5,
            'hidden_cards_inferred': False, 'strategic_verification': False}
