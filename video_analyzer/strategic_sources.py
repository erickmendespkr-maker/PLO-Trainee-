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
    restricted: bool = False
    terms_url: str | None = None
    methodology: str | None = None
    distribution: str | None = None


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
    Dataset('pokerdata-plo5-preflop', 'PokerData', 'strategy', (5,),
            'https://pokerdata.io/ranges/plo5-preflop-ranges',
            restricted=True, terms_url='https://www.pokerstudy.ai/terms',
            methodology='HydraSolver, 6-max, 100 BB, 1.2 BB ante, 5% rake capped at 1 BB',
            distribution='Paid ZIP of gzipped JSON; browser viewing is not an export license'),
    Dataset('pokerdata-plo5-postflop', 'PokerData', 'strategy', (5,),
            'https://pokerdata.io/', restricted=True,
            terms_url='https://www.pokerstudy.ai/terms',
            methodology='Selected solved postflop trees; coverage is not exhaustive',
            distribution='Paid packs; API bulk export requires a separate license'),
    Dataset('omahasolve-plo5-equity', 'OmahaSolve', 'equity', (5,),
            'https://omahasolve.com/plo5-preflop-ranges', restricted=True,
            terms_url='https://omahasolve.com/terms',
            methodology='Simulated equity against random five-card hands',
            distribution='Public reference page; no open dataset export verified'),
    Dataset('omahasolve-plo6-equity', 'OmahaSolve', 'equity', (6,),
            'https://omahasolve.com/plo6-preflop-ranges', restricted=True,
            terms_url='https://omahasolve.com/terms',
            methodology='Simulated equity against random six-card hands',
            distribution='Public reference page; no open dataset export verified'),
    Dataset('omahasolve-plo5-ranges', 'OmahaSolve', 'heuristic', (5,),
            'https://omahasolve.com/plo5-preflop-ranges', restricted=True,
            terms_url='https://omahasolve.com/terms',
            methodology='Equity ranking mapped to PLO4 opening frequencies; not solved PLO5 strategy'),
    Dataset('omahasolve-plo6-ranges', 'OmahaSolve', 'heuristic', (6,),
            'https://omahasolve.com/plo6-preflop-ranges', restricted=True,
            terms_url='https://omahasolve.com/terms',
            methodology='Equity ranking mapped to PLO4 opening frequencies; not solved PLO6 strategy'),
)


def acquisition_plan(dataset_id, *, kind, variant):
    """Return a scoped candidate, not permission to write production records."""
    dataset = next((d for d in CATALOG if d.id == dataset_id), None)
    if dataset is None or type(variant) is not int or variant not in dataset.variants or kind != dataset.kind:
        raise ValueError('Unknown or incompatible dataset scope')
    eligible = not dataset.restricted and dataset.kind == 'equity' and dataset.license == 'CC BY 4.0' and bool(dataset.url and dataset.attribution)
    return {'dataset_id': dataset.id, 'kind': dataset.kind, 'variant': variant,
            'status': 'LICENSE_CANDIDATE' if eligible else ('RESTRICTED' if dataset.restricted else 'PERMISSION_PENDING'),
            'download_url': dataset.url if eligible else None,
            'license': dataset.license, 'attribution': dataset.attribution,
            'license_url': LICENSE_URL if eligible else None,
            'evidence_url': dataset.evidence, 'reviewed_on': REVIEWED_ON,
            'advertised_rows': dataset.advertised_rows,
            'terms_url': dataset.terms_url, 'methodology': dataset.methodology,
            'distribution': dataset.distribution,
            'verified_rows': 0, 'production_import_allowed': False}
