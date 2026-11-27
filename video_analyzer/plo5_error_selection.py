"""PLO5 offline study selection. Solver adapter must supply comparable action EV bounds."""
from math import isfinite

def select_errors(decisions):
    """Return one record per confirmed erroneous decision; no financial outcome filter.
    EV intervals must include numerical and model uncertainty; values are incremental BB.
    The upstream adapter must certify reconstruction and strategic model applicability.
    """
    errors, unresolved = [], []
    seen = set()
    for d in decisions:
        key = (d["hand_id"], d["decision_id"])
        if key in seen:
            raise ValueError("duplicate decision")
        seen.add(key)
        if not (d.get("reconstruction_verified") is True and d.get("strategy_verified") is True):
            unresolved.append(key)
            continue
        ev = d["action_ev_bounds"]
        actual = d["action"]
        if actual not in ev or len(ev) < 2:
            unresolved.append(key)
            continue
        for lo, hi in ev.values():
            if not (isfinite(lo) and isfinite(hi) and lo <= hi):
                raise ValueError("invalid EV bounds")
        best = max(ev, key=lambda a: ev[a][0])
        lower_loss = ev[best][0] - ev[actual][1]
        upper_loss = max(v[1] for v in ev.values()) - ev[actual][0]
        if lower_loss > 0:
            errors.append({"hand_id": key[0], "decision_id": key[1],
                           "street": d["street"], "actual": actual,
                           "recommended": best, "ev_loss_lower_bb": lower_loss,
                           "ev_loss_upper_bb": upper_loss,
                           "pot_odds": d.get("pot_odds"),
                           "evidence": d.get("evidence")})
        elif upper_loss > 0:
            unresolved.append(key)
    return {"errors": errors, "unresolved": unresolved, "decisions_checked": len(seen)}
