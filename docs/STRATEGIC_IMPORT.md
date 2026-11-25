# Offline strategic fixture import — format v1

The adapters accept UTF-8 or UTF-8 BOM, up to 8 MiB and 10,000 records.
Only synthetic fixtures may be imported at this stage. No production data,
license approvals, network requests or changes to the schema are performed.

JSON envelope (synthetic example, not a recommended poker strategy):

```json
{"format":"plo-strategy-v1","records":[{"variant":5,"scenario":{"position":"BTN"},"actions":{"fold":0.2,"raise":0.8}}]}
```

CSV uses the exact header `variant,scenario,actions`. The scenario and actions
cells contain JSON objects escaped according to CSV quoting rules. TXT uses the
same three columns separated by tabs (TSV with a .txt suffix); arbitrary text
or provider-specific exports are not supported. Variant is 5 or 6.
Frequencies must be finite numbers in [0,1] summing to 1 within 1e-6.

```python
from contextlib import closing
import strategic_store as store
from strategic_import import import_fixture

with closing(store.connect('test-strategy.sqlite')) as db:
    source = store.add_source(db, 'synthetic fixture', 'test only', 'local test')
    print(import_fixture(db, 'fixture.json', source_id=source, synthetic=True))
```

All records are validated before writing. A single transaction inserts the
batch, rolls back on failure, and counts identical records as duplicates.
The returned report contains the file SHA-256, format, source ID, number read,
inserted and duplicates. Reports are not yet stored as persistent import lots.
The default lookup excludes fixtures. Scenario validation remains structural;
card, position, street, units and EV normalization are later work.

Run from video_analyzer:

```sh
python -m unittest -v test_strategic_store test_strategic_backup test_strategic_import
```

Block 04: 42 tests passed locally (11 new, 31 regressions). No provider dataset
has been authorized or imported. Windows and the full repository suite remain
unverified.
