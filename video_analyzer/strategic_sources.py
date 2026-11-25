"""Reviewed public source catalog; no network or automatic license approvals."""
from dataclasses import dataclass

REVIEWED_ON = '2026-11-25'
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'


@dataclass(frozen=True)
class Dataset:
    id: str
    provider: str
    kind: str
    variants: tuple
    evidence: str
    url: str | None = None
    license: str | None = None
    advertised_rows: int | None = None
    attribution: str | None = None


CATALOG = (
    Dataset('plospot-preflop', 'PLO Spot', 'strategy', (5,),
            'https://plospot.com/data-and-method.html'),
    Dataset('solvepoker-strategy', 'SolvePoker', 'strategy', (5,),
            'https://solvepoker.app/methodology'),
    Dataset('solvepoker-plo5-equity', 'SolvePoker', 'equity', (5,),
            'https://solvepoker.app/plo5-starting-hand-rankings',
            'https://solvepoker.app/data/plo5-hand-rankings.csv',
            'CC BY 4.0', 134459, 'solvepoker.app'),
    Dataset('solvepoker-plo6-equity-top10000', 'SolvePoker', 'equity', (6,),
            'https://solvepoker.app/plo5-starting-hand-rankings',
            'https://solvepoker.app/data/plo6-hand-rankings-top10000.csv',
            'CC BY 4.0', 10000, 'solvepoker.app'),
)


def acquisition_plan(dataset_id, *, kind, variant):
    """Return a scoped candidate, not permission to write production records."""
    dataset = next((d for d in CATALOG if d.id == dataset_id), None)
    if dataset is None or type(variant) is not int or variant not in dataset.variants or kind != dataset.kind:
        raise ValueError('Unknown or incompatible dataset scope')
    eligible = dataset.kind == 'equity' and dataset.license == 'CC BY 4.0' and bool(dataset.url and dataset.attribution)
    return {'dataset_id': dataset.id, 'kind': dataset.kind, 'variant': variant,
            'status': 'LICENSE_CANDIDATE' if eligible else 'PERMISSION_PENDING',
            'download_url': dataset.url if eligible else None,
            'license': dataset.license, 'attribution': dataset.attribution,
            'license_url': LICENSE_URL if eligible else None,
            'evidence_url': dataset.evidence, 'reviewed_on': REVIEWED_ON,
            'advertised_rows': dataset.advertised_rows,
            'verified_rows': 0, 'production_import_allowed': False}
