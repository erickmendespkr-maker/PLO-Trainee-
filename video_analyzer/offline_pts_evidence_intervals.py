"""Conservative uncertainty windows from sparse offline video frame observations.

A transition window is NOT an exact hand boundary or a verified poker action.
"""
import math


def propose_transition_windows(observations, *, max_gap_seconds=30.0):
    """Build table-local transition proposals; never infer hidden cards or actions."""
    if not isinstance(observations, list):
        raise ValueError("observations must be a list")
    if type(max_gap_seconds) not in (int, float) or not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError("invalid max_gap_seconds")
    by_table, seen = {}, set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("invalid observation")
        table, pts, state, sha = (observation.get(key) for key in ("table_id", "pts", "state", "frame_sha256"))
        if not isinstance(table, str) or not table.strip() or not isinstance(state, str) or not state.strip():
            raise ValueError("invalid table or state")
        if type(pts) not in (int, float) or not math.isfinite(pts) or pts < 0:
            raise ValueError("invalid pts")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid frame hash")
        key = (table, pts)
        if key in seen:
            raise ValueError("duplicate table timestamp")
        seen.add(key)
        by_table.setdefault(table, []).append((pts, state, sha))
    windows = []
    for table, rows in sorted(by_table.items()):
        rows.sort()
        for (start, previous, first_sha), (end, current, last_sha) in zip(rows, rows[1:]):
            if previous == current:
                continue
            gap = end - start
            windows.append({
                "table_id": table, "earliest_pts": start, "latest_pts": end,
                "from_state": previous, "to_state": current,
                "start_frame_sha256": first_sha, "end_frame_sha256": last_sha,
                "gap_seconds": gap, "requires_review": True,
                "usable_as_hand_boundary": False,
                "status": "CANDIDATE" if gap <= max_gap_seconds else "SPARSE_UNCERTAIN",
            })
    return sorted(windows, key=lambda window: (window["earliest_pts"], window["table_id"], window["latest_pts"]))
