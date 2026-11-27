"""PLO5 offline study selection using comparable incremental EV intervals (BB)."""
from math import isfinite


def select_errors(decisions):
    """Classify decisions using certified reconstruction and model applicability.

    EV bounds must include numerical and model uncertainty. A recommended
    alternative is provably better than the observed action, not necessarily
    uniquely optimal among all alternatives. No financial outcome filter.
    """
    errors, unresolved, adequate = [], [], []
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
        alternatives = {a: bounds for a, bounds in ev.items() if a != actual}
        best = max(alternatives, key=lambda a: alternatives[a][0])
        lower_loss = max(0.0, alternatives[best][0] - ev[actual][1])
        upper_loss = max(0.0, max(v[1] for v in alternatives.values()) - ev[actual][0])
        if lower_loss > 0:
            errors.append({"hand_id": key[0], "decision_id": key[1],
                           "street": d["street"], "actual": actual,
                           "recommended": best, "ev_loss_lower_bb": lower_loss,
                           "ev_loss_upper_bb": upper_loss,
                           "pot_odds": d.get("pot_odds"),
                           "evidence": d.get("evidence")})
        elif upper_loss > 0:
            unresolved.append(key)
        else:
            adequate.append(key)
    return {"errors": errors, "unresolved": unresolved, "adequate": adequate,
            "decisions_checked": len(seen)}
