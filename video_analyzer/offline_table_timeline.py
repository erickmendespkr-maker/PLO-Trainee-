"""Conservative offline timeline of observed table presence; not hand detection."""
import math

def build_table_timeline(observations, *, max_gap_seconds=15.0):
    if not isinstance(observations, list):
        raise ValueError('observations must be a list')
    if type(max_gap_seconds) not in (float, int) or not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0:
        raise ValueError('invalid maximum gap')
    samples = []
    previous = -1.0
    for sample in observations:
        if not isinstance(sample, dict):
            raise ValueError('invalid observation')
        t = sample.get('timestamp_seconds')
        if type(t) not in (int, float) or not math.isfinite(t) or t < 0 or t <= previous:
            raise ValueError('timestamps must be finite and strictly increasing')
        previous = t
        tables = sample.get('tables')
        if not isinstance(tables, list):
            raise ValueError('invalid table list')
        ids = set()
        for table in tables:
            if not isinstance(table, dict):
                raise ValueError('invalid table evidence')
            ident, confidence = table.get('table_id'), table.get('confidence')
            if type(ident) is not int or ident not in range(1, 5) or ident in ids:
                raise ValueError('invalid or repeated table id')
            if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError('invalid confidence')
            ids.add(ident)
        samples.append((float(t), {v['table_id']: float(v['confidence']) for v in tables}))
    segments = []
    for table_id in range(1, 5):
        current = None
        for t, tables in samples:
            if table_id not in tables:
                if current is not None:
                    segments.append(current)
                    current = None
                continue
            confidence = tables[table_id]
            if current is None or t - current['last_observed_seconds'] > max_gap_seconds:
                if current is not None:
                    segments.append(current)
                current = {'table_id': table_id, 'first_observed_seconds': t,
                           'last_observed_seconds': t, 'sample_count': 1,
                           'minimum_confidence': confidence, 'verified_by_human': False}
            else:
                current['last_observed_seconds'] = t
                current['sample_count'] += 1
                current['minimum_confidence'] = min(current['minimum_confidence'], confidence)
        if current is not None:
            segments.append(current)
    segments.sort(key=lambda s: (s['first_observed_seconds'], s['table_id']))
    return {'schema_version': 1, 'segments': segments, 'observation_count': len(samples),
            'hand_boundaries_verified': False, 'analysis_verified': False,
            'interpretation': 'table presence proposals at observed timestamps only'}
