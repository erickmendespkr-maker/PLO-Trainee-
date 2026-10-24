"""Create an offline, manually played MP4 review package from validated triage.

Requires the exact original clip bytes named in each triage row. Rechecks
SHA-256 while copying, probes video with ffprobe, and writes a self-contained
HTML page plus a local clips/ directory. This is NOT evidence authentication,
OCR validation, automatic clip selection, or a poker decision assistant.

Example:
  python activity_triage_clip_browser.py triage.json exported_clips/ output_package/

All input is local. No web services, network requests, or paid dependencies.
"""
import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path
import subprocess
import tempfile

from activity_triage_dashboard import build_triage_dashboard, validate_triage

MAX_CLIPS = 1000
MAX_CLIP_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024 * 1024
MAX_TRIAGE_BYTES = 8 * 1024 * 1024


def _probe_video(path):
    """Validate that a copied file contains a decodable video stream header."""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_type,width,height:format=duration,format_name',
             '-of', 'json', str(path)], capture_output=True, text=True,
            timeout=20, check=True)
        payload = json.loads(result.stdout)
        stream = payload['streams'][0]
        container = payload['format']
        duration = float(container['duration'])
        if (stream.get('codec_type') != 'video' or
                type(stream.get('width')) is not int or stream['width'] < 1 or
                type(stream.get('height')) is not int or stream['height'] < 1 or
                not math.isfinite(duration) or not 0 < duration <= 3600 or
                'mp4' not in container.get('format_name', '')):
            raise ValueError('Invalid MP4 video metadata')
        return {'duration_seconds': duration,
                'width': stream['width'], 'height': stream['height']}
    except (OSError, subprocess.SubprocessError, KeyError, IndexError,
            TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid or unreadable MP4 video: ' + path.name) from exc


def _copy_and_verify(source, target, expected_sha):
    if not source.is_file() or source.is_symlink():
        raise ValueError('Missing, non-regular or linked MP4: ' + source.name)
    size = source.stat().st_size
    if not 0 < size <= MAX_CLIP_BYTES:
        raise ValueError('MP4 size outside safety limit: ' + source.name)
    sha = hashlib.sha256()
    copied = 0
    with source.open('rb') as src, target.open('xb') as dst:
        while chunk := src.read(1024 * 1024):
            copied += len(chunk)
            if copied > MAX_CLIP_BYTES:
                raise ValueError('MP4 exceeded size limit while copying: ' + source.name)
            sha.update(chunk)
            dst.write(chunk)
    if copied != size:
        raise ValueError('MP4 changed size while copying: ' + source.name)
    if sha.hexdigest() != expected_sha:
        raise ValueError('MP4 SHA-256 mismatch: ' + source.name)
    return size


def _embed_manual_players(html, triage, verified_filenames):
    """Extend the validated dashboard without changing its notes or script hash."""
    rows = triage['candidates']
    if set(verified_filenames) != {row['filename'] for row in rows}:
        raise ValueError('Verified MP4 list does not match triage')
    parts = html.split('</article>')
    if len(parts) != len(rows) + 1:
        raise ValueError('Unexpected dashboard HTML structure')
    if not rows:
        return html
    old = 'media-src &#x27;none&#x27;'
    if html.count(old) != 1:
        raise ValueError('Unexpected dashboard media policy')
    output = []
    for row, part in zip(rows, parts):
        player = ('<details><summary>Reproduzir MP4 local (abrir manualmente)</summary>'
                  '<p class="meta">SHA-256 conferido na criacao do pacote; '
                  'o navegador nao verifica alteracoes posteriores.</p>'
                  '<video controls preload="none" playsinline src="./clips/' +
                  escape(row['filename'], quote=True) +
                  '" aria-label="Clipe da mesa ' + str(row['table_id']) +
                  '">Seu navegador nao reproduz MP4.</video></details>')
        output.append(part + player + '</article>')
    output.append(parts[-1])
    return ''.join(output).replace(old, 'media-src &#x27;self&#x27;', 1)


def build_clip_browser_package(triage, clips_dir, output_dir, *, expected_sha256=None):
    """Atomically create output_dir/index.html, clips/ and manifest.json.

    Never overwrites existing destinations. Staging is removed on failure.
    An MP4's hash is verified at *packaging time*, not continuously thereafter.
    """
    triage_sha = validate_triage(triage, expected_sha256=expected_sha256)
    clips_dir, output_dir = Path(clips_dir), Path(output_dir)
    if not clips_dir.is_dir() or clips_dir.is_symlink():
        raise ValueError('Require regular source clip directory')
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError('Output package must not exist')
    if clips_dir.resolve() == output_dir.resolve() or clips_dir.resolve() in output_dir.resolve().parents:
        raise ValueError('Output cannot be inside the clip source directory')
    expected = {}
    for row in triage['candidates']:
        filename, sha = row['filename'], row['original_mp4_sha256']
        if filename in expected and expected[filename] != sha:
            raise ValueError('Conflicting SHA-256 for the same MP4 filename')
        expected[filename] = sha
    if len(expected) > MAX_CLIPS:
        raise ValueError('Too many MP4 clips to package')
    total = 0
    for name in expected:
        source = clips_dir / name
        if not source.is_file() or source.is_symlink():
            raise ValueError('Missing, non-regular or linked MP4: ' + name)
        size = source.stat().st_size
        if not 0 < size <= MAX_CLIP_BYTES:
            raise ValueError('MP4 size outside safety limit: ' + name)
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError('Clip package exceeds total size limit')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError('Output package must not exist')
    with tempfile.TemporaryDirectory(prefix='.plo-clip-browser-', dir=output_dir.parent) as td:
        stage = Path(td) / 'package'
        stage.mkdir()
        (stage / 'clips').mkdir()
        metadata = []
        for name in sorted(expected):
            dest = stage / 'clips' / name
            size = _copy_and_verify(clips_dir / name, dest, expected[name])
            video = _probe_video(dest)
            metadata.append({'filename': name, 'sha256': expected[name],
                             'size_bytes': size, **video})
        rendered = build_triage_dashboard(triage, expected_sha256=triage_sha)
        html_bytes = _embed_manual_players(rendered['html'], triage, expected).encode('utf-8')
        (stage / 'index.html').write_bytes(html_bytes)
        manifest = {
            'schema_version': 1,
            'status': 'offline_manual_review_clips_verified_at_packaging_time',
            'source_triage_sha256': triage_sha,
            'recording_sha256_from_triage_unverified': triage['recording_sha256'],
            'html_sha256': hashlib.sha256(html_bytes).hexdigest(),
            'total_decisions': rendered['total'],
            'clips_copied': len(metadata),
            'clips': metadata,
            'visual_evidence_verified': False,
            'strategic_error_established': False,
            'auto_clip_selection_authorized': False,
            'ev_ranking_authorized': False,
            'warning': 'MP4 hashes checked during packaging only; playback does not validate '
                       'video-derived poker facts, opponent ranges, or real-hand EV.',
        }
        (stage / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        # Atomic within a filesystem, without changing or deleting input clips.
        stage.rename(output_dir)
    return manifest


def write_clip_browser_package(triage_json, clips_dir, output_dir, *, expected_sha256=None):
    source = Path(triage_json)
    if (not source.is_file() or source.is_symlink() or
            source.stat().st_size > MAX_TRIAGE_BYTES):
        raise ValueError('Require regular triage JSON within size limit')
    triage = json.loads(source.read_text(encoding='utf-8'))
    return build_clip_browser_package(triage, clips_dir, output_dir,
                                      expected_sha256=expected_sha256)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('triage_json')
    parser.add_argument('clips_dir')
    parser.add_argument('output_dir')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args(argv)
    manifest = write_clip_browser_package(args.triage_json, args.clips_dir,
                                          args.output_dir, expected_sha256=args.expected_sha256)
    print(json.dumps({'decisions': manifest['total_decisions'],
                      'verified_mp4': manifest['clips_copied'],
                      'auto_selection_authorized': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
