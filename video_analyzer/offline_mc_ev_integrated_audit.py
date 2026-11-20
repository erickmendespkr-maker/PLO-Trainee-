"""Fail-closed integration of existing offline conditional EV report audits.

This module audits supplied hypothetical shares; it does not generate poker
equity samples, inspect footage, or certify a strategy.
"""
from offline_mc_ev_report import build_mc_ev_report
from offline_mc_sample_provenance_audit import audit_sample_provenance
from offline_mc_ev_arithmetic_audit import audit_mc_ev_arithmetic


def build_and_audit_conditional_report(*, video_sha256, hand_id, reviewed,
                                       variant, pot_before_call, call_cost,
                                       scenarios, rake=0.0, confidence=0.95):
    """Build a report and independently verify hashes and arithmetic.

    The input scenarios contain {seed, shares, range_description}. The seed
    is provenance metadata, not proof that samples came from that seed.
    """
    report = build_mc_ev_report(
        video_sha256=video_sha256, hand_id=hand_id, reviewed=reviewed,
        variant=variant, pot_before_call=pot_before_call,
        call_cost=call_cost, scenarios=scenarios, rake=rake,
        confidence=confidence)
    samples = {name: item["shares"] for name, item in scenarios.items()}
    provenance = audit_sample_provenance(report, samples)
    arithmetic = audit_mc_ev_arithmetic(
        report, samples, pot_before_call=pot_before_call,
        call_cost=call_cost, rake=rake)
    if provenance.get("sample_hashes_verified") != len(samples):
        raise ValueError("incomplete provenance verification")
    if arithmetic.get("ev_arithmetic_verified") is not True:
        raise ValueError("arithmetic not verified")
    return {
        "report": report,
        "audit": {
            "sample_hashes_verified": provenance["sample_hashes_verified"],
            "ev_arithmetic_verified": True,
            "video_observations_verified": False,
            "sampling_independence_verified": False,
            "range_assumptions_verified": False,
            "equity_engine_executed": False,
            "strategic_verdict_allowed": False,
        },
    }
