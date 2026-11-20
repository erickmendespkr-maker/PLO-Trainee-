"""Reaudit a saved conditional report against its bound monetary assumptions.

Integrity is not evidence that monetary inputs were observed in footage. A SHA
stored alongside its payload is not a signature and cannot prevent coordinated
replacement of both; independently trusted digests are required for that.
"""
from offline_ev_monetary_binding import bind_monetary_assumptions
from offline_mc_sample_provenance_audit import audit_sample_provenance
from offline_mc_ev_arithmetic_audit import audit_mc_ev_arithmetic


def reaudit_bound_report(report, samples_by_scenario, *, expected_binding_sha256=None):
    """Fail closed on absent/changed monetary binding and inconsistent EV.

    Optional expected_binding_sha256 must originate outside the report, e.g. a
    trusted review record; it prevents coordinated payload+digest replacement.
    """
    if type(report) is not dict or type(samples_by_scenario) is not dict:
        raise ValueError('report and samples must be dictionaries')
    binding = report.get('monetary_binding')
    if type(binding) is not dict or set(binding) != {'assumptions', 'sha256', 'source'}:
        raise ValueError('missing or malformed monetary binding')
    assumptions = binding['assumptions']
    if type(assumptions) is not dict or set(assumptions) != {
        'model', 'pot_before_call', 'call_cost', 'rake', 'unit'
    } or assumptions['model'] != 'hypothetical_heads_up_single_call':
        raise ValueError('unsupported monetary assumptions')
    if binding['source'] != 'caller_supplied_not_video_verified':
        raise ValueError('unsupported monetary source')
    expected = bind_monetary_assumptions(
        pot_before_call=assumptions['pot_before_call'],
        call_cost=assumptions['call_cost'], rake=assumptions['rake'],
        currency_unit=assumptions['unit'])
    if binding != expected:
        raise ValueError('monetary digest or payload mismatch')
    if expected_binding_sha256 is not None:
        if type(expected_binding_sha256) is not str or len(expected_binding_sha256) != 64:
            raise ValueError('invalid trusted digest')
        if binding['sha256'] != expected_binding_sha256:
            raise ValueError('trusted monetary digest mismatch')
    provenance = audit_sample_provenance(report, samples_by_scenario)
    arithmetic = audit_mc_ev_arithmetic(
        report, samples_by_scenario,
        pot_before_call=assumptions['pot_before_call'],
        call_cost=assumptions['call_cost'], rake=assumptions['rake'])
    if provenance.get('sample_hashes_verified') != len(samples_by_scenario):
        raise ValueError('incomplete sample audit')
    if arithmetic.get('ev_arithmetic_verified') is not True:
        raise ValueError('incomplete arithmetic audit')
    return {
        'monetary_binding_integrity_verified': True,
        'trusted_monetary_digest_checked': expected_binding_sha256 is not None,
        'sample_hashes_verified': provenance['sample_hashes_verified'],
        'ev_arithmetic_verified': True,
        'video_observations_verified': False,
        'range_assumptions_verified': False,
        'equity_engine_executed': False,
        'strategic_verdict_allowed': False,
    }
