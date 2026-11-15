"""Audit raw offline showdown samples; this does not infer ranges or solve GTO."""
import math


def audit_showdown_samples(result):
    """Validate Monte Carlo provenance and report a conservative 95% bound.

    Hoeffding assumes independent draws from a fixed conditional range model.
    It does not cover OCR errors, range misspecification or video uncertainty.
    """
    if not isinstance(result, dict):
        raise ValueError('sample result must be a mapping')
    shares = result.get('shares')
    n = result.get('iterations')
    attempts = result.get('attempts')
    seed = result.get('seed')
    if not isinstance(shares, (list, tuple)) or not shares:
        raise ValueError('nonempty shares required')
    if type(n) is not int or n != len(shares) or n <= 0:
        raise ValueError('iteration count mismatch')
    if type(attempts) is not int or attempts < n:
        raise ValueError('invalid attempt count')
    if type(seed) is not int:
        raise ValueError('integer seed required')
    if result.get('gto_solution') is not False:
        raise ValueError('GTO provenance must be explicitly false')
    if result.get('range_uncertainty_included') is not False:
        raise ValueError('range uncertainty must be explicitly excluded')
    if result.get('ocr_uncertainty_included') is not False:
        raise ValueError('OCR uncertainty must be explicitly excluded')
    if any(type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1 for x in shares):
        raise ValueError('shares must be finite fractions between zero and one')
    mean = math.fsum(shares) / n
    radius = math.sqrt(math.log(40) / (2 * n))
    return {
        'equity_mean': mean,
        'confidence_interval_95': [max(0., mean-radius), min(1., mean+radius)],
        'confidence_method': 'hoeffding_two_sided_95_fixed_range_iid',
        'iterations': n, 'attempts': attempts, 'seed': seed,
        'acceptance_rate': n / attempts,
        'range_uncertainty_included': False,
        'ocr_uncertainty_included': False,
        'gto_solution': False,
    }
