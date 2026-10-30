"""Portable, verified offline PLO5/PLO6 batch-session ZIP (no original video).

Usage:
    python offline_session_portable_bundle.py export SESSION_ROOT NEW_ZIP
    python offline_session_portable_bundle.py verify SESSION_ZIP
    python offline_session_portable_bundle.py open SESSION_ZIP NEW_DIRECTORY

SESSION_ROOT contains plan.json, annotations.json, batches/, workspace/results/,
workspace/batch_timeline.html and optional workspace/clips/. The original session
video is deliberately omitted. Only human-reviewed, offline, conditional math.

Verification replays the existing source-plan, batch, Monte Carlo result and clip
validators from an isolated extraction, WITHOUT rerunning Monte Carlo. SHA-256
establishes internal consistency, not video authenticity or poker correctness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

import offline_session_batch_timeline as timeline

MANIFEST = 'portable_manifest.json'
MAX_FILES = 12_000
MAX_FILE_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
BLOCK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name, directory=False):
    require(type(name) is str and name and '\\' not in name and '\x00' not in name and
            not name.startswith('/') and not name.startswith('~') and
            not name.startswith('\\') and not name.startswith('//'), 'unsafe archive name')
    base = name[:-1] if directory else name
    parts = base.split('/')
    require(all(p not in ('', '.', '..') and ':' not in p for p in parts) and
            str(PurePosixPath(base)) == base, 'unsafe archive path')
    require((name.endswith('/') if directory else not name.endswith('/')),
            'invalid archive entry kind')
    return base


def read_json(path):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_MANIFEST_BYTES,
            'invalid JSON input')
    return json.loads(path.read_text(encoding='utf-8'))


def expected_paths(root):
    """Derive exact allowlist from previously deep-verified session manifests."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'invalid session directory')
    for name in ('plan.json', 'annotations.json'):
        require((root/name).is_file() and not (root/name).is_symlink(), 'missing source file')
    timeline.process(root/'plan.json', root/'annotations.json', root/'batches',
                     root/'workspace', verify=True)
    state = read_json(root/'workspace/results/session_history.json')
    batches = read_json(root/'batches/manifest.json')
    files = {'plan.json', 'annotations.json', 'batches/manifest.json',
             'workspace/results/session_history.json', 'workspace/batch_timeline.html'}
    for row in batches['batches']:
        name = row['directory']
        require(type(name) is str and name.startswith('batch-') and
                name[6:].isdigit() and len(name) == 10, 'invalid batch directory')
        for leaf in ('plan.json', 'annotations.json', 'queue.json'):
            files.add(f'batches/{name}/{leaf}')
    for row in state['batches']:
        name = row['directory']
        files.add(f'workspace/results/{name}/manifest.json')
        result = read_json(root/f'workspace/results/{name}/manifest.json')
        for hand in result['hands']:
            if hand['status'] == 'offline_conditional_equity_computed':
                path = hand['result_file']
                require(type(path) is str and path.startswith('hands/') and
                        path.endswith('.json') and len(path.split('/')) == 2,
                        'invalid math result file')
                files.add(f'workspace/results/{name}/{path}')
    clips_root = root/'workspace/clips'
    if clips_root.exists() or clips_root.is_symlink():
        require(clips_root.is_dir() and not clips_root.is_symlink(), 'invalid clips directory')
        for folder in clips_root.iterdir():
            require(folder.is_dir() and not folder.is_symlink() and
                    folder.name in {x['directory'] for x in state['batches']},
                    'unexpected clip batch')
            base = f'workspace/clips/{folder.name}'
            files.add(base+'/manifest.json')
            clips = read_json(folder/'manifest.json')['clips']
            for clip in clips:
                files.add(base+'/'+clip['file'])
                files.add(base+'/'+clip['sidecar'])
    require(len(files) <= MAX_FILES, 'too many session files')
    for f in files:
        safe_name(f)
    return files, state


def inventory(root):
    files, state = expected_paths(root)
    root = Path(root)
    observed_files, dirs = set(), set()
    for current, subdirs, filenames in os.walk(root, topdown=True, followlinks=False):
        rel = Path(current).relative_to(root)
        if rel.parts:
            dirs.add(rel.as_posix()+'/')
        for name in subdirs:
            p = Path(current)/name
            require(p.is_dir() and not p.is_symlink(), 'linked or invalid directory')
        for name in filenames:
            p = Path(current)/name
            require(p.is_file() and not p.is_symlink(), 'linked or invalid file')
            observed_files.add(p.relative_to(root).as_posix())
    require(observed_files == files, 'unexpected or missing session file')
    allowed_dirs = {f'workspace/results/{row["directory"]}/hands/'
                    for row in state['batches']}
    if (root/'workspace/clips').is_dir():
        allowed_dirs.add('workspace/clips/')
    for f in files:
        parts = f.split('/')
        allowed_dirs.update('/'.join(parts[:n])+'/' for n in range(1, len(parts)))
    require(dirs <= allowed_dirs, 'unexpected session directory')
    require(len(dirs) + len(files) <= MAX_FILES, 'too many archive members')
    return sorted(files), sorted(dirs), state


def stream_copy(source, dest, limit):
    h, size = hashlib.sha256(), 0
    while True:
        chunk = source.read(BLOCK)
        if not chunk:
            break
        size += len(chunk)
        require(size <= limit, 'file exceeds size limit')
        h.update(chunk)
        dest.write(chunk)
    return size, h.hexdigest()


def export(root, destination):
    root, destination = Path(root), Path(destination)
    require(destination.suffix.lower() == '.zip' and
            destination.parent.is_dir() and not destination.parent.is_symlink() and
            not destination.exists() and not destination.is_symlink() and
            root.resolve() not in destination.resolve().parents,
            'destination must be a new ZIP outside the session')
    files, dirs, state = inventory(root)
    total = 0
    meta = {}
    for name in files:
        path = root/name
        size = path.stat().st_size
        require(size <= MAX_FILE_BYTES, 'file too large')
        total += size
        require(total <= MAX_TOTAL_BYTES, 'session exceeds archive size limit')
        with path.open('rb') as stream:
            size2, sha = stream_copy(stream, _NullWriter(), MAX_FILE_BYTES)
        require(size2 == size, 'input changed during scan')
        meta[name] = {'size_bytes': size, 'sha256': sha}
    manifest = {'schema_version': 1,
                'status': 'portable_offline_human_reviewed_batch_session',
                'source_video_included': False,
                'ocr_verified': False, 'actions_observed_or_graded': False,
                'ranges_are_hypotheses': True,
                'confidence_intervals_are_sampling_only': True,
                'source_video_sha256_claim': state['source_video_sha256_claim'],
                'hands': state['total_hands_reviewed'],
                'completed_batches': state['completed_batches'],
                'total_batches': state['total_batches'],
                'complete': state['complete'],
                'files': meta, 'directories': dirs}
    raw_manifest = canonical(manifest)
    require(len(raw_manifest) <= MAX_MANIFEST_BYTES, 'manifest exceeds size limit')
    try:
        with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            for name in dirs:
                archive.writestr(name, b'')
            for name in files:
                with (root/name).open('rb') as source, archive.open(name, 'w', force_zip64=True) as target:
                    size, sha = stream_copy(source, target, MAX_FILE_BYTES)
                require(meta[name] == {'size_bytes': size, 'sha256': sha},
                        'source changed during ZIP creation')
            archive.writestr(MANIFEST, raw_manifest)
        # Reject edits between initial verification and publication.
        require(inventory(root)[0:2] == (files, dirs), 'source structure changed')
        timeline.process(root/'plan.json', root/'annotations.json', root/'batches',
                         root/'workspace', verify=True)
        verify(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return manifest


class _NullWriter:
    def write(self, chunk):
        pass


def _inspect(archive):
    infos = archive.infolist()
    require(len(infos) <= MAX_FILES+1, 'too many archive members')
    names = [i.filename for i in infos]
    require(len(names) == len(set(names)) and MANIFEST in names,
            'duplicate or missing archive member')
    for info in infos:
        safe_name(info.filename, directory=info.is_dir())
        mode = info.external_attr >> 16
        require(not stat.S_ISLNK(mode) and not (info.flag_bits & 1) and
                info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                'unsupported or unsafe archive entry')
        require(info.file_size <= MAX_FILE_BYTES and
                (info.is_dir() is False or info.file_size == 0),
                'invalid member size')
    require(sum(i.file_size for i in infos) <= MAX_TOTAL_BYTES+MAX_MANIFEST_BYTES,
            'archive exceeds size limit')
    info = archive.getinfo(MANIFEST)
    require(not info.is_dir() and info.file_size <= MAX_MANIFEST_BYTES,
            'invalid portable manifest')
    manifest_raw = archive.read(MANIFEST)
    manifest = json.loads(manifest_raw)
    require(type(manifest) is dict and manifest_raw == canonical(manifest) and
            manifest.get('schema_version') == 1 and
            manifest.get('status') == 'portable_offline_human_reviewed_batch_session' and
            manifest.get('source_video_included') is False and
            manifest.get('ocr_verified') is False and
            manifest.get('actions_observed_or_graded') is False and
            manifest.get('ranges_are_hypotheses') is True and
            manifest.get('confidence_intervals_are_sampling_only') is True,
            'invalid portable provenance')
    files, dirs = manifest.get('files'), manifest.get('directories')
    require(type(files) is dict and type(dirs) is list and
            len(dirs) == len(set(dirs)) and all(type(d) is str for d in dirs) and
            set(names) == set(files) | set(dirs) | {MANIFEST} and
            all(type(v) is dict and set(v) == {'sha256', 'size_bytes'} and
                type(v['size_bytes']) is int and 0 <= v['size_bytes'] <= MAX_FILE_BYTES and
                type(v['sha256']) is str and len(v['sha256']) == 64 and
                all(c in '0123456789abcdef' for c in v['sha256']) for v in files.values()),
            'invalid archive inventory')
    require(all(not archive.getinfo(name).is_dir() for name in files) and
            all(archive.getinfo(name).is_dir() for name in dirs),
            'incorrect archive entry types')
    return manifest


def _replay(root, manifest):
    files, dirs, state = inventory(root)
    require(files == sorted(manifest['files']) and dirs == sorted(manifest['directories']),
            'extracted inventory differs')
    require(state['source_video_sha256_claim'] == manifest['source_video_sha256_claim'] and
            state['total_hands_reviewed'] == manifest['hands'] and
            state['completed_batches'] == manifest['completed_batches'] and
            state['total_batches'] == manifest['total_batches'] and
            state['complete'] == manifest['complete'], 'portable history differs')


def _unpack(archive, destination, manifest):
    destination.mkdir()
    for name in manifest['directories']:
        (destination/safe_name(name, directory=True)).mkdir(parents=True, exist_ok=True)
    for name, expected in manifest['files'].items():
        path = destination/safe_name(name)
        require(path.parent.is_dir() and not path.is_symlink() and not path.exists(),
                'invalid extraction destination')
        with archive.open(name) as src, path.open('xb') as dst:
            size, sha = stream_copy(src, dst, MAX_FILE_BYTES)
        require(expected == {'size_bytes': size, 'sha256': sha},
                'archive content hash mismatch: ' + name)
    _replay(destination, manifest)


def verify(source):
    source = Path(source)
    require(source.is_file() and not source.is_symlink(), 'invalid source ZIP')
    with zipfile.ZipFile(source, 'r') as archive:
        manifest = _inspect(archive)
        with tempfile.TemporaryDirectory(prefix='plo-portable-verify-') as temporary:
            root = Path(temporary)/'session'
            _unpack(archive, root, manifest)
    return manifest


def open_bundle(source, destination):
    source, destination = Path(source), Path(destination)
    require(destination.parent.is_dir() and not destination.parent.is_symlink() and
            not destination.exists() and not destination.is_symlink() and
            source.resolve() != destination.resolve(),
            'output must be a new directory')
    with zipfile.ZipFile(source, 'r') as archive:
        manifest = _inspect(archive)
        stage = Path(tempfile.mkdtemp(prefix='.plo-portable-open-', dir=destination.parent))
        try:
            # Stage itself exists: extract into a child and atomically publish that child.
            session = stage/'session'
            _unpack(archive, session, manifest)
            require(not destination.exists() and not destination.is_symlink(),
                    'output appeared during extraction')
            os.rename(session, destination)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('export'); a.add_argument('session_root'); a.add_argument('new_zip')
    a = sub.add_parser('verify'); a.add_argument('zip_file')
    a = sub.add_parser('open'); a.add_argument('zip_file'); a.add_argument('new_directory')
    args = parser.parse_args(argv)
    if args.command == 'export':
        result = export(args.session_root, args.new_zip)
    elif args.command == 'verify':
        result = verify(args.zip_file)
    else:
        result = open_bundle(args.zip_file, args.new_directory)
    print(json.dumps({k: result[k] for k in ('hands', 'completed_batches', 'total_batches', 'complete')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
