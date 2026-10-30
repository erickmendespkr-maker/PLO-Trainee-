"""Offline, read-only four-table timeline for verified reviewed PLO clips.

Usage:
    python offline_session_timeline.py PLAN ANNOTATIONS QUEUE WORKSPACE
    python offline_session_timeline.py --verify PLAN ANNOTATIONS QUEUE WORKSPACE

Requires an already verified clips/ and math/ workspace. Source timestamps,
hand boundaries and table identities remain HUMAN DECLARATIONS. No live data,
OCR inference, strategy grading or simulation is performed here. A source
video may be at most 60 minutes for this timeline view.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from html import escape
import json
import math
from pathlib import Path

import offline_reviewed_math_clip_gallery as bridge

MAX_SESSION_SECONDS = 3600
MAX_TABLES = 4


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(verified):
    """Normalize the output of bridge.assemble; reject impossible table timelines."""
    require(type(verified) is dict and type(verified.get('rows')) is list,
            'invalid verified gallery')
    rows = verified['rows']
    require(1 <= len(rows) <= 100, 'timeline supports 1..100 reviewed clips')
    by_table = defaultdict(list)
    hands = set()
    for item in rows:
        require(type(item) is dict, 'invalid reviewed row')
        hand, table = item.get('hand_id'), item.get('table_id')
        require(type(hand) is str and type(table) is str and
                bridge.q.ID.fullmatch(hand) and bridge.q.ID.fullmatch(table),
                'invalid hand or table ID')
        require(hand not in hands, 'duplicate hand across tables')
        hands.add(hand)
        start, end = item.get('start'), item.get('end')
        require(type(start) in (float, int) and type(end) in (float, int) and
                math.isfinite(start) and math.isfinite(end) and
                0 <= start < end <= MAX_SESSION_SECONDS,
                'clip timestamp outside 60-minute session')
        require(type(item.get('explanation')) is str, 'missing human explanation')
        require(type(item.get('video')) is str and item['video'] == hand + '.mp4',
                'invalid clip filename')
        require(type(item.get('math')) is dict and
                item['math'].get('status') in ('blocked', 'conditional'),
                'invalid math status')
        by_table[table].append(item)
    require(len(by_table) <= MAX_TABLES, 'more than four tables')
    result = []
    for table, group in sorted(by_table.items()):
        ordered = sorted(group, key=lambda x: (x['start'], x['end'], x['hand_id']))
        for previous, current in zip(ordered, ordered[1:]):
            require(current['start'] >= previous['end'],
                    'overlapping reviewed hands on the same table')
        result.append({'table_id': table, 'rows': ordered,
                       'calculated': sum(x['math']['status'] == 'conditional' for x in ordered),
                       'blocked': sum(x['math']['status'] == 'blocked' for x in ordered)})
    return {'tables': result, 'total_hands': len(rows),
            'max_declared_timestamp': max(x['end'] for x in rows),
            'source_video_sha256_claim': verified['source_video_sha256_claim'],
            'recognition_verified': False, 'action_graded': False}


def _time(seconds):
    minutes, rem = divmod(seconds, 60)
    return f'{int(minutes):02d}:{rem:06.3f}'


def render(timeline):
    nav = []
    sections = []
    for group in timeline['tables']:
        table = escape(group['table_id'])
        nav.append(f'<a href="#table-{table}">{table}: {len(group["rows"])} mãos</a>')
        bars = []
        cards = []
        for item in group['rows']:
            hand = escape(item['hand_id'])
            start, end = item['start'], item['end']
            left = 100 * start / MAX_SESSION_SECONDS
            width = 100 * (end - start) / MAX_SESSION_SECONDS
            label = escape(f'{item["hand_id"]} · {_time(start)}–{_time(end)}', quote=True)
            bars.append(f'<a class="segment" href="#hand-{hand}" title="{label}" '
                        f'aria-label="{label}" style="left:{left:.5f}%;width:{width:.5f}%"></a>')
            info = item['math']
            if info['status'] == 'blocked':
                detail = ('<p>Sem cálculo: ' +
                          escape(', '.join(str(s) for s in info['reasons'])) + '</p>')
            else:
                ci = info['ci']
                detail = (f'<p>Equity condicional: {info["equity"]*100:.2f}% '
                          f'(IC 95% amostral: {ci[0]*100:.2f}%–{ci[1]*100:.2f}%; '
                          f'{int(info["iterations"])} iterações; '
                          f'range hipotético: {escape(info["range_kind"])}). '
                          'Intervalo não inclui incerteza de cartas ou ranges.</p>')
                if info['ev'] is None:
                    detail += '<p>EV não calculado.</p>'
                else:
                    detail += ('<p>EV de call condicionado ao showdown imediato: '
                               f'{info["ev"]["call_ev_incremental"]:+.3f} unidades. '
                               'Não é avaliação da decisão real.</p>')
            cards.append(f'<details id="hand-{hand}"><summary>{hand} · '
                         f'{_time(start)}–{_time(end)} · '
                         f'{"Equity condicional" if info["status"] == "conditional" else "Não analisada"}'
                         '</summary>'
                         f'<video controls preload="none" src="clips/{escape(item["video"], quote=True)}"></video>'
                         f'<p>{escape(item["explanation"])}</p>{detail}'
                         '<p><a href="index.html">Painel de análises e proveniência</a></p>'
                         '</details>')
        sections.append(f'<section id="table-{table}"><h2>Mesa {table}</h2>'
                        f'<p>{len(group["rows"])} mãos revisadas · '
                        f'{group["calculated"]} com cálculo condicional · '
                        f'{group["blocked"]} bloqueadas</p>'
                        '<div class="track" role="group" '
                        f'aria-label="Linha do tempo da mesa {table}">{"".join(bars)}</div>'
                        '<p class="axis">00:00 · escala até 60:00 · segmentos são cortes declarados</p>'
                        + ''.join(cards) + '</section>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'media-src \'self\' blob:; style-src \'unsafe-inline\';">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee · linha do tempo offline</title>'
            '<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:0 1rem;'
            'background:#f8fafc;color:#172332}nav{display:flex;flex-wrap:wrap;gap:1rem}'
            'section,details{background:white;border:1px solid #cbd5e1;border-radius:10px;'
            'padding:1rem;margin:1rem 0}summary{cursor:pointer;font-weight:600}'
            '.track{height:24px;background:#e2e8f0;position:relative;overflow:hidden;'
            'border-radius:6px}.segment{display:block;position:absolute;top:0;height:100%;'
            'background:#2563eb;min-width:2px}.segment:focus{outline:2px solid #f59e0b}'
            '.axis{font-size:.85rem;color:#475569}video{display:block;width:100%;'
            'max-height:420px;margin-top:1rem;background:#111827}p{line-height:1.5}'
            '</style></head><body><h1>Revisão de sessões gravadas · PLO5/PLO6</h1>'
            '<p>Somente análise offline. Timestamps, mesas, cartas e limites das mãos '
            'são declarações humanas, não reconhecimento automático comprovado. '
            'Equity e EV dependem de ranges hipotéticos; não são notas de jogadas. '
            'Hashes verificam integridade, não autenticidade visual.</p>'
            f'<p>{timeline["total_hands"]} corte(s) · '
            f'{len(timeline["tables"])} mesa(s) · '
            f'último timestamp declarado {_time(timeline["max_declared_timestamp"])}.</p>'
            f'<nav aria-label="Mesas">{"".join(nav)}</nav>'
            + ''.join(sections) + '</body></html>\n')


def process(plan, annotations, queue, workspace, verify=False):
    root, _, _ = bridge.locate(workspace)
    dashboard = root / 'index.html'
    require(dashboard.is_file() and not dashboard.is_symlink(),
            'existing verified dashboard required')
    # Validate dashboard bytes as well as its upstream clips/math provenance.
    bridge.process(plan, annotations, queue, root, verify=True)
    destination = root / 'timeline.html'
    require(not destination.is_symlink(), 'symlink timeline forbidden')
    if verify:
        require(destination.is_file(), 'missing timeline')
    else:
        require(not destination.exists(), 'timeline already exists')
    first = prepare(bridge.assemble(plan, annotations, queue, root))
    html = render(first)
    require(prepare(bridge.assemble(plan, annotations, queue, root)) == first,
            'source changed while preparing timeline')
    if verify:
        require(destination.read_bytes() == html.encode('utf-8'),
                'timeline differs from verified inputs')
    else:
        with destination.open('x', encoding='utf-8') as stream:
            stream.write(html)
    return {'tables': len(first['tables']), 'clips': first['total_hands'],
            'verified': verify, 'recognition_verified': False, 'action_graded': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('plan'); parser.add_argument('annotations')
    parser.add_argument('queue'); parser.add_argument('workspace')
    args = parser.parse_args(argv)
    print(json.dumps(process(args.plan, args.annotations, args.queue,
                             args.workspace, verify=args.verify)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
