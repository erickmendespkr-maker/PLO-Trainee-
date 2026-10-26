"""Build a bounded, read-only offline session index from manually linked PLO clips.

This is a presentation layer, NOT OCR, hand detection, automatic clip selection,
Monte Carlo recomputation, or proof of strategic error. All files remain local.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import stat
from urllib.parse import quote

from offline_clip_review_page import (file_sha, read_json, require,
                                      validate_link, validate_visual)

MAX_ENTRIES = 40
MAX_MANIFEST = 128 * 1024
MAX_HTML = 256 * 1024
FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ -]{0,119}\Z")


def safe_name(name, extension):
    require(type(name) is str and FILENAME.fullmatch(name) is not None and
            name not in ('.', '..') and not name.startswith('.') and
            name.lower().endswith(extension), 'Unsafe filename')
    return name


def regular_file(root, name, extension):
    name = safe_name(name, extension)
    path = root / name
    require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0,
            'Missing, empty or unsafe input')
    return path


def esc(value):
    return html.escape(str(value), quote=True)


def fmt(value, digits=2):
    return f'{value:.{digits}f}'


def render_index(label, records, manifest_digest):
    cards = []
    for item in records:
        link = item['link']
        math_data = link['hypothetical_math']
        window = link['clip_selection_seconds_human']
        ci = math_data['equity_sampling_ci95']
        ev_ci = math_data['ev_sampling_ci95']
        url = esc('./' + quote(item['clip_name'], safe=''))
        visual = (f"MAE visual amostrado: {fmt(item['visual']['mean_best_normalized_gray_mae'], 6)}; "
                  'não verifica PTS ou cartas.' if item['visual'] else
                  'Sem comparação visual amostrada.')
        cards.append(f'''<article>
<h2>Mesa {link['table_id']} · {esc(link['hand_label_human_assigned'])} · {esc(math_data['variant'])}</h2>
<p>Janela escolhida manualmente: {fmt(window[0],3)}–{fmt(window[1],3)} s; decisão alegada: {fmt(link['decision_timestamp_seconds_human'],3)} s.</p>
<video controls preload="none" playsinline src="{url}">MP4 local indisponível.</video>
<div class="metrics"><p>Equity hipotética: <strong>{fmt(100*math_data['equity'])}%</strong><br><small>IC 95% apenas amostral: {fmt(100*ci[0])}%–{fmt(100*ci[1])}%</small></p>
<p>EV modelado vs fold=0: <strong>{fmt(math_data['ev_vs_fold_zero'])} fichas</strong><br><small>IC 95% apenas amostral: {fmt(ev_ci[0])} a {fmt(ev_ci[1])}</small></p>
<p>Confiança humana subjetiva: <strong>{fmt(100*math_data['human_confidence_subjective'])}%</strong><br><small>Não é confiança estatística.</small></p></div>
<details><summary>Hipóteses, limites e rastreabilidade</summary>
<p>Ação assumida: {esc(math_data['action_assumed'])}; Monte Carlo: {math_data['monte_carlo_trials']} simulações; semente: {math_data['monte_carlo_seed']}.</p>
<p>Range: {esc(math_data['opponent_range_combinations'] if math_data['opponent_range_combinations'] is not None else 'não informado')} combinações.</p>
<p>Hipóteses: {esc(math_data['model_notes'])}</p><p>Limitações: {esc(math_data['model_limitations'])}</p>
<p>{esc(visual)}</p><p>SHA-256 MP4: <code>{esc(link['clip_mp4_sha256'])}</code></p>
<p>SHA-256 vínculo: <code>{item['link_digest']}</code></p>
<p>Aviso: {esc(link['warning'])}</p></details></article>''')
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · Sessão offline · {esc(label)}</title><style>
:root{{color-scheme:dark}}body{{font:16px/1.5 system-ui,sans-serif;max-width:1150px;margin:auto;padding:2rem;background:#101827;color:#edf2f8}}
header,article{{background:#1b293d;border:1px solid #41536b;border-radius:14px;padding:1.2rem;margin:1rem 0}}
.warning{{background:#49301d;border-color:#c48a48}}video{{width:100%;max-height:420px;background:black;border-radius:8px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem}}
small{{color:#c9d7e6}}p,code{{overflow-wrap:anywhere}}summary{{cursor:pointer}}@media print{{video{{display:none}}}}
</style></head><body><header><h1>PLO Trainee · Sessão offline</h1>
<p>{esc(label)} · {len(records)} cortes · até quatro mesas · ordem por timestamp humano.</p>
<p>Sem rede, JavaScript, captura ao vivo ou interação com plataformas de pôquer.</p></header>
<section class="warning" role="note"><h2>⚠️ Revisão hipotética, não validada contra vídeo real</h2>
<p>As mãos, os timestamps e as decisões foram identificados manualmente. Os intervalos estatísticos cobrem somente a amostragem, não incertezas de OCR, ranges ou modelo. Não há erros estratégicos comprovados nem seleção automática de cortes.</p></section>
{''.join(cards)}<footer><p>SHA-256 do manifesto de sessão: <code>{manifest_digest}</code>. Este índice não recalcula equity ou EV.</p></footer></body></html>'''


def export_index(manifest_path, output_path):
    manifest_file, target = Path(manifest_path), Path(output_path)
    root = manifest_file.parent
    require(root.is_dir() and not root.is_symlink() and
            target.parent.resolve() == root.resolve() and
            not target.parent.is_symlink() and
            target.suffix.lower() == '.html' and not target.exists() and
            target.resolve() != manifest_file.resolve(),
            'Output must be a new HTML file beside the manifest')
    manifest, raw = read_json(manifest_file, MAX_MANIFEST)
    require(set(manifest) == {'schema_version', 'session_label', 'entries'} and
            manifest['schema_version'] == 1, 'Invalid session manifest')
    label = manifest['session_label']
    require(type(label) is str and 0 < len(label) <= 120, 'Invalid session label')
    entries = manifest['entries']
    require(type(entries) is list and 1 <= len(entries) <= MAX_ENTRIES,
            'Expected 1–40 manually selected clips')
    seen_files = {manifest_file.name, target.name}
    seen_hands = set()
    records = []
    session_key = None
    snapshots = [(manifest_file, hashlib.sha256(raw).hexdigest())]
    for entry in entries:
        require(type(entry) is dict and set(entry) in
                ({'clip', 'link'}, {'clip', 'link', 'visual'}), 'Invalid clip entry')
        paths = []
        for key, suffix in [('clip', '.mp4'), ('link', '.json'), ('visual', '.json')]:
            if key in entry:
                path = regular_file(root, entry[key], suffix)
                require(path.name not in seen_files, 'Repeated or overlapping file')
                seen_files.add(path.name)
                paths.append((key, path))
        files = dict(paths)
        clip_sha = file_sha(files['clip'])
        link, link_raw = read_json(files['link'], 128 * 1024)
        validate_link(link, clip_sha)
        key = (link['job_id'], link['source_recording_sha256'])
        require(session_key is None or session_key == key,
                'Mixed source recording or job in one session')
        session_key = key
        hand_key = (link['table_id'], link['hand_label_human_assigned'])
        require(hand_key not in seen_hands, 'Duplicate table/hand identity')
        seen_hands.add(hand_key)
        visual = None
        if 'visual' in files:
            visual, _ = read_json(files['visual'], 32 * 1024)
            validate_visual(visual, link)
        records.append({'link': link, 'clip_name': files['clip'].name,
                        'link_digest': hashlib.sha256(link_raw).hexdigest(),
                        'visual': visual})
        snapshots.extend((path, file_sha(path)) for _, path in paths)
    records.sort(key=lambda r: (r['link']['decision_timestamp_seconds_human'],
                                r['link']['table_id'], r['link']['hand_label_human_assigned']))
    payload = render_index(label, records, hashlib.sha256(raw).hexdigest()).encode('utf-8')
    require(len(payload) <= MAX_HTML, 'HTML output too large')
    require(all(path.is_file() and not path.is_symlink() and file_sha(path) == digest
                for path, digest in snapshots), 'Input changed during index generation')
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'Unsafe output')
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {'status': 'offline_manual_multi_hand_index_not_video_verified',
            'hands': len(records), 'tables': sorted({r['link']['table_id'] for r in records}),
            'output': str(target)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session_manifest_json')
    parser.add_argument('new_session_index_html')
    args = parser.parse_args(argv)
    print(json.dumps(export_index(args.session_manifest_json, args.new_session_index_html)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
