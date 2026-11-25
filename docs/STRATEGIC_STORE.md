# Strategic SQLite store — offline foundation (blocks 01–03)

The v3 store is a local Python/SQLite library for recorded-session analysis.
It contains no licensed production strategy data. Real record writes are disabled;
all examples are synthetic tests, not solver results. No network access is required.

## Run tests

From `video_analyzer/` with Python 3.11+:

```sh
python -m unittest -v test_strategic_store test_strategic_backup
```

Block 03: 31 tests passed locally on Linux / Python 3.13.5 (21 existing + 10 new).
The complete repository suite, Windows, and real-session integration are not verified.

## Local database lifecycle

```python
from contextlib import closing
import strategic_store as store
import strategic_backup as snapshots

with closing(store.connect('strategy.sqlite')) as db:
    print(store.lookup(db, 5, {'position': 'BTN'}))  # [] until real data is enabled

report = snapshots.backup('strategy.sqlite', 'strategy-backup.sqlite')
print(report)  # save the SHA-256 independently in a trusted location
snapshots.restore('strategy-backup.sqlite', 'strategy-restored.sqlite',
                  expected_sha256=report['sha256'])
```

- Backups use SQLite's backup API, including committed WAL data. The result is a
  standalone database in DELETE journal mode. Uncommitted writes are excluded.
- Both operations validate the staged copy before publishing it to a new path.
  Existing files, including the source itself, are never overwritten. The target
  directory must already exist and support hard links; unsupported filesystems
  fail rather than fall back to an unsafe overwrite. Windows has not been tested.
- Restore requires the original snapshot hash, a trusted standalone input with
  no WAL/journal sidecars, and no concurrent modifications to that input.
  Compare hashes from an independent trusted record; a hash is not a signature.
- `audit(db)` checks the exact current schema, SQLite integrity and foreign keys,
  canonical source/scenario identities, strategy payloads and record hashes.
  Use it on a committed, stable v3 database. It is not a poker scenario validator,
  license authenticator or tamper-proof audit of human permission reviews.
- Backups preserve source permission history, not just the current status.
  Keep copies private. Restore to a new path, inspect it, then explicitly select
  it as the working database. Do not replace a live database or its sidecars.
- v2 migrates to v3 on `store.connect`. v1/unknown versions are rejected, not
  silently upgraded. The backup helper currently accepts only the v3 schema.
  Back up any older database separately before migration.

## Pending

Import adapters, full scenario normalization, authorized production data,
coverage reports and integration with reconstructed hands. No real strategies
were imported or released in blocks 01–03. Permission reviews are human metadata,
not evidence that any third-party dataset has been licensed.
