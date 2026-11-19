"""Join reviewed loss evidence to offline hand proposals; never infer EV or GTO."""
from .offline_loss_evidence import classify_hand_evidence
from .offline_review_priority import build_review_queue

def build_loss_review_handoff(proposals, evidence, *, limit=200):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("invalid limit")
    if not isinstance(proposals, list) or not isinstance(evidence, list):
        raise ValueError("proposals and evidence must be lists")
    # The queue helper caps each invocation at 1000 entries. Process every
    # chunk before global ranking to avoid losing late hands in long sessions.
    entries = []
    for offset in range(0, len(proposals), 1000):
        entries.extend(build_review_queue(proposals[offset:offset + 1000], limit=1000)["review_queue"])
    if len({p["hand_id"] for p in entries}) != len(entries):
        raise ValueError("duplicate hand ID across batches")
    queue = {"review_queue": entries}
    identities = {(p["hand_id"], p["table_id"]) for p in entries}
    by_key = {}
    for raw in evidence:
        result = classify_hand_evidence(raw)
        key = (result["hand_id"], result["table_id"])
        if key in by_key or key not in identities:
            raise ValueError("duplicate or orphan evidence")
        by_key[key] = result
    ordered = []
    for item in queue["review_queue"]:
        loss = by_key.get((item["hand_id"], item["table_id"]))
        ordered.append({**item, "loss_evidence": loss,
            "loss_over_30bb": bool(loss and loss["loss_over_30bb"]),
            "review_required": True, "strategy_verified": False})
    ordered.sort(key=lambda r: (not r["loss_over_30bb"],
        -(r["loss_evidence"]["confirmed_loss_bb"] or 0) if r["loss_evidence"] else 0,
        -r["hero_invested_bb"], r["start_seconds"], r["hand_id"]))
    return {"schema_version": 1, "analysis_verified": False, "is_gto": False,
        "ranking_basis": "confirmed_loss_over_30bb_then_investment_not_ev",
        "total_proposals": len(ordered),
        "confirmed_over_30bb": sum(x["loss_over_30bb"] for x in ordered),
        "review_queue": ordered[:limit]}
