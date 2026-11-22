"""Conservative offline hand timeline proposal builder; no live poker integration."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math

STREETS = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}

@dataclass(frozen=True)
class Observation:
    table_id: str
    timestamp: float
    street: str
    board: tuple[str, ...] = ()
    confidence: float = 0.0


def propose_intervals(observations: Iterable[Observation], duration: float) -> list[dict]:
    """Return review-only intervals. Street reset is a candidate boundary, never a confirmed hand."""
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be finite and positive")
    grouped: dict[str, list[Observation]] = {}
    for obs in observations:
        if not isinstance(obs, Observation):
            raise ValueError("observation must be an Observation")
        if not isinstance(obs.table_id, str) or not obs.table_id.strip() or not isinstance(obs.street, str) or obs.street not in STREETS:
            raise ValueError("invalid table or street")
        if isinstance(obs.timestamp, bool) or not isinstance(obs.timestamp, (int, float)) or not math.isfinite(obs.timestamp) or not 0 <= obs.timestamp <= duration:
            raise ValueError("timestamp outside video")
        if isinstance(obs.confidence, bool) or not isinstance(obs.confidence, (int, float)) or not math.isfinite(obs.confidence) or not 0 <= obs.confidence <= 1:
            raise ValueError("invalid confidence")
        if not isinstance(obs.board, tuple) or len(obs.board) not in {0, 3, 4, 5} or any(not isinstance(card, str) or not card.strip() for card in obs.board):
            raise ValueError("invalid board length")
        # A single visible board cannot contain the same physical card twice.
        # Keep OCR uncertainty explicit; do not infer missing ranks or suits.
        normalized_board = [card.strip().upper() for card in obs.board]
        if len(normalized_board) != len(set(normalized_board)):
            raise ValueError("duplicate board cards")
        # Whitespace around an OCR/layout table label does not identify a new table.
        grouped.setdefault(obs.table_id.strip(), []).append(obs)
    output = []
    for table, entries in sorted(grouped.items()):
        entries.sort(key=lambda x: x.timestamp)
        for prev, curr in zip(entries, entries[1:]):
            if prev.timestamp == curr.timestamp:
                raise ValueError("duplicate timestamp on table")
            reset = STREETS[curr.street] < STREETS[prev.street]
            # OCR can vary only in case or surrounding whitespace; those are
            # formatting changes, not evidence of a different physical board.
            prev_board = tuple(card.strip().upper() for card in prev.board)
            curr_board = tuple(card.strip().upper() for card in curr.board)
            changed = curr_board != prev_board
            if reset or changed:
                output.append({"table_id": table, "start_s": prev.timestamp,
                               "end_s": curr.timestamp, "reason": "street_reset" if reset else "board_change",
                               "confidence_upper_bound": min(prev.confidence, curr.confidence),
                               "verified_by_human": False, "hand_id": None,
                               "boundary_exact": False,
                               "note": "Change occurred somewhere between samples; not a confirmed hand boundary."})
    return sorted(output, key=lambda x: (x["start_s"], x["table_id"]))
