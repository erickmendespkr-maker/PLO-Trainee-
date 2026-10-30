"""Read-only offline timeline for verified cross-batch PLO5/PLO6 math history.

Usage: python offline_session_batch_timeline.py PLAN ANNOTATIONS BATCHES WORKSPACE
       python offline_session_batch_timeline.py --verify PLAN ANNOTATIONS BATCHES WORKSPACE

WORKSPACE/results must contain the verified resumable math history. Optional
WORKSPACE/clips/batch-NNNN directories contain already exported, independently
hash-verified human-reviewed MP4 clips. No video processing or poker access.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from html import escape
import json
import math
from pathlib import Path

import offline_session_batch_history as history
import offline_reviewed_clip_gallery as gallery
import offline_reviewed_hand_math_queue as queue

MAX_HANDS = 4000
MAX_SECONDS = 3600
OUTPUT = 'batch_timeline.html'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked(plan, annotations, batches, workspace):
    root = Path(workspace)
    require(root.is_dir() and not root.is_symlink(), 'workspace must be a real directory')
    results = root / 'results'
    state = history.process(plan, annotations, batches, results, verify=True)
    require(0 <= len(state['hands']) <= MAX_HANDS and
            state['total_hands_reviewed'] == len(state['hands']), 'invalid history length')
    require(state['ocr_verified'] is False and state['actions_observed_or_graded'] is False and
            state['ranges_are_hypotheses'] is True, 'unsupported provenance claims')
    batch_names = {row['directory'] for row in state['batches']}
    clips_root = root / 'clips'
    videos = {}
    if clips_root.exists() or clips_root.is_symlink():
        require(clips_root.is_dir() and not clips_root.is_symlink(), 'invalid clips root')
        require(all(p.is_dir() and not p.is_symlink() and p.name in batch_names
                    for p in clips_root.iterdir()), 'unexpected clip batch directory')
        hands = {h['hand_id']: h for h in state['hands']}
        for folder in sorted(clips_root.iterdir()):
            name = folder.name
            clip_plan = Path(batches) / name / 'plan.json'
            mf = folder / 'manifest.json'
            require(mf.is_file() and not mf.is_symlink(), 'invalid clip manifest')
            manifest = queue.read(mf)
            require(manifest.get('source_plan_sha256') == queue.digest(clip_plan),
                    'clip batch not bound to reviewed plan')
            verified = gallery.build(folder)
            require(verified['source_video_sha256_claim'] == state['source_video_sha256_claim'],
                    'clip source video differs')
            for clip in verified['clips']:
                hand = clip['hand_id']
                require(hand in hands and hands[hand]['batch'] == name and
                        hands[hand]['table_id'] == clip['table_id'] and
                        hands[hand]['start_seconds'] == clip['start_seconds'] and
                        hands[hand]['end_seconds'] == clip['end_seconds'] and
                        hand not in videos, 'clip does not match verified history')
                videos[hand] = {'src': 'clips/' + name + '/' + clip['video'],
                                'explanation': clip['explanation']}
    groups = defaultdict(list)
    seen = set()
    for hand in state['hands']:
        ident, table = hand['hand_id'], hand['table_id']
        require(ident not in seen and queue.ID.fullmatch(ident) and queue.ID.fullmatch(table),
                'invalid or repeated hand identity')
        seen.add(ident)
        a, b = hand['start_seconds'], hand['end_seconds']
        require(type(a) in (int, float) and type(b) in (int, float) and
                math.isfinite(a) and math.isfinite(b) and 0 <= a < b <= MAX_SECONDS,
                'timestamp outside session')
        require(hand['status'] in ('offline_conditional_equity_computed', 'blocked_not_analyzed'),
                'unknown math status')
        groups[table].append(hand)
    require(len(groups) <= 4, 'more than four tables')
    for rows in groups.values():
        rows.sort(key=lambda h: (h['start_seconds'], h['end_seconds'], h['hand_id']))
        require(all(b['start_seconds'] >= a['end_seconds'] for a, b in zip(rows, rows[1:])),
                'overlapping hands on one table')
    return state, dict(sorted(groups.items())), videos


def clock(seconds):
    minutes, rest = divmod(seconds, 60)
    return f'{int(minutes):02d}:{rest:06.3f}'


def render(state, groups, videos):
    nav, sections = [], []
    for table, hands in groups.items():
        tid = escape(table, quote=True)
        nav.append(f'<a href="#table-{tid}">{tid} ({len(hands)})</a>')
        bars, cards = [], []
        for h in hands:
            ident = escape(h['hand_id'], quote=True)
            a, b = h['start_seconds'], h['end_seconds']
            label = escape(f'{h["hand_id"]} {clock(a)}–{clock(b)}', quote=True)
            bars.append(f'<a class="segment" href="#hand-{ident}" title="{label}" '
                        f'style="left:{a/36:.5f}%;width:{(b-a)/36:.5f}%"></a>')
            calculated = h['status'] == 'offline_conditional_equity_computed'
            if calculated:
                ci = h['equity_ci95_sampling_only']
                detail = (f'<p>Equity condicional: {h["equity"]*100:.2f}% '
                          f'(IC 95% apenas amostral: {ci[0]*100:.2f}%–{ci[1]*100:.2f}%; '
                          f'{h["iterations"]} iterações; semente {h["seed"]}). '
                          'Ranges hipotéticos; incerteza visual não incluída.</p>')
                ev = h['terminal_call_ev_model']
                detail += ('<p>EV de call não calculado.</p>' if ev is None else
                           f'<p>EV incremental de call, showdown imediato: '
                           f'{ev["call_ev_incremental"]:+.3f} unidades; não é nota da jogada.</p>')
                path = escape('results/' + h['result_path'], quote=True)
                detail += f'<p><a href="{path}">Resultado JSON verificado</a></p>'
            else:
                detail = '<p>Sem cálculo: ' + escape(', '.join(map(str, h['blocked_reasons']))) + '</p>'
            clip = videos.get(h['hand_id'])
            if clip:
                detail += (f'<video controls preload="none" src="{escape(clip["src"], quote=True)}"></video>'
                           f'<p>Explicação declarada: {escape(clip["explanation"])}</p>')
            else:
                detail += '<p>Sem corte MP4 verificado associado.</p>'
            cards.append(f'<details id="hand-{ident}"><summary>{ident} · {clock(a)}–{clock(b)} · '
                         f'{"Equity condicional" if calculated else "Bloqueada"}</summary>{detail}</details>')
        calculated_count = sum(h['status'] == 'offline_conditional_equity_computed' for h in hands)
        sections.append(f'<section id="table-{tid}"><h2>Mesa {tid}</h2><p>{len(hands)} mãos · '
                        f'{calculated_count} calculadas · {len(hands)-calculated_count} bloqueadas</p>'
                        '<div class="track" aria-label="Linha do tempo de mãos declaradas">'
                        + ''.join(bars) + '</div><p class="muted">Escala 00:00–60:00</p>'
                        + ''.join(cards) + '</section>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'media-src \'self\' blob:; style-src \'unsafe-inline\';">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee · histórico de lotes</title>'
            '<style>body{font:16px system-ui;max-width:1050px;margin:2rem auto;'
            'padding:0 1rem;background:#f8fafc;color:#172332}nav{display:flex;gap:1rem;'
            'flex-wrap:wrap}section,details{background:white;border:1px solid #cbd5e1;'
            'border-radius:9px;padding:1rem;margin:1rem 0}summary{cursor:pointer}'
            '.track{height:24px;background:#e2e8f0;position:relative;overflow:hidden}'
            '.segment{position:absolute;top:0;height:100%;background:#2563eb;min-width:2px}'
            'video{display:block;width:100%;max-height:420px;background:#111827}'
            '.muted{color:#475569}p{line-height:1.5}</style></head><body>'
            '<h1>PLO Trainee · histórico offline de sessões gravadas</h1>'
            '<p>Cartas, ranges, mesas e timestamps são declarações humanas não verificadas '
            'por OCR. Equity/EV são modelos condicionais, nunca avaliação definitiva. '
            'Hashes garantem integridade local, não autenticidade da gravação.</p>'
            f'<p>{state["total_hands_reviewed"]} mãos · {len(groups)} mesas · '
            f'{state["completed_batches"]}/{state["total_batches"]} lotes · '
            f'{len(videos)} cortes MP4 verificados · '
            f'{"Completo" if state["complete"] else "Parcial"}.</p>'
            f'<nav aria-label="Mesas">{"".join(nav)}</nav>'
            + ''.join(sections) + '</body></html>\n')


def process(plan, annotations, batches, workspace, verify=False):
    root = Path(workspace)
    dest = root / OUTPUT
    require(not dest.is_symlink(), 'symlink output forbidden')
    require(dest.is_file() if verify else not dest.exists(),
            'missing timeline' if verify else 'timeline already exists')
    first = checked(plan, annotations, batches, root)
    html = render(*first).encode('utf-8')
    require(checked(plan, annotations, batches, root) == first,
            'sources changed during rendering')
    if verify:
        require(dest.read_bytes() == html, 'timeline differs from verified sources')
    else:
        with dest.open('xb') as stream:
            stream.write(html)
    return {'hands': first[0]['total_hands_reviewed'], 'tables': len(first[1]),
            'clips': len(first[2]), 'complete': first[0]['complete'],
            'verified': verify, 'ocr_verified': False, 'action_graded': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    for name in ('plan', 'annotations', 'batches', 'workspace'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    print(json.dumps(process(args.plan, args.annotations, args.batches,
                             args.workspace, verify=args.verify)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
