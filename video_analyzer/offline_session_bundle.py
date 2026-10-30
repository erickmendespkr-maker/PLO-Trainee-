"""Export/verify an offline, human-reviewed PLO clip session as a portable ZIP.

Only clips already accepted by offline_reviewed_clip_gallery are included. The
original recording is NOT copied. No OCR, Monte Carlo or action grading occurs.

Usage:
  python offline_session_bundle.py export CLIP_DIR NEW_BUNDLE.zip [ATTACHMENTS.json]
  python offline_session_bundle.py verify BUNDLE.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
import zipfile

import offline_reviewed_clip_gallery as gallery

MAX_FILE_BYTES = 1024 * 1024 * 1024  # 1 GiB per reviewed clip
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024  # 4 GiB uncompressed per bundle
MAX_FILES = 406
MANIFEST_NAME = 'session_bundle_manifest.json'
INDEX_NAME = 'index.html'


def canonical_json(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + '\n').encode('utf-8')


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    return gallery.sha(path)


def entries_for_session(root, attachments=None):
    root = Path(root)
    snapshot = gallery.build(root, attachments)
    names = {'manifest.json'}
    if attachments is not None:
        gallery.local_file(root, attachments, '.json', 2_000_000)
        names.add(attachments)
    for clip in snapshot['clips']:
        names.update((clip['video'], clip['sidecar']))
        if clip['analysis'] is not None:
            names.update((clip['analysis']['acknowledged_report'],
                          clip['analysis']['sensitivity']))
    files = {}
    total = 0
    for name in sorted(names):
        path = gallery.local_file(root, name)
        size = path.stat().st_size
        gallery.require(size <= MAX_FILE_BYTES, f'oversized input: {name}')
        total += size
        gallery.require(total <= MAX_TOTAL_BYTES, 'session exceeds byte limit')
        files[name] = {'sha256': hash_file(path), 'size_bytes': size}
    index = gallery.render(snapshot).encode('utf-8')
    gallery.require(len(index) <= 4_000_000, 'generated HTML too large')
    files[INDEX_NAME] = {'sha256': hash_bytes(index), 'size_bytes': len(index)}
    gallery.require(len(files) <= MAX_FILES, 'too many files')
    manifest = {
        'schema_version': 1,
        'status': 'offline_human_reviewed_session_not_verified_hands',
        'source_video_included': False,
        'attachments_index': attachments,
        'source_video_sha256_claim': snapshot['source_video_sha256_claim'],
        'source_manifest_sha256': snapshot['source_manifest_sha256'],
        'action_graded': False,
        'visual_card_recognition_verified': False,
        'range_or_fold_probability_observed': False,
        'clips': [{
            'hand_id': x['hand_id'], 'table_id': x['table_id'],
            'start_seconds': x['start_seconds'], 'end_seconds': x['end_seconds'],
            'clip_sha256': x['clip_sha256'],
            'has_conditional_analysis': x['analysis'] is not None,
        } for x in snapshot['clips']],
        'files': files,
    }
    return manifest, index


def export(root, destination, attachments=None):
    root, destination = Path(root), Path(destination)
    gallery.require(root.is_dir() and not root.is_symlink(), 'invalid clip directory')
    gallery.require(destination.suffix.lower() == '.zip' and not destination.exists()
                    and not destination.is_symlink() and
                    destination.parent.is_dir() and
                    destination.parent.resolve() != root.resolve() and
                    root.resolve() not in destination.resolve().parents,
                    'bundle must be a new ZIP outside the clip directory')
    manifest, index = entries_for_session(root, attachments)
    payload = canonical_json(manifest)
    try:
        with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            for name, expected in sorted(manifest['files'].items()):
                if name == INDEX_NAME:
                    archive.writestr(name, index)
                    continue
                path = gallery.local_file(root, name)
                # Read and hash during the actual archive write to reject concurrent edits.
                with path.open('rb') as src, archive.open(name, 'w', force_zip64=True) as out:
                    digest = hashlib.sha256()
                    size = 0
                    while chunk := src.read(1024 * 1024):
                        size += len(chunk)
                        gallery.require(size <= expected['size_bytes'], 'input changed during export')
                        digest.update(chunk)
                        out.write(chunk)
                    gallery.require(size == expected['size_bytes'] and
                                    digest.hexdigest() == expected['sha256'],
                                    'input changed during export')
            archive.writestr(MANIFEST_NAME, payload)
        verify(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return manifest


def verify(archive_path):
    archive_path = Path(archive_path)
    gallery.require(archive_path.is_file() and not archive_path.is_symlink(), 'invalid bundle')
    with zipfile.ZipFile(archive_path, 'r') as archive:
        infos = archive.infolist()
        names = [x.filename for x in infos]
        gallery.require(len(names) == len(set(names)) and len(names) <= MAX_FILES + 1,
                        'duplicate or excessive archive entries')
        gallery.require(MANIFEST_NAME in names and INDEX_NAME in names, 'missing bundle files')
        for info in infos:
            gallery.require(info.filename == Path(info.filename).name and
                            '/' not in info.filename and '\\' not in info.filename and
                            info.filename not in ('.', '..') and
                            not info.is_dir() and info.file_size <= MAX_FILE_BYTES,
                            'unsafe archive member')
        gallery.require(sum(i.file_size for i in infos) <= MAX_TOTAL_BYTES,
                        'archive exceeds uncompressed limit')
        manifest_info = archive.getinfo(MANIFEST_NAME)
        gallery.require(manifest_info.file_size <= 2_000_000, 'manifest too large')
        manifest = json.loads(archive.read(MANIFEST_NAME))
        gallery.require(type(manifest) is dict and manifest.get('schema_version') == 1 and
                        manifest.get('status') ==
                        'offline_human_reviewed_session_not_verified_hands' and
                        manifest.get('source_video_included') is False and
                        manifest.get('action_graded') is False and
                        manifest.get('visual_card_recognition_verified') is False and
                        manifest.get('range_or_fold_probability_observed') is False,
                        'unsupported session claims')
        files = manifest.get('files')
        gallery.require(type(files) is dict and set(files) == set(names) - {MANIFEST_NAME},
                        'file inventory mismatch')
        for name, info in files.items():
            gallery.require(type(info) is dict and set(info) == {'sha256', 'size_bytes'} and
                            type(info['sha256']) is str and gallery.SHA.fullmatch(info['sha256'])
                            and type(info['size_bytes']) is int and
                            info['size_bytes'] == archive.getinfo(name).file_size,
                            'invalid inventory entry')
            digest = hashlib.sha256()
            with archive.open(name) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            gallery.require(digest.hexdigest() == info['sha256'], 'archive content mismatch')
        gallery.require(manifest.get('source_manifest_sha256') == files['manifest.json']['sha256'],
                        'source manifest mismatch')
        attachments = manifest.get('attachments_index')
        gallery.require(attachments is None or (type(attachments) is str and
                        attachments in files and attachments.endswith('.json') and
                        attachments not in ('manifest.json',)), 'invalid attachments index')
        gallery.require(type(manifest.get('clips')) is list and
                        1 <= len(manifest['clips']) <= 100, 'invalid clip inventory')
        gallery.require(type(manifest.get('source_video_sha256_claim')) is str and
                        gallery.SHA.fullmatch(manifest['source_video_sha256_claim']),
                        'invalid video source claim')
        # Deep semantic replay: hash-valid files alone cannot establish that the
        # clip/analysis provenance and human-review flags are mutually consistent.
        with tempfile.TemporaryDirectory(prefix='plo_bundle_verify_') as tmp:
            root = Path(tmp)
            for name in files:
                with archive.open(name) as src, (root / name).open('wb') as dst:
                    while chunk := src.read(1024 * 1024):
                        dst.write(chunk)
            snapshot = gallery.build(root, attachments)
            gallery.require(snapshot['source_manifest_sha256'] ==
                            manifest['source_manifest_sha256'] and
                            snapshot['source_video_sha256_claim'] ==
                            manifest['source_video_sha256_claim'],
                            'source provenance mismatch')
            observed = [{
                'hand_id': x['hand_id'], 'table_id': x['table_id'],
                'start_seconds': x['start_seconds'], 'end_seconds': x['end_seconds'],
                'clip_sha256': x['clip_sha256'],
                'has_conditional_analysis': x['analysis'] is not None,
            } for x in snapshot['clips']]
            gallery.require(manifest['clips'] == observed, 'clip inventory mismatch')
            gallery.require((root / INDEX_NAME).read_bytes() ==
                            gallery.render(snapshot).encode('utf-8'),
                            'HTML does not match verified review data')
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    exp = sub.add_parser('export')
    exp.add_argument('clip_dir'); exp.add_argument('new_bundle_zip')
    exp.add_argument('attachments_json', nargs='?')
    check = sub.add_parser('verify'); check.add_argument('bundle_zip')
    args = p.parse_args(argv)
    if args.command == 'export':
        result = export(args.clip_dir, args.new_bundle_zip, args.attachments_json)
    else:
        result = verify(args.bundle_zip)
    print(json.dumps({'status': result['status'], 'clips': len(result['clips']),
                      'files': len(result['files']), 'verified_archive': True,
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
