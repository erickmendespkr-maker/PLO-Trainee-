"""Fail-closed evidence gate for offline video hand review; no GTO claims."""
import math

def review_gate(hand):
    if not isinstance(hand, dict):
        raise ValueError("hand must be a dictionary")
    reasons = []
    if hand.get("review_status") != "HUMAN_CONFIRMED":
        reasons.append("human_review_missing")
    game = hand.get("game")
    if game not in ("PLO5", "PLO6"):
        reasons.append("game_unverified")
    table = hand.get("table_id")
    if type(table) is not int or table not in range(1, 5):
        reasons.append("table_unverified")
    start, end = hand.get("hand_start_seconds"), hand.get("hand_end_seconds")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end)) or start < 0 or end <= start:
        reasons.append("hand_interval_unverified")
    hero, board = hand.get("hero_cards"), hand.get("board_cards")
    expected = {"PLO5": 5, "PLO6": 6}.get(game)
    if not isinstance(hero, list) or expected is None or len(hero) != expected:
        reasons.append("hero_cards_unverified")
    if not isinstance(board, list) or len(board) not in (3, 4, 5):
        reasons.append("board_unverified")
    if isinstance(hero, list) and isinstance(board, list):
        cards = hero + board
        if any(not isinstance(c, str) or len(c) != 2 or c[0] not in "23456789TJQKA" or c[1] not in "cdhs" for c in cards) or len(cards) != len(set(cards)):
            reasons.append("invalid_or_duplicate_cards")
    if hand.get("action") not in ("fold", "call", "raise"):
        reasons.append("action_unverified")
    for key in ("pot_before_action", "amount_to_call"):
        v = hand.get(key)
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
            reasons.append(key + "_unverified")
    evidence = hand.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(
        not isinstance(e, dict) or e.get("human_verified") is not True
        or type(e.get("pts_seconds")) not in (int, float)
        or not math.isfinite(e["pts_seconds"])
        or e["pts_seconds"] < 0
        or (type(start) in (int, float) and type(end) in (int, float)
            and math.isfinite(start) and math.isfinite(end)
            and not (start <= e["pts_seconds"] <= end))
        or not isinstance(e.get("frame_sha256"), str)
        or len(e["frame_sha256"]) != 64
        or any(ch not in "0123456789abcdef" for ch in e["frame_sha256"])
        for e in evidence
    ):
        reasons.append("frame_evidence_unverified")
    if isinstance(evidence, list) and evidence and all(isinstance(e, dict) for e in evidence):
        source_hash = hand.get("source_video_sha256")
        if not isinstance(source_hash, str) or len(source_hash) != 64 or any(ch not in "0123456789abcdef" for ch in source_hash):
            reasons.append("source_video_hash_missing")
        if any(e.get("source_video_sha256") != source_hash for e in evidence):
            reasons.append("source_video_link_unverified")
        if any(e.get("table_id") != table for e in evidence):
            reasons.append("frame_table_link_unverified")
    if not isinstance(hand.get("range_assumptions"), dict) or not hand["range_assumptions"]:
        reasons.append("opponent_range_missing")
    if not isinstance(hand.get("model_assumptions"), dict) or not hand["model_assumptions"]:
        reasons.append("ev_model_missing")
    return {"status": "INSUFFICIENT_DATA" if reasons else "CONDITIONAL_ANALYSIS_PERMITTED",
            "reasons": sorted(set(reasons)), "gto_claim_permitted": False,
            "automatic_blunder_label_permitted": False}
