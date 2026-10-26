"""Read-only offline crosswalk: manually selected MP4 clips ↔ reviewed hand candidates.

A matching job/source SHA and table/hand label is a *declared association*, not
video verification. This view never recomputes equity/EV or authorizes decisions.
It requires a valid Cycle 118–120 independent-review chain and Cycle 114 clip
manifest. Source files remain unchanged; output is a new local HTML file.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import stat
from urllib.parse import quote

from offline_clip_review_page import file_sha, read_json as read_clip_json, require, validate_link, validate_visual
from offline_hand_correction_overlay import read_json as read_hand_json
from offline_reviewed_snapshot_page import FIELDS_TO_SHOW, validate_chain, value_text
from offline_session_review_index import MAX_ENTRIES, MAX_MANIFEST, regular_file

MAX_HTML = 1024 * 1024


def esc(value):
    return html.escape(str(value), quote=True)


def load_crosswalk(manifest_path, draft_path, overlay_path, review_path, snapshot_path):
    """Validate every input, cross-check exact identities and retain file hashes."""
    paths = [Path(p) for p in (manifest_path, draft_path, overlay_path, review_path, snapshot_path)]
    root = paths[0].parent
    require(root.is_dir() and not root.is_symlink() and
            len({p.resolve() for p in paths}) == len(paths) and
            all(p.parent.resolve() == root.resolve() and not p.parent.is_symlink() and
                p.is_file() and not p.is_symlink() for p in paths),
            'All distinct input files must be regular files in the session folder')
    manifest, manifest_raw = read_clip_json(paths[0], MAX_MANIFEST)
    require(set(manifest) == {'schema_version', 'session_label', 'entries'} and
            type(manifest['schema_version']) is int and manifest['schema_version'] == 1 and
            type(manifest['session_label']) is str and
            0 < len(manifest['session_label']) <= 120, 'Invalid session manifest')
    entries = manifest['entries']
    require(type(entries) is list and 1 <= len(entries) <= MAX_ENTRIES,
            'Expected 1–40 manually selected clips')
    loaded = [read_hand_json(p) for p in paths[1:]]
    draft, overlay, review, snapshot = (pair[0] for pair in loaded)
    lookup, checked_snapshot = validate_chain(draft, overlay, review, snapshot)
    snapshot_hands = {(row['table_id'], row['hand_label_human_assigned']): row
                      for row in checked_snapshot['hands']}
    require(len(snapshot_hands) == len(checked_snapshot['hands']), 'Duplicate snapshot hand')
    seen_names = {p.name for p in paths}
    snapshots = [(paths[0], hashlib.sha256(manifest_raw).hexdigest())]
    snapshots += [(p, hashlib.sha256(raw).hexdigest()) for p, (_, raw) in zip(paths[1:], loaded)]
    seen_hands = set()
    records = []
    for entry in entries:
        require(type(entry) is dict and set(entry) in
                ({'clip', 'link'}, {'clip', 'link', 'visual'}), 'Invalid clip entry')
        files = {}
        for key, suffix in (('clip', '.mp4'), ('link', '.json'), ('visual', '.json')):
            if key not in entry:
                continue
            path = regular_file(root, entry[key], suffix)
            require(path.name not in seen_names, 'Overlapping or repeated source file')
            seen_names.add(path.name)
            files[key] = path
        clip_digest = file_sha(files['clip'])
        link, _ = read_clip_json(files['link'], 128 * 1024)
        validate_link(link, clip_digest)
        require(link['job_id'] == draft['job_id'] and
                link['source_recording_sha256'] == draft['source_sha256'],
                'Clip and reviewed hand chain belong to different jobs/recordings')
        hand_key = (link['table_id'], link['hand_label_human_assigned'])
        require(hand_key not in seen_hands, 'Repeated table/hand identity')
        seen_hands.add(hand_key)
        visual = None
        if 'visual' in files:
            visual, _ = read_clip_json(files['visual'], 32 * 1024)
            validate_visual(visual, link)
        candidate = snapshot_hands.get(hand_key)
        if candidate is not None:
            require(candidate['human_entry_candidate']['variant'] ==
                    link['hypothetical_math']['variant'],
                    'PLO variant mismatch between candidate and hypothetical clip math')
        records.append({'clip_name': files['clip'].name, 'link': link,
                        'candidate': candidate, 'visual': visual})
        snapshots.extend((p, file_sha(p)) for p in files.values())
    records.sort(key=lambda r: (r['link']['decision_timestamp_seconds_human'],
                                r['link']['table_id'], r['link']['hand_label_human_assigned']))
    return manifest['session_label'], records, lookup, checked_snapshot, snapshots


def render_crosswalk(label, records, lookup, snapshot, hashes):
    """Inert local HTML. Human corrections and old hypothetical math are separate."""
    sections = []
    matched_keys = set()
    for record in records:
        link, candidate = record['link'], record['candidate']
        key = (link['table_id'], link['hand_label_human_assigned'])
        math_data = link['hypothetical_math']
        url = esc('./' + quote(record['clip_name'], safe=''))
        interval_warning = 'Sem intervalo de mão revisado: PTS não verificado.'
        table = '<p><strong>Sem histórico revisado para este corte.</strong> Identidade manual sem correspondência.</p>'
        if candidate is not None:
            matched_keys.add(key)
            old, new = lookup[key], candidate['human_entry_candidate']
            start, end = new['source_pts_start_seconds'], new['source_pts_end_seconds']
            if start is not None and end is not None:
                decision = link['decision_timestamp_seconds_human']
                clip_start, clip_end = link['clip_selection_seconds_human']
                interval_warning = ('Decisão fora do intervalo humano revisado; verificar manualmente.'
                                    if not start <= decision <= end else
                                    'Decisão dentro do intervalo humano revisado; não confirma PTS.')
                if clip_end < start or clip_start > end:
                    interval_warning += ' Corte sem sobreposição com intervalo revisado.'
            fields = []
            for field in FIELDS_TO_SHOW:
                before, after = value_text(old[field]), value_text(new[field])
                css = ' class="changed"' if before != after else ''
                fields.append(f'<tr{css}><th scope="row">{esc(field)}</th><td><code>{esc(before)}</code></td>'
                              f'<td><code>{esc(after)}</code></td></tr>')
            table = ('<p><strong>Candidato revisado por humanos, não confirmado no vídeo.</strong> '
                     + str(len(candidate['applied_corrections'])) + ' correção(ões) aceita(s). '
                     + esc(interval_warning) + '</p><details><summary>Comparar histórico original e candidato</summary>'
                     + '<div class="scroll"><table><thead><tr><th>Campo</th><th>Original</th><th>Revisado</th></tr></thead><tbody>'
                     + ''.join(fields) + '</tbody></table></div>'
                     + '<p>SHA-256 entrada candidata: <code>' + esc(candidate['candidate_human_entry_sha256'])
                     + '</code></p></details>')
        ci = math_data['equity_sampling_ci95']
        sections.append(f'''<article><h2>Mesa {link['table_id']} · {esc(key[1])} · {esc(math_data['variant'])}</h2>
<p>Decisão alegada: {link['decision_timestamp_seconds_human']:.3f} s; janela manual: {link['clip_selection_seconds_human'][0]:.3f}–{link['clip_selection_seconds_human'][1]:.3f} s.</p>
<video controls preload="none" playsinline src="{url}">Vídeo local indisponível.</video>
{table}
<details><summary>Equity/EV hipotéticos preexistentes — não recalculados a partir das correções</summary>
<p>Equity: {100*math_data['equity']:.2f}% (IC 95% amostral {100*ci[0]:.2f}%–{100*ci[1]:.2f}%).
EV modelado vs fold=0: {math_data['ev_vs_fold_zero']:.2f} fichas.
Semente: {math_data['monte_carlo_seed']}; simulações: {math_data['monte_carlo_trials']}.</p>
<p>Hipóteses: {esc(math_data['model_notes'])}. Limitações: {esc(math_data['model_limitations'])}.</p>
<p>SHA-256 do corte: <code>{esc(link['clip_mp4_sha256'])}</code>.</p></details></article>''')
    missing = [(row['table_id'], row['hand_label_human_assigned']) for row in snapshot['hands']
               if (row['table_id'], row['hand_label_human_assigned']) not in matched_keys]
    unmatched_html = ''.join('<li>Mesa ' + str(t) + ' · ' + esc(h) + '</li>' for t, h in missing)
    unmatched_html = ('<ul>' + unmatched_html + '</ul>' if missing else
                      '<p>Todas as mãos revisadas possuem um corte associado manualmente.</p>')
    matched = len(matched_keys)
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · Cruzamento offline · {esc(label)}</title><style>
:root{{color-scheme:dark}}body{{font:16px/1.5 system-ui,sans-serif;max-width:1180px;margin:auto;padding:1.5rem;background:#101827;color:#eef4fc}}
header,article,aside,footer{{border:1px solid #41536b;border-radius:12px;padding:1rem;margin:1rem 0;background:#1b293d}}
aside{{background:#47321f;border-color:#d99c54}}video{{width:100%;max-height:400px;background:black}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.5rem;border:1px solid #41536b;text-align:left;vertical-align:top}}
.changed{{background:#304733}}code{{overflow-wrap:anywhere;white-space:pre-wrap}}details{{margin-top:.75rem}}summary{{cursor:pointer}}
</style></head><body><header><h1>PLO Trainee · Sessão gravada e histórico revisado</h1>
<p>{esc(label)} · {len(records)} cortes · {matched} vínculos exatos por identificadores humanos · {len(records)-matched} cortes sem revisão · {len(missing)} mãos sem corte.</p>
<p>Somente leitura, local, assíncrono, sem JavaScript ou conexão a plataformas de pôquer.</p></header>
<aside><strong>Associação declarada, NÃO validação do vídeo.</strong> A correspondência usa job, SHA-256 de origem, mesa e rótulo humano da mão. Não comprova cartas, ações, PTS, OCR, ranges ou erros estratégicos. Equity/EV dos cortes são hipóteses antigas e NÃO foram recalculados a partir das correções. Nenhuma seleção automática está autorizada.</aside>
{''.join(sections)}<section><h2>Mãos revisadas sem corte correspondente</h2>{unmatched_html}</section>
<footer><p>Origem: <code>{esc(snapshot['source_recording_sha256'])}</code>. Draft canônico: <code>{esc(snapshot['source_draft_sha256'])}</code>. Revisão: <code>{esc(snapshot['source_review_sha256'])}</code>.</p>
<p>SHA-256 manifesto bruto: <code>{esc(hashes[0][1])}</code>.</p></footer></body></html>'''


def export_crosswalk(manifest_path, draft_path, overlay_path, review_path, snapshot_path, output_path):
    target = Path(output_path)
    paths = [Path(p) for p in (manifest_path, draft_path, overlay_path, review_path, snapshot_path)]
    require(target.suffix.lower() == '.html' and target.parent.is_dir() and
            not target.parent.is_symlink() and
            target.parent.resolve() == paths[0].parent.resolve() and
            not target.exists() and target.resolve() not in {p.resolve() for p in paths},
            'Output must be a new HTML file beside the session manifest')
    label, records, lookup, snapshot, hashes = load_crosswalk(*paths)
    payload = render_crosswalk(label, records, lookup, snapshot, hashes).encode('utf-8')
    require(len(payload) <= MAX_HTML, 'HTML output exceeds limit')
    require(all(p.is_file() and not p.is_symlink() and file_sha(p) == sha
                for p, sha in hashes), 'Input changed while building crosswalk')
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
    return {'status': 'offline_manual_crosswalk_not_video_verified',
            'clips': len(records), 'matched': sum(r['candidate'] is not None for r in records),
            'reviewed_without_clip': len(snapshot['hands']) - sum(r['candidate'] is not None for r in records),
            'ready_for_equity_or_ev': False, 'automatic_clip_selection_authorized': False,
            'output': str(target)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('session_manifest_json', 'draft_json', 'overlay_json', 'review_json',
                 'reviewed_snapshot_json', 'new_crosswalk_html'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    print(json.dumps(export_crosswalk(args.session_manifest_json, args.draft_json,
                                      args.overlay_json, args.review_json,
                                      args.reviewed_snapshot_json, args.new_crosswalk_html)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
