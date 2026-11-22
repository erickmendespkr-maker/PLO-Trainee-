"""Conservative offline evidence gate for PLO5/PLO6 video analysis.

This module does not calculate strategy or connect to live games.
"""
import math
import re

CARD_PATTERN = re.compile(r"^(?:[2-9TJQKA][CDHS])$")
VALID_ACTIONS = frozenset({"fold", "check", "call", "bet", "raise", "all_in"})
from collections.abc import Mapping

REQUIRED = ("table_id", "hand_id", "start_s", "end_s", "hero_cards", "board", "action", "pot_before", "cost_to_call")


def review_gate(hand: Mapping, *, video_duration_s: float, variant: str) -> dict:
    """Require human review of decision-critical fields before conditional EV."""
    if variant not in ("PLO5", "PLO6"):
        raise ValueError("variant must be PLO5 or PLO6")
    if (isinstance(video_duration_s, bool) or
            not isinstance(video_duration_s, (int, float)) or
            not math.isfinite(video_duration_s) or video_duration_s <= 0):
        raise ValueError("invalid video duration")
    if not isinstance(hand, Mapping):
        raise ValueError("hand must be a mapping")

    missing = [key for key in REQUIRED if key not in hand or hand[key] is None]
    invalid = []
    for key in ("table_id", "hand_id", "action"):
        if key in hand and (not isinstance(hand[key], str) or not hand[key].strip()):
            invalid.append(key)
    for key in ("start_s", "end_s", "pot_before", "cost_to_call"):
        if key in hand and hand[key] is not None:
            value = hand[key]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                invalid.append(key)
    if all(key in hand and isinstance(hand[key], (int, float)) and
           not isinstance(hand[key], bool) and math.isfinite(hand[key])
           for key in ("start_s", "end_s")):
        if not 0 <= hand["start_s"] < hand["end_s"] <= video_duration_s:
            invalid.append("time_window")

    if "action" in hand and isinstance(hand["action"], str) and hand["action"].strip().lower() not in VALID_ACTIONS:
        invalid.append("action")
    if "table_id" in hand and isinstance(hand["table_id"], str) and hand["table_id"].strip() not in {"1", "2", "3", "4", "mesa-1", "mesa-2", "mesa-3", "mesa-4"}:
        invalid.append("table_id")
    cards = []
    for key, lengths in (("hero_cards", {5 if variant == "PLO5" else 6}),
                         ("board", {0, 3, 4, 5})):
        if key in hand and hand[key] is not None:
            value = hand[key]
            if (not isinstance(value, (list, tuple)) or len(value) not in lengths
                    or any(not isinstance(card, str) or not card.strip() for card in value)):
                invalid.append(key)
            else:
                normalized = [card.strip().upper() for card in value]
                if any(not CARD_PATTERN.fullmatch(card) for card in normalized):
                    invalid.append(key)
                cards.extend(normalized)
    if len(cards) != len(set(cards)):
        invalid.append("duplicate_cards")

    verified = hand.get("verified_fields")
    if (not isinstance(verified, (list, tuple, set, frozenset)) or
            any(not isinstance(item, str) for item in verified)):
        verified = ()
    unverified = [key for key in REQUIRED if key not in verified]
    if "action" in hand and isinstance(hand["action"], str) and hand["action"].strip().lower() in {"fold", "check"} and hand.get("cost_to_call") not in (0, 0.0):
        invalid.append("cost_to_call")
    ready = not (missing or invalid or unverified)
    return {
        "status": "READY_FOR_CONDITIONAL_ANALYSIS" if ready else "INSUFFICIENT_DATA",
        "missing_fields": sorted(set(missing)),
        "invalid_fields": sorted(set(invalid)),
        "unverified_fields": sorted(set(unverified)),
        "is_gto_solution": False,
        "strategic_conclusion": None,
    }
