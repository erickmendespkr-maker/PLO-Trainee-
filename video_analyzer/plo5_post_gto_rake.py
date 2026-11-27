"""Exact HU river terminal ledger. Not a rake-aware strategy solver."""
from fractions import Fraction
from plo5_pre_gto_context import need, integer


def settle(state, showdown_share, rake_bps, rake_cap, *, rake_on_fold):
    need(len(state.order) == 2 and len(state.board) == 5 and not state.pending and
         state.status in ('fold_terminal', 'river_showdown', 'all_in_showdown'), 'HU river terminal required')
    need(type(rake_on_fold) is bool, 'Explicit fold rake rule required')
    need(integer(rake_bps) <= 10000, 'Invalid rake rate')
    integer(rake_cap)
    need(type(showdown_share) in (int, Fraction) and showdown_share in (0, Fraction(1,2), 1), 'Invalid showdown share')
    a,b = state.total_paid
    m = min(a,b)
    contested = state.base_pot + 2*m
    fold = len(state.active) == 1
    q = Fraction(int(state.active[0] == 0)) if fold else Fraction(showdown_share)
    # Explicit model: cap is chips (zero cap means zero rake); floor to integer chip.
    rake = min(rake_cap, contested*rake_bps//10000) if (not fold or rake_on_fold) else 0
    returned = (a-m,b-m)
    awards = (q*(contested-rake),(1-q)*(contested-rake))
    utility = tuple(award-m for award in awards)
    need(sum(awards)+sum(returned)+rake == state.pot, 'Ledger not conserved')
    need(sum(utility)+rake == state.base_pot, 'Utility not conserved')
    return dict(contested=contested, rake=rake, returned=returned, awards=awards,
                utility_chips=utility, utility_bb=tuple(v/state.bb for v in utility),
                rounding='floor_chip', cap_semantics='zero_cap_zero_rake', rake_on_fold=rake_on_fold,
                split_semantics='fractional_chip_no_odd_chip_rule', room_rules_verified=False, gto_solution=False)
