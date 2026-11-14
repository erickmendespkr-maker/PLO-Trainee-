"""Offline bridge: reproducible hypothetical PLO showdown samples to conditional call EV.

No video/OCR evidence is inferred. Only heads-up single-pot call, no future betting.
"""
from .offline_omaha_monte_carlo import sample_showdown_shares
from .offline_equity_ev_uncertainty import evaluate_sampled_call_scenarios


def analyze_hypothetical_call(*, hero, board, range_scenarios, pot_before_call,
                              call_cost, iterations=1000, seed=0, confidence=0.95,
                              rake_fraction=0, rake_cap=0, max_attempts=None):
    """Compute conditional EV with simultaneous sampling intervals across named ranges.

    Every scenario uses a distinct deterministic seed. Samples represent a fixed
    hypothetical opponent range, not OCR uncertainty, opponent-range confidence,
    or a GTO solution. The underlying EV model is heads-up only.
    """
    if not isinstance(range_scenarios, (list, tuple)) or not range_scenarios:
        raise ValueError("nonempty range scenarios required")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if len(range_scenarios) > 100:
        raise ValueError("too many scenarios")
    names = set()
    sampled = []
    provenance = []
    for index, scenario in enumerate(range_scenarios):
        if not isinstance(scenario, dict) or set(scenario) != {"name", "opponent_range"}:
            raise ValueError("scenario requires name and opponent_range")
        name = scenario["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("scenario names must be unique nonempty strings")
        names.add(name)
        result = sample_showdown_shares(
            hero=hero, board=board, opponent_ranges=[scenario["opponent_range"]],
            iterations=iterations, seed=seed + index,
            max_attempts=max_attempts)
        sampled.append({"name": name, "shares": result["shares"]})
        provenance.append({"name": name, "seed": result["seed"],
                           "iterations": result["iterations"],
                           "attempts": result["attempts"],
                           "sampling_method": result["sampling_method"]})
    analysis = evaluate_sampled_call_scenarios(
        pot_before_call=pot_before_call, call_cost=call_cost,
        scenarios=sampled, confidence=confidence,
        rake_fraction=rake_fraction, rake_cap=rake_cap)
    return {**analysis, "sampling_provenance": provenance,
            "evidence_source": "hypothetical_cards_and_ranges_only",
            "video_hand_verified": False, "ocr_verified": False,
            "gto_solution": False}
