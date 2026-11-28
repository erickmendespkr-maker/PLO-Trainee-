"""Offline PLO5 conditional terminal accounting; never certify video outcomes."""
from fractions import Fraction


def require(ok, message):
    if not ok:
        raise ValueError(message)


def terminal_accounting(before, committed, folded, after, external, *, rake=None):
    """Integer chips; before = pre-blind stacks, after = post-award stacks.

    external is an explicit signed net transfer per dealt seat (including zero).
    None means unknown, never assume a rebuy from a stack increase. Aggregate
    awards are conditional; allocation across side pots is deliberately unknown.
    """
    require(type(before) is dict and 2 <= len(before) <= 6, 'Invalid dealt roster')
    seats = list(before)
    for row in (committed, folded, after, external):
        require(type(row) is dict and set(row) == set(seats), 'Roster mismatch')
    for p in seats:
        require(type(p) is str and bool(p), 'Invalid seat')
        require(all(type(row[p]) is int and 0 <= row[p] <= 10**9 for row in (before, committed)), 'Invalid chips')
        require(committed[p] <= before[p] and type(folded[p]) is bool, 'Invalid contribution/fold')
        require(after[p] is None or type(after[p]) is int and 0 <= after[p] <= 10**9, 'Invalid final stack')
        require(external[p] is None or type(external[p]) is int and abs(external[p]) <= 10**9, 'Invalid external transfer')
    require(rake is None or type(rake) is int and rake >= 0, 'Invalid rake')
    top, second = sorted(committed.values(), reverse=True)[:2]
    require(second > 0 and any(not x for x in folded.values()), 'No contested pot')
    returned = {p: top-second if committed[p] == top else 0 for p in seats}
    net = {p: committed[p]-returned[p] for p in seats}
    require(all(folded[p] or net[p] == max(net.values()) or committed[p] == before[p] and not returned[p] for p in seats), 'Lower eligible contribution requires all-in')
    layers = []
    previous = 0
    for cap in sorted(set(net.values())-{0}):
        contributors = [p for p in seats if net[p] >= cap]
        eligible = [p for p in contributors if not folded[p]]
        require(len(contributors) >= 2 and eligible, 'Invalid pot layer')
        layers.append(dict(cap=cap, gross=(cap-previous)*len(contributors), eligible=eligible))
        previous = cap
    gross = sum(net.values())
    require(rake is None or rake < gross, 'Rake exceeds pot')
    result = dict(status='MISSING_BALANCE_OR_TRANSFER', returned=returned, net_committed=net, layers=layers, gross=gross, rake_residual=None, aggregate_awards=None, conditional_net=None, financial_result_verified=False, complete_hand_verified=False, strategy_authorized=False)
    if any(after[p] is None or external[p] is None for p in seats):
        return result
    awards = {p: after[p]-before[p]+net[p]-external[p] for p in seats}
    residual = gross-sum(awards.values())
    result['rake_residual'] = residual
    if residual < 0 or residual >= gross or rake is not None and residual != rake or any(v < 0 or folded[p] and v for p,v in awards.items()):
        result['status'] = 'BALANCE_CONFLICT'
        return result
    # Eligibility sets are nested. Allocate each seat's demand from its most
    # restricted eligible layers first; unused layer capacity can be rake.
    capacity = [l['gross'] for l in layers]
    for p in sorted(seats, key=lambda p: sum(p in l['eligible'] for l in layers)):
        remaining = awards[p]
        for i in reversed(range(len(layers))):
            if p in layers[i]['eligible']:
                take = min(remaining, capacity[i]); capacity[i] -= take; remaining -= take
        if remaining:
            result['status'] = 'SIDE_POT_ELIGIBILITY_CONFLICT'
            return result
    if rake is None:
        result['status'] = 'RAKE_UNDECLARED'
        return result
    result.update(status='CONDITIONAL_AGGREGATE_ACCOUNTING', aggregate_awards=awards, conditional_net={p: awards[p]-net[p] for p in seats})
    return result


def display_balance(before, after, pot_before, pot_after):
    """Exact screen-total delta only, without assigning payout, rake or rebuy."""
    if set(before) != set(after) or not before or any(v is None for v in (pot_before,pot_after,*before.values(),*after.values())):
        return dict(status='INCOMPLETE_DISPLAY_ROSTER', residual_bb=None)
    delta = sum(Fraction(after[p])-Fraction(before[p]) for p in before)+Fraction(pot_after)-Fraction(pot_before)
    return dict(status='DISPLAY_TOTAL_CONSERVED' if delta == 0 else 'DISPLAY_TOTAL_CHANGED', residual_bb=[delta.numerator,delta.denominator])
