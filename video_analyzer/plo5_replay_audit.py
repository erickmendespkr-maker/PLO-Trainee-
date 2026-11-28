"""Independent legal-prefix replay for auto-reconstructed PLO5 candidates.

Checks in-memory consistency with the existing pre/post betting engines; this
is NOT independent visual ground truth and never certifies a hand or strategy.
"""
from plo5_pre_gto_context import need, cards
from plo5_post_gto_context import DECK
from plo5_snapshot_replay import positions, reveal
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def audit_auto_events(seed, events, expected_terminal=None):
    """Replay the emitted events from the original posted-blind seed.

    Reject illegal actions, unanchored streets, repeated cards, terminal
    divergence and malformed event data. Only checks the *candidate* prefix.
    """
    result = dict(status='INVALID_LEGAL_PREFIX', terminal_candidate=None,
                  event_count=0, board=[], error=None, hand_verified=False,
                  financial_result_verified=False, strategy_authorized=False)
    try:
        need(type(seed) is dict and type(events) is list and len(events) <= 512,
             'Invalid replay candidate')
        mapping = positions(seed['dealt'], seed['button'])
        need(set(seed['initial']) == set(mapping), 'Initial seat roster mismatch')
        hero = tuple(cards(seed['holding']))
        need(len(hero) == 5, 'PLO5 requires five private cards')
        state = pre.start({pos:seed['initial'][seat] for seat,pos in mapping.items()},
                          seed['sb'], seed['bb'])
        board = []
        for event in events:
            need(type(event) is dict, 'Invalid event')
            if 'cards' in event:
                need(set(event) == {'cards'} and type(event['cards']) is list,
                     'Invalid board event')
                new = event['cards']
                need(len(new) == (3 if not board else 1), 'Skipped street')
                need(all(type(card) is str and card in DECK for card in new)
                     and len(set(hero + tuple(board) + tuple(new))) == len(hero) + len(board) + len(new),
                     'Invalid or repeated community card')
                state = reveal(state, new)
                board.extend(new)
            else:
                need(set(event) == {'position','action','amount'}, 'Invalid action event')
                engine = pre if isinstance(state,pre.State) else post
                state = engine.step(state,event['position'],event['action'],event['amount'])
        result.update(terminal_candidate=state.status,event_count=len(events),board=board)
        result['status'] = ('LEGAL_PREFIX_CONSISTENT' if expected_terminal is None
                            or state.status == expected_terminal else 'TERMINAL_MISMATCH')
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        result['error'] = str(exc)[:160]
    return result
