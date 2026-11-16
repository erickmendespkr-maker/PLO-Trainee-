"""Fail-closed eligibility gate for offline conditional analysis. Never labels a GTO error."""
import math

def assess(record):
    required=("video_sha256","table_id","hand_id","start_pts","end_pts","hero_cards","board_cards","action","pot_before","call_cost","ranges","equity_seed","equity_trials","equity_ci_low","equity_ci_high")
    if not isinstance(record,dict):
        return {"eligible":False,"status":"INSUFFICIENT_DATA","reasons":["invalid_record"]}
    reasons=[f"missing_{k}" for k in required if record.get(k) is None]
    sha=record.get("video_sha256")
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):
        reasons.append("invalid_sha256")
    for flag in ("human_reviewed","cards_visibility_confirmed","action_amounts_confirmed","model_assumptions_reviewed"):
        if record.get(flag) is not True: reasons.append("unconfirmed_"+flag)
    variant=record.get("variant")
    if variant not in ("PLO5","PLO6"): reasons.append("invalid_variant")
    hero,board=record.get("hero_cards"),record.get("board_cards")
    if not isinstance(hero,(list,tuple)) or len(hero)!={"PLO5":5,"PLO6":6}.get(variant,-1):
        reasons.append("invalid_hero")
    if not isinstance(board,(list,tuple)) or not 3<=len(board)<=5:
        reasons.append("invalid_board")
    cards=list(hero)+list(board) if isinstance(hero,(list,tuple)) and isinstance(board,(list,tuple)) else []
    if len(cards)!=len(set(map(str,cards))) or any(not isinstance(c,str) or len(c)!=2 or c[0] not in "23456789TJQKA" or c[1] not in "cdhs" for c in cards):
        reasons.append("invalid_cards")
    numeric=("start_pts","end_pts","pot_before","call_cost","equity_ci_low","equity_ci_high")
    for key in numeric:
        value=record.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            reasons.append("invalid_"+key)
    def finite(k):
        v=record.get(k)
        return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    if finite("start_pts") and finite("end_pts") and not 0<=record["start_pts"]<record["end_pts"]:
        reasons.append("invalid_pts_order")
    for key in ("pot_before","call_cost"):
        if finite(key) and record[key]<0: reasons.append("negative_"+key)
    if finite("equity_ci_low") and finite("equity_ci_high") and not 0<=record["equity_ci_low"]<=record["equity_ci_high"]<=1:
        reasons.append("invalid_equity_interval")
    for key in ("equity_seed","equity_trials"):
        if type(record.get(key)) is not int or (key=="equity_trials" and record[key]<=0):
            reasons.append("invalid_"+key)
    if not isinstance(record.get("ranges"),dict) or not record["ranges"]:
        reasons.append("missing_ranges")
    if record.get("range_sensitive") is True:
        reasons.append("range_sensitive")
    reasons=sorted(set(reasons))
    return {"eligible":not reasons,"status":"INSUFFICIENT_DATA" if reasons else "CONDITIONAL_REVIEW_ONLY","reasons":reasons,"disclaimer":"Hypothetical range-dependent estimate, not GTO or a proven error."}
