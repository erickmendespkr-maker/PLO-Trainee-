"""Conservative, deterministic offline ledger for visual proposals awaiting review."""
import hashlib
import json
import math

def build_review_ledger(proposal_result, *, video_sha256, duration_seconds):
    if not isinstance(proposal_result, dict) or proposal_result.get("schema_version") != 1:
        raise ValueError("unsupported proposal schema")
    if proposal_result.get("analysis_verified") is not False or proposal_result.get("hand_boundaries_verified") is not False:
        raise ValueError("unverified proposals required")
    if not isinstance(video_sha256, str) or len(video_sha256) != 64 or any(c not in "0123456789abcdef" for c in video_sha256):
        raise ValueError("invalid video SHA256")
    if type(duration_seconds) not in (int, float) or not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("invalid duration")
    proposals = proposal_result.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("invalid proposals")
    entries = []
    for p in proposals:
        if not isinstance(p, dict) or p.get("hand_verified") is not False or p.get("boundaries_verified") is not False:
            raise ValueError("confirmed hand not accepted")
        table, start, end = p.get("table_id"), p.get("start_observed_seconds"), p.get("end_observed_seconds")
        count, confidence = p.get("sample_count"), p.get("minimum_confidence")
        if type(table) is not int or table not in range(1, 5):
            raise ValueError("invalid table")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end, confidence)):
            raise ValueError("invalid numeric evidence")
        if not (0 <= start < end <= duration_seconds) or not (0 <= confidence <= 1) or type(count) is not int or count < 2:
            raise ValueError("invalid interval or evidence")
        states = p.get("board_states_observed")
        if not isinstance(states, list) or not states or any(s not in ("unknown", "none_visible", "flop", "turn", "river") for s in states):
            raise ValueError("invalid board observations")
        canonical = json.dumps([video_sha256, table, start, end], separators=(",", ":"))
        key = hashlib.sha256(canonical.encode()).hexdigest()[:20]
        entries.append(dict(proposal_id=key, video_sha256=video_sha256, table_id=table,
                            start_observed_seconds=start, end_observed_seconds=end,
                            sample_count=count, minimum_confidence=confidence,
                            board_states_observed=states, review_status="pending_human_review",
                            hand_verified=False, loss_bb=None, equity=None, ev=None,
                            clip_export_allowed=False,
                            note="May span multiple hands; observation times are not verified boundaries"))
    entries.sort(key=lambda x: (x["start_observed_seconds"], x["table_id"], x["proposal_id"]))
    ids = [e["proposal_id"] for e in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate proposal")
    return dict(schema_version=1, video_sha256=video_sha256, duration_seconds=duration_seconds,
                entries=entries, confirmed_hands=0, strategy_verified=False)
