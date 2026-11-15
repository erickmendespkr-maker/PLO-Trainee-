"""No-clobber publishing of staged MP4 and JSON files on the same filesystem.

Hard-link staging files into final names using O_EXCL-like link semantics.
If the second publication fails, remove the first only if it still refers
to our inode. This is not a multi-file atomic transaction: readers must
consider a pair complete only after both files exist and hashes validate.
"""
import os
from pathlib import Path


def _same_inode(a, b):
    try:
        x, y = a.stat(), b.stat()
        return (x.st_dev, x.st_ino) == (y.st_dev, y.st_ino)
    except FileNotFoundError:
        return False


def publish_pair_no_clobber(staged_video, staged_json, final_video, final_json):
    """Publish existing staged files without overwriting unrelated files.

    Requires staged and final paths on a filesystem supporting hard links.
    The caller is responsible for source staging and integrity validation.
    """
    sources = (Path(staged_video), Path(staged_json))
    targets = (Path(final_video), Path(final_json))
    if len({str(p.resolve(strict=False)) for p in (*sources, *targets)}) != 4:
        raise ValueError('staged and final paths must be distinct')
    if any(not p.is_file() or p.is_symlink() or p.stat().st_size == 0 for p in sources):
        raise ValueError('staged files must be nonempty regular files')
    if any(p.parent.resolve() != targets[0].parent.resolve() for p in targets):
        raise ValueError('final files must share a directory')
    if any(p.exists() or p.is_symlink() for p in targets):
        raise FileExistsError('final artifact already exists')
    linked = []
    try:
        for src, dst in zip(sources, targets):
            os.link(src, dst, follow_symlinks=False)
            linked.append((src, dst))
    except BaseException:
        for src, dst in reversed(linked):
            if _same_inode(src, dst):
                dst.unlink()
        raise
    return tuple(str(p) for p in targets)
