"""Conservative evidence classification for losses in recorded PLO sessions."""
import math

def classify_hand_evidence(hand):
    if not isinstance(hand, dict): raise ValueError("invalid hand")
    hid, table = hand.get("hand_id"), hand.get("table_id")
    if not isinstance(hid,str) or not 1<=len(hid)<=128 or type(table) is not int or table not in (1,2,3,4): raise ValueError("invalid identity")
    invested=hand.get("hero_invested_bb")
    if type(invested) not in (int,float) or not math.isfinite(invested) or not 0<=invested<=100000: raise ValueError("invalid investment")
    for key in ("fold_visible","fold_human_verified","investment_human_verified","stack_human_verified"):
        if hand.get(key) is not None and type(hand[key]) is not bool: raise ValueError("invalid boolean")
    before,after=hand.get("stack_before_bb"),hand.get("stack_after_bb")
    if (before is None)!=(after is None): raise ValueError("partial stack")
    net=None
    if before is not None:
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (before,after)): raise ValueError("invalid stack")
        adj=hand.get("stack_adjustments_bb")
        if adj is not None and (type(adj) not in (int,float) or not math.isfinite(adj)): raise ValueError("invalid adjustment")
        if hand.get("stack_human_verified") is True and adj is not None: net=after-before-adj
    loss=None
    reason="INSUFFICIENT_EVIDENCE"
    if hand.get("fold_visible") is True and hand.get("fold_human_verified") is True and hand.get("investment_human_verified") is True:
        loss=float(invested)
        reason="CONFIRMED_FOLD_INVESTMENT"
        if net is not None and not math.isclose(net,-invested,abs_tol=.02):
            loss=None
            reason="CONFLICTING_EVIDENCE"
    elif net is not None:
        if net < -.02:
            loss=-net
            reason="RECONCILED_STACK_LOSS"
        else: reason="NO_CONFIRMED_LOSS"
    return {"schema_version":1,"hand_id":hid,"table_id":table,"invested_bb":float(invested),"confirmed_loss_bb":loss,"loss_over_30bb":loss is not None and loss>30,"classification":reason,"review_required":loss is None,"strategy_verified":False,"is_gto":False}
