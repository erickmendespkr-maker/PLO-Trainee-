"""Offline batch destination collision audit; no files are written."""
from pathlib import Path


def audit_destinations(plan, output_root):
    """Reject aliases, symlinks and unsafe output paths before FFmpeg is invoked.

    This is a preflight check, not an atomic reservation. Export must use
    exclusive creation or a private job directory to avoid TOCTOU races.
    """
    root = Path(output_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('output_root must be a directory')
    if not isinstance(plan, list):
        raise ValueError('plan must be a list')
    seen = set()
    audited = []
    for item in plan:
        if not isinstance(item, dict) or item.get('status') != 'PLANNED_ONLY':
            raise ValueError('expected provisional plan')
        raw = item.get('destination')
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('invalid destination')
        target = Path(raw)
        if target.suffix.lower() != '.mp4':
            raise ValueError('destination must be MP4')
        if target.is_symlink() or target.with_suffix('.json').is_symlink():
            raise ValueError('symlink destination rejected')
        canonical = target.resolve(strict=False)
        if not canonical.is_relative_to(root) or canonical == root:
            raise ValueError('destination escapes output root')
        if not canonical.parent.is_dir():
            raise ValueError('destination parent must exist')
        manifest = canonical.with_suffix('.json')
        if canonical in seen or manifest in seen:
            raise ValueError('duplicate canonical destination')
        if canonical.exists() or manifest.exists():
            raise FileExistsError(str(canonical))
        seen.update((canonical, manifest))
        audited.append({'destination': str(canonical), 'manifest': str(manifest),
                        'status': 'DESTINATION_AUDITED_NOT_RESERVED'})
    return audited
