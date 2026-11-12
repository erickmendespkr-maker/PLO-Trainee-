"""Conservative adapter between hypothetical range sensitivity and review EV binding.

Never converts hypothetical ranges into verified video evidence or GTO results.
"""
import math
import re

IDENT = re.compile(r"[A-Za-z0-9_.-]{1,80}\Z")

def adapt_sensitivity(source, scenario_id):
    if type(source) is not dict or type(scenario_id) is not str or not IDENT.fullmatch(scenario_id):
        raise ValueError("invalid source or scenario")
    flags = ("gto_solution", "strategic_error_established",
             "automatic_clip_selection_authorized", "range_uncertainty_included_in_ci")
    if (source.get("schema_version") != 1 or
        source.get("analysis_status") != "HYPOTHETICAL_RANGE_SENSITIVITY_ONLY" or
        any(source.get(k) is not False for k in flags)):
        raise ValueError("unsafe source provenance")
    p, c = source.get("pot_before_call_bb"), source.get("call_cost_bb")
    if (any(type(x) not in (int, float) or not math.isfinite(x) for x in (p, c))
        or not 0 <= p <= 1e6 or not 0 < c <= 1e6):
        raise ValueError("invalid pot or cost")
    rows = source.get("scenarios")
    if type(rows) is not list or not 2 <= len(rows) <= 12:
        raise ValueError("incompatible range count")
    converted, seen, labels = [], set(), set()
    for row in rows:
        if type(row) is not dict:
            raise ValueError("invalid row")
        rid = row.get("range_id")
        if type(rid) is not str or not IDENT.fullmatch(rid) or rid in seen:
            raise ValueError("duplicate or invalid range")
        seen.add(rid)
        q, ci, ev, bounds = (row.get(k) for k in (
            "equity", "equity_ci_conditional", "ev_call_bb", "ev_ci_conditional_bb"))
        if (type(ci) is not list or len(ci) != 2 or
            type(bounds) is not list or len(bounds) != 2 or
            any(type(x) not in (int, float) or not math.isfinite(x)
                for x in [q, *ci, ev, *bounds]) or
            not 0 <= ci[0] <= q <= ci[1] <= 1):
            raise ValueError("invalid equity interval")
        if (abs(ev-(q*(p+c)-c)) > 1e-6 or
            any(abs(y-(x*(p+c)-c)) > 1e-6 for x,y in zip(ci,bounds))):
            raise ValueError("inconsistent EV")
        label = ("positive_under_interval" if bounds[0] > 0 else
                 "negative_under_interval" if bounds[1] < 0 else
                 "uncertain_or_break_even")
        if (row.get("conditional_label") != label or
            type(row.get("iterations")) is not int or row["iterations"] < 1 or
            type(row.get("seed")) is not int or row["seed"] < 0):
            raise ValueError("invalid metadata")
        labels.add(label)
        converted.append({
            "range_id": rid, "equity": q, "equity_interval_conditional": ci,
            "ev_call_bb": ev, "ev_interval_conditional_bb": bounds,
            "conditional_label": label, "range_is_user_assumption": True,
            "range_uncertainty_included_in_interval": False})
    sensitive = labels not in ({"positive_under_interval"}, {"negative_under_interval"})
    odds = c/(p+c)
    be = source.get("break_even_equity")
    if (source.get("range_sensitive") is not sensitive or
        type(be) not in (int,float) or not math.isfinite(be) or abs(be-odds)>1e-8):
        raise ValueError("inconsistent summary")
    return {
        "schema_version": 1,
        "analysis_status": "hypothetical_weighted_range_ev_not_video_verified",
        "scenario_id": scenario_id, "pot_before_call_bb": p,
        "call_cost_bb": c, "break_even_equity": odds,
        "range_results": converted, "range_sensitive": sensitive,
        "source_hand_reconstruction_verified": False,
        "strategic_error_established": False,
        "automatic_clip_selection_authorized": False,
        "gto_solution": False, "range_uncertainty_included_in_interval": False,
        "warning": "Hypothetical ranges only; not verified against footage; not GTO."}
