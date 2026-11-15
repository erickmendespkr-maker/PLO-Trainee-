"""Plan safe, deterministic exports from unverified review handoff records."""
from pathlib import Path
try:
    from .offline_handoff_review_records import review_records_from_handoff
except ImportError:
    from offline_handoff_review_records import review_records_from_handoff


def plan_review_exports(handoff, output_directory):
    """Produce export requests, not exported or verified hands.

    The caller must explicitly invoke the existing FFmpeg exporter for each item.
    """
    records = review_records_from_handoff(handoff)
    directory = Path(output_directory)
    result = []
    names = set()
    for index, record in enumerate(records, 1):
        filename = f"review_table{record['table_id']}_{index:04d}.mp4"
        if filename in names:
            raise ValueError('duplicate export filename')
        names.add(filename)
        destination = directory / filename
        if destination.exists() or destination.with_suffix('.json').exists():
            raise FileExistsError(f'output exists: {destination}')
        result.append({'destination': str(destination), 'record': record,
                       'status': 'PLANNED_ONLY', 'human_review_required': True})
    return result
