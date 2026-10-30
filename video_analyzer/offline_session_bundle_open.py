"""Safely unpack a verified offline PLO review bundle into a NEW directory.

This is a read-only *viewer handoff*: it never recognizes cards, grades actions,
opens a poker client, or contacts a server. The HTML gallery is opened manually.

Usage:
    python offline_session_bundle_open.py BUNDLE.zip NEW_DIRECTORY

The archive is copied to a private staging directory before verification so
changes to the source during extraction cannot silently alter the checked data.
All members are verified by offline_session_bundle.verify(), then extracted as
ordinary regular files using an explicit inventory (never extractall()).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

import offline_session_bundle as bundle
import offline_reviewed_clip_gallery as gallery


def _copy_limited(src, dst, limit):
    size = 0
    digest = hashlib.sha256()
    while chunk := src.read(1024 * 1024):
        size += len(chunk)
        gallery.require(size <= limit, 'bundle exceeds byte limit')
        digest.update(chunk)
        dst.write(chunk)
    return size, digest.hexdigest()


def unpack(source, destination):
    source, destination = Path(source), Path(destination)
    gallery.require(source.is_file() and not source.is_symlink() and
                    source.suffix.lower() == '.zip', 'source must be a regular ZIP')
    gallery.require(destination.name not in ('', '.', '..') and
                    destination.parent.is_dir() and
                    not destination.parent.is_symlink() and
                    not destination.exists() and not destination.is_symlink(),
                    'destination must be a new directory')
    # Copying to a private directory also prevents source mutation between
    # verification and extraction, without trusting the original archive path.
    with tempfile.TemporaryDirectory(prefix='.plo_open_', dir=destination.parent) as temp:
        stage = Path(temp)
        frozen = stage / 'verified_input.zip'
        with source.open('rb') as stream, frozen.open('xb') as target:
            _copy_limited(stream, target, bundle.MAX_TOTAL_BYTES)
        manifest = bundle.verify(frozen)  # full semantic and hash replay
        extracted = stage / 'contents'
        extracted.mkdir()
        with zipfile.ZipFile(frozen) as archive:
            for name, expected in sorted(manifest['files'].items()):
                # verify() already checked flat paths; assert again at use site.
                gallery.require(name == Path(name).name and name not in ('.', '..') and
                                '/' not in name and '\\' not in name,
                                'unsafe member during extraction')
                with archive.open(name) as inp, (extracted / name).open('xb') as out:
                    size, digest = _copy_limited(inp, out, expected['size_bytes'])
                gallery.require(size == expected['size_bytes'] and
                                digest == expected['sha256'],
                                'extracted content differs from verified inventory')
        # Preserve the bundle manifest alongside the files for offline inspection.
        with (extracted / bundle.MANIFEST_NAME).open('xb') as out:
            out.write(bundle.canonical_json(manifest))
        gallery.require((extracted / 'index.html').is_file(), 'missing gallery')
        # No overwriting existing directory; fail if another process created it.
        gallery.require(not destination.exists() and not destination.is_symlink(),
                        'destination already exists')
        os.rename(extracted, destination)
    return {
        'status': manifest['status'],
        'gallery': str(destination / 'index.html'),
        'clips': len(manifest['clips']),
        'conditional_analyses': sum(x['has_conditional_analysis'] for x in manifest['clips']),
        'source_video_included': False,
        'action_graded': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle_zip')
    parser.add_argument('new_directory')
    args = parser.parse_args(argv)
    print(json.dumps(unpack(args.bundle_zip, args.new_directory), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
