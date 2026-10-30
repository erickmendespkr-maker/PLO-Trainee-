"""Build a local, static entry page for a verified offline PLO review session.

Usage (run from video_analyzer/):
    python offline_session_workspace.py open BUNDLE.zip NEW_WORKSPACE
    python offline_session_workspace.py verify EXISTING_WORKSPACE

The source video is never copied. The ZIP is verified before extraction, and
neither this module nor its HTML contacts a server, recognizes cards, or grades
poker decisions. Review HTML is copied from this module's directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import offline_session_bundle as bundle
import offline_session_bundle_open as opener
import offline_reviewed_clip_gallery as gallery

WORKSPACE_MANIFEST = 'workspace_manifest.json'
REVIEW_UI = 'offline_visual_review_ui.html'
LANDING = 'index.html'
SESSION = 'session'
STATUS = 'offline_review_workspace_not_verified_hands'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def landing_html():
    # Fixed HTML: no source-controlled names, annotations or ZIP content interpolated.
    return '''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>PLO Trainee · Sessão offline</title>
<style>
:root{font-family:system-ui,sans-serif;color-scheme:dark;background:#0e1522;color:#eef3fa}
body{max-width:780px;margin:5vh auto;padding:20px}h1{font-size:1.8rem}
section{border:1px solid #44566e;background:#172236;border-radius:12px;padding:20px;margin:16px 0}
a{color:#a9d5ff;font-weight:650}p{line-height:1.55;color:#c5d2e3}
small{color:#d8c5a6}
</style></head><body><h1>PLO Trainee · Sessão offline</h1>
<p>Arquivos locais de uma sessão gravada. Nenhum vídeo é enviado à rede.</p>
<section><h2>Consultar cortes revisados</h2>
<p>Abra os MP4 e as explicações fornecidas por revisão humana, com análises condicionais quando presentes.</p>
<a href="session/index.html">Abrir galeria de cortes</a></section>
<section><h2>Revisar outra gravação</h2>
<p>Selecione até quatro regiões de mesas e revise intervalos. A interface não comprova cartas ou ações automaticamente.</p>
<a href="offline_visual_review_ui.html">Abrir revisão visual</a></section>
<small>Equity e EV dependem de cartas confirmadas, ranges hipotéticos e incerteza explícita. Não usar durante jogo ao vivo.</small>
</body></html>\n'''


def _manifest(session, ui, landing):
    record = json.loads((session / bundle.MANIFEST_NAME).read_text(encoding='utf-8'))
    return {
        'schema_version': 1,
        'status': STATUS,
        'source_video_included': False,
        'action_graded': False,
        'review_ui_sha256': sha(ui),
        'landing_sha256': sha(landing),
        'session_manifest_sha256': sha(session / bundle.MANIFEST_NAME),
        'clips': len(record['clips']),
        'conditional_analyses': sum(bool(c['has_conditional_analysis']) for c in record['clips']),
    }


def open_workspace(source_zip, destination):
    source, dest = Path(source_zip), Path(destination)
    ui_source = Path(__file__).with_name(REVIEW_UI)
    gallery.require(ui_source.is_file() and not ui_source.is_symlink(),
                    'missing regular offline visual review HTML beside script')
    gallery.require(dest.name not in ('', '.', '..') and dest.parent.is_dir() and
                    not dest.parent.is_symlink() and not dest.exists() and
                    not dest.is_symlink(), 'workspace must be a new directory')
    # Temporary workspace is assembled and verified before its final rename.
    with tempfile.TemporaryDirectory(prefix='.plo_workspace_', dir=dest.parent) as temp:
        stage = Path(temp)
        opener.unpack(source, stage / SESSION)  # ZIP verified before any extraction
        shutil.copyfile(ui_source, stage / REVIEW_UI)
        (stage / LANDING).write_text(landing_html(), encoding='utf-8')
        manifest = _manifest(stage / SESSION, stage / REVIEW_UI, stage / LANDING)
        (stage / WORKSPACE_MANIFEST).write_bytes(bundle.canonical_json(manifest))
        verify_workspace(stage)
        gallery.require(not dest.exists() and not dest.is_symlink(),
                        'workspace destination already exists')
        os.rename(stage, dest)
    return {'status': STATUS, 'entry': str(dest / LANDING),
            'clips': manifest['clips'], 'conditional_analyses': manifest['conditional_analyses'],
            'source_video_included': False, 'action_graded': False}


def verify_workspace(root):
    root = Path(root)
    gallery.require(root.is_dir() and not root.is_symlink(), 'invalid workspace directory')
    expected = {LANDING, REVIEW_UI, WORKSPACE_MANIFEST, SESSION}
    gallery.require({p.name for p in root.iterdir()} == expected,
                    'unexpected workspace entries')
    for name in (LANDING, REVIEW_UI, WORKSPACE_MANIFEST):
        p = root / name
        gallery.require(p.is_file() and not p.is_symlink(), 'invalid workspace file')
    session = root / SESSION
    gallery.require(session.is_dir() and not session.is_symlink(), 'invalid session directory')
    manifest = json.loads((root / WORKSPACE_MANIFEST).read_text(encoding='utf-8'))
    gallery.require(type(manifest) is dict and manifest.get('schema_version') == 1 and
                    manifest.get('status') == STATUS and
                    manifest.get('source_video_included') is False and
                    manifest.get('action_graded') is False,
                    'unsupported workspace claims')
    gallery.require(sha(root / REVIEW_UI) == manifest.get('review_ui_sha256') and
                    sha(root / LANDING) == manifest.get('landing_sha256') and
                    (root / LANDING).read_text(encoding='utf-8') == landing_html() and
                    sha(session / bundle.MANIFEST_NAME) == manifest.get('session_manifest_sha256'),
                    'workspace file integrity mismatch')
    record = json.loads((session / bundle.MANIFEST_NAME).read_text(encoding='utf-8'))
    files = record.get('files')
    gallery.require(type(files) is dict and
                    {p.name for p in session.iterdir()} == set(files) | {bundle.MANIFEST_NAME},
                    'session file inventory mismatch')
    for name, expected in files.items():
        gallery.require(name == Path(name).name and name not in ('.', '..') and
                        '/' not in name and '\\' not in name, 'unsafe session name')
        p = session / name
        gallery.require(p.is_file() and not p.is_symlink() and
                        p.stat().st_size == expected['size_bytes'] and
                        sha(p) == expected['sha256'], 'session content integrity mismatch')
    snapshot = gallery.build(session, record.get('attachments_index'))
    gallery.require((session / 'index.html').read_bytes() ==
                    gallery.render(snapshot).encode('utf-8'),
                    'session HTML differs from reviewed data')
    gallery.require(record.get('status') == 'offline_human_reviewed_session_not_verified_hands' and
                    record.get('source_video_included') is False and
                    record.get('action_graded') is False and
                    record.get('visual_card_recognition_verified') is False and
                    record.get('range_or_fold_probability_observed') is False and
                    len(snapshot['clips']) == manifest.get('clips') and
                    sum(c['analysis'] is not None for c in snapshot['clips']) ==
                    manifest.get('conditional_analyses'), 'session claims mismatch')
    return {'status': STATUS, 'clips': manifest['clips'],
            'conditional_analyses': manifest['conditional_analyses'],
            'integrity_verified': True, 'action_graded': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    opened = sub.add_parser('open')
    opened.add_argument('bundle_zip'); opened.add_argument('new_workspace')
    checked = sub.add_parser('verify'); checked.add_argument('workspace')
    args = parser.parse_args(argv)
    result = (open_workspace(args.bundle_zip, args.new_workspace) if args.command == 'open'
              else verify_workspace(args.workspace))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
