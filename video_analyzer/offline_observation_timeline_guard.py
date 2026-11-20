"""Conservative offline observation timeline validation; never certifies OCR."""
import math
from collections import defaultdict

STREETS = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}

def validate_observation_timeline(observations, *, duration_s, max_tables=4):
    if isinstance(duration_s, bool) or not isinstance(duration_s, (int, float)) or not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("invalid duration_s")
    if isinstance(max_tables, bool) or not isinstance(max_tables, int) or not 1 <= max_tables <= 4:
        raise ValueError("invalid max_tables")
    if not isinstance(observations, list):
        raise ValueError("observations must be a list")
    errors, groups = [], defaultdict(list)
    for i, o in enumerate(observations):
        if not isinstance(o, dict):
            errors.append({"index": i, "code": "INVALID_RECORD"})
            continue
        table, hand, pts = o.get("table_id"), o.get("hand_id"), o.get("pts_s")
        street, board = o.get("street"), o.get("board")
        if isinstance(table, bool) or not isinstance(table, int) or not 1 <= table <= max_tables:
            errors.append({"index": i, "code": "INVALID_TABLE"})
            continue
        if not isinstance(hand, str) or not hand.strip():
            errors.append({"index": i, "code": "INVALID_HAND"})
            continue
        if isinstance(pts, bool) or not isinstance(pts, (int, float)) or not math.isfinite(pts) or not 0 <= pts <= duration_s:
            errors.append({"index": i, "code": "INVALID_PTS"})
            continue
        if street not in STREETS:
            errors.append({"index": i, "code": "INVALID_STREET"})
            continue
        if o.get("verified_by_human") is not False:
            errors.append({"index": i, "code": "UNSAFE_VERIFICATION"})
            continue
        if board is not None and (not isinstance(board, list) or len(board) != STREETS[street] or any(not isinstance(c, str) or not c.strip() for c in board) or len(set(board)) != len(board)):
            errors.append({"index": i, "code": "INVALID_BOARD"})
            continue
        groups[(table, hand)].append((float(pts), STREETS[street], board, i))
    for entries in groups.values():
        entries.sort(key=lambda x: (x[0], x[3]))
        previous = None
        for pts, count, board, idx in entries:
            if previous is not None:
                old_pts, old_count, old_board = previous
                if pts == old_pts:
                    errors.append({"index": idx, "code": "DUPLICATE_PTS"})
                if count < old_count:
                    errors.append({"index": idx, "code": "STREET_REGRESSION"})
                if board is not None and old_board is not None and board[:len(old_board)] != old_board:
                    errors.append({"index": idx, "code": "BOARD_CHANGED"})
            previous = (pts, count, board)
    return {"ok": not errors, "errors": errors, "observation_count": len(observations), "hand_count": len(groups), "verified_hands": 0}
