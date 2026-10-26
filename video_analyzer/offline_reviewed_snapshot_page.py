"""Render an offline, read-only comparison of original and human-reviewed hands.

No video/OCR verification, math authorization, live capture or remote resources.
The source draft, correction overlay, independent review and candidate snapshot
must form a consistent chain; this module never changes them.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import stat

from offline_hand_correction_overlay import canonical, check, digest, read_json, validate_draft
from offline_hand_reviewed_snapshot import build_snapshot

MAX_HANDS = 200
MAX_HTML = 1024 * 1024
FIELDS_TO_SHOW = (
    "variant", "hero_cards", "board_by_street", "actions", "pot_before_decision",
    "call_amount", "effective_stack", "source_pts_start_seconds",
    "source_pts_end_seconds", "opponent_range_notes", "confidence_subjective", "notes",
)


def esc(value):
    return html.escape(str(value), quote=True)


def value_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def validate_chain(draft, overlay, review, snapshot):
    """Reject modified candidate data and invalid or mismatched source records."""
    lookup = validate_draft(draft)
    check(type(snapshot) is dict, "Invalid snapshot")
    rebuilt = build_snapshot(draft, overlay, review)
    check(canonical(rebuilt) == canonical(snapshot), "Snapshot differs from reviewed source chain")
    check(0 < len(rebuilt["hands"]) <= MAX_HANDS, "Expected 1-200 reviewed hands")
    for row in rebuilt["hands"]:
        for gate in ("hand_reconstruction_verified", "source_pts_verified",
                     "ready_for_equity_or_ev", "automatic_clip_selection_authorized"):
            check(row[gate] is False, "Unverified hand cannot be authorized")
    return lookup, rebuilt


def render_page(draft, snapshot, lookup):
    blocks = []
    for row in snapshot["hands"]:
        key = (row["table_id"], row["hand_label_human_assigned"])
        old = lookup[key]
        new = row["human_entry_candidate"]
        changed = {proof["field"] for proof in row["applied_corrections"]}
        rows = []
        for field in FIELDS_TO_SHOW:
            was = value_text(old[field])
            now = value_text(new[field])
            diff = canonical(old[field]) != canonical(new[field])
            check(diff == (field in changed), "Untracked candidate change")
            css = ' class="changed"' if diff else ''
            rows.append(f'<tr{css}><th scope="row">{esc(field)}</th><td><code>{esc(was)}</code></td>'
                        f'<td><code>{esc(now)}</code></td><td>{"Revisado" if diff else "Sem alteração"}</td></tr>')
        proofs = ''.join(
            '<li><strong>' + esc(p['field']) + '</strong> · proposta ' +
            '<code>' + esc(p['correction_sha256']) + '</code> · motivo: ' +
            esc(p['review_reason']) + '</li>'
            for p in row['applied_corrections']
        ) or '<li>Nenhuma correção aceita para esta mão.</li>'
        blocks.append(f'''<section class="hand"><h2>Mesa {row['table_id']} · {esc(key[1])} · {esc(new['variant'])}</h2>
<p>Estado: <strong>candidato revisado por humanos; não verificado no vídeo.</strong> {len(changed)} campo(s) alterado(s).</p>
<div class="scroll"><table><thead><tr><th>Campo</th><th>Original</th><th>Candidato revisado</th><th>Diferença</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<details><summary>Proveniência das correções aceitas</summary><ul>{proofs}</ul>
<p>SHA-256 da entrada original: <code>{esc(row['original_human_entry_sha256'])}</code></p>
<p>SHA-256 da entrada candidata: <code>{esc(row['candidate_human_entry_sha256'])}</code></p></details></section>''')
    count = snapshot['counts']
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; object-src 'none'">
<title>PLO Trainee · Revisão offline</title><style>
:root{{color-scheme:dark}}body{{font:16px/1.5 system-ui,sans-serif;max-width:1200px;margin:auto;padding:1.5rem;background:#101827;color:#edf2f8}}
header,.hand,.warning{{padding:1rem;margin:1rem 0;border:1px solid #465c78;border-radius:12px;background:#1b293d}}
.warning{{border-color:#db9b4a;background:#47321f}}.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse}}
th,td{{border:1px solid #465c78;padding:.55rem;text-align:left;vertical-align:top}}.changed{{background:#304733}}
code{{white-space:pre-wrap;overflow-wrap:anywhere}}details{{margin-top:.8rem}}summary{{cursor:pointer}}
</style></head><body><header><h1>PLO Trainee · Comparação de mãos revisadas</h1>
<p>{count['hands']} mão(s), {count['accepted_applied']} correção(ões) aceita(s), {count['rejected_unapplied']} rejeitada(s).</p>
<p>Job: <code>{esc(draft['job_id'])}</code> · origem SHA-256: <code>{esc(draft['source_sha256'])}</code></p></header>
<aside class="warning"><h2>Não é uma análise estratégica validada</h2><p>Correções aceitas representam concordância humana, não prova de OCR, cartas, ações ou timestamps no vídeo. Nenhuma mão está liberada para equity, EV, seleção automática de cortes ou julgamento de erro. Valores ausentes continuam ausentes.</p></aside>
{''.join(blocks)}<footer><p>SHA-256 do draft canônico: <code>{snapshot['source_draft_sha256']}</code>; overlay: <code>{snapshot['source_overlay_sha256']}</code>; revisão: <code>{snapshot['source_review_sha256']}</code>.</p>
<p>Relatório estático e local. Sem JavaScript, rede ou integração com plataformas de pôquer.</p></footer></body></html>'''


def export_page(draft_path, overlay_path, review_path, snapshot_path, output_path):
    paths = [Path(p) for p in (draft_path, overlay_path, review_path, snapshot_path, output_path)]
    target = paths[-1]
    check(len({p.resolve() for p in paths}) == len(paths) and
          target.suffix.lower() == '.html' and target.parent.is_dir() and
          not target.parent.is_symlink() and not target.exists(), "Unsafe output path")
    loaded = [read_json(path) for path in paths[:-1]]
    draft, overlay, review, snapshot = (item[0] for item in loaded)
    lookup, validated = validate_chain(draft, overlay, review, snapshot)
    payload = render_page(draft, validated, lookup).encode('utf-8')
    check(len(payload) <= MAX_HTML, "HTML output exceeds limit")
    check(all(path.is_file() and not path.is_symlink() and path.read_bytes() == raw
              for path, (_, raw) in zip(paths[:-1], loaded)), "Source changed during rendering")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                 getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            check(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Unsafe output")
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {'status': 'offline_review_comparison_not_video_verified',
            'hands': validated['counts']['hands'],
            'accepted': validated['counts']['accepted_applied'],
            'rejected': validated['counts']['rejected_unapplied'],
            'ready_for_equity_or_ev': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('draft_json', 'overlay_json', 'review_json', 'reviewed_snapshot_json', 'new_html'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    print(json.dumps(export_page(args.draft_json, args.overlay_json, args.review_json,
                                 args.reviewed_snapshot_json, args.new_html)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
