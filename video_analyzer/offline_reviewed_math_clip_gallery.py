"""Offline read-only dashboard joining *reviewed* clips and conditional PLO math.

Usage:
    python offline_reviewed_math_clip_gallery.py PLAN ANNOTATIONS QUEUE WORKSPACE
    python offline_reviewed_math_clip_gallery.py --verify PLAN ANNOTATIONS QUEUE WORKSPACE

WORKSPACE must already contain clips/manifest.json, clips/*.mp4 and
math/manifest.json, math/hands/*.json. The new output is WORKSPACE/index.html.
The dashboard never extracts video observations or grades poker actions.
All card identities, ranges, clip boundaries and confidence are human claims.
"""
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path

import offline_reviewed_hand_math_queue as q
import offline_reviewed_math_runner as runner
import offline_reviewed_clip_gallery as gallery


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def locate(workspace):
    root = Path(workspace)
    require(root.is_dir() and not root.is_symlink(), 'invalid workspace')
    clips, math = root / 'clips', root / 'math'
    require(clips.is_dir() and not clips.is_symlink() and
            math.is_dir() and not math.is_symlink(), 'workspace needs real clips/ and math/ directories')
    return root, clips, math


def assemble(plan_path, annotations_path, queue_path, workspace):
    root, clips, math = locate(workspace)
    # Reconstruct and verify source queue; check result payloads and their hashes.
    checked = runner.verify_results(plan_path, annotations_path, queue_path, math)
    plan = q.read(plan_path)
    reviewed = q.validate_plan(plan)
    clip_manifest = q.read(clips / 'manifest.json')
    require(clip_manifest.get('source_plan_sha256') == q.digest(plan_path),
            'clip manifest is not bound to the reviewed plan')
    require(clip_manifest.get('source_video_sha256') == plan['source_video_sha256'],
            'clip manifest video does not match reviewed plan')
    clip_index = gallery.build(clips)
    math_manifest = q.read(math / 'manifest.json')
    require(math_manifest['source_video_sha256_claim'] == clip_index['source_video_sha256_claim'],
            'math and clip video mismatch')
    math_hands = {h['hand_id']: h for h in math_manifest['hands']}
    require(len(math_hands) == len(math_manifest['hands']), 'duplicate math hand ID')
    rows = []
    for clip in clip_index['clips']:
        hand = clip['hand_id']
        require(hand in reviewed and hand in math_hands, 'clip has no reviewed math hand')
        record, m = reviewed[hand], math_hands[hand]
        require(clip['table_id'] == record['table_id'] == m['table_id'],
                'clip and math table identity mismatch')
        require(clip['start_seconds'] == record['start_seconds'] == m['start_seconds'] and
                clip['end_seconds'] == record['end_seconds'] == m['end_seconds'],
                'clip and math timestamp mismatch')
        require(clip['analysis'] is None, 'legacy clip analysis attachment must be separate')
        if m['status'] == 'offline_conditional_equity_computed':
            result = q.read(math / m['result_file'])
            require(result['equity'] == m['equity'], 'math result mismatch')
            row_math = {'status': 'conditional', 'variant': result['variant'],
                        'equity': result['equity'],
                        'ci': result['equity_ci95_sampling_only'],
                        'iterations': result['iterations'], 'seed': result['seed'],
                        'range_kind': result['opponent_model_kind'],
                        'ev': result.get('terminal_call_ev_model'),
                        'result_file': m['result_file']}
        else:
            require(m['status'] == 'blocked_not_analyzed', 'unsupported math status')
            row_math = {'status': 'blocked', 'reasons': m['blocked_reasons']}
        rows.append({'hand_id': hand, 'table_id': clip['table_id'],
                     'start': clip['start_seconds'], 'end': clip['end_seconds'],
                     'video': clip['video'], 'explanation': clip['explanation'],
                     'confidence': m['reviewer_confidence_declared_not_calibrated'],
                     'math': row_math})
    require(len(rows) >= 1 and len(rows) <= 100, 'invalid clip count')
    require(checked['verified'] + checked['blocked'] == len(math_hands),
            'math count mismatch')
    return {'rows': rows, 'math_count': len(math_hands),
            'unclipped_math_hands': len(math_hands)-len(rows),
            'source_video_sha256_claim': plan['source_video_sha256']}


def render(data):
    pieces = []
    for item in data['rows']:
        ident, table = escape(item['hand_id']), escape(item['table_id'])
        conf = item['confidence']
        confidence = 'Não declarada' if conf is None else f'{conf:.2f} (declaração não calibrada)'
        info = item['math']
        if info['status'] == 'blocked':
            reasons = ', '.join(escape(str(s)) for s in info['reasons'])
            detail = f'<p class="muted">Sem cálculo: {reasons}. Cartas não inferidas.</p>'
        else:
            ci = info['ci']
            detail = (f'<p><strong>Equity condicional: {info["equity"]*100:.2f}%</strong> '
                      f'({escape(info["variant"])}; IC 95% amostral '
                      f'{ci[0]*100:.2f}%–{ci[1]*100:.2f}%).</p>'
                      f'<p>Range hipotético: {escape(info["range_kind"])}; '
                      f'{info["iterations"]} amostras, semente {info["seed"]}. '
                      'Intervalo não inclui incerteza de cartas ou ranges.</p>')
            ev = info['ev']
            if ev is None:
                detail += '<p>EV não calculado (parâmetros insuficientes).</p>'
            else:
                detail += (f'<p>EV incremental de call, modelo de showdown imediato: '
                           f'{ev["call_ev_incremental"]:+.3f} unidades. '
                           'Sem rake, side pots ou apostas futuras; não é avaliação da ação real.</p>')
            detail += (f'<p><a href="math/{escape(info["result_file"], quote=True)}">'
                       'Resultado matemático JSON</a></p>')
        pieces.append(f'<article><h2>{ident} · {table}</h2>'
                      f'<p>Trecho declarado: {item["start"]:.3f}–{item["end"]:.3f} s. '
                      f'Confiança do revisor: {escape(confidence)}.</p>'
                      f'<video controls preload="metadata" src="clips/{escape(item["video"], quote=True)}"></video>'
                      f'<p>{escape(item["explanation"])}</p>{detail}</article>')
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'media-src \'self\' blob:; style-src \'unsafe-inline\';">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee · cortes e matemática condicional</title>'
            '<style>body{font:16px system-ui;max-width:880px;margin:2rem auto;'
            'padding:0 1rem;background:#f8fafc;color:#172332}'
            'article{background:white;border:1px solid #d6dfe8;padding:1rem;'
            'border-radius:12px;margin:1rem 0}video{width:100%;max-height:460px;'
            'background:#101820}p{line-height:1.5}.muted{color:#775c28}</style>'
            '</head><body><h1>PLO Trainee · revisão offline</h1>'
            '<p>Somente vídeos gravados. Limites das mãos, cartas e ranges são '
            'declarações humanas, não fatos reconhecidos automaticamente. '
            'Equity e EV são condicionais, não notas de decisões. '
            'Hashes comprovam integridade dos arquivos, não autenticidade visual.</p>'
            f'<p>{len(data["rows"])} corte(s) · '
            f'{data["unclipped_math_hands"]} mão(s) sem corte nesta galeria.</p>'
            + ''.join(pieces) + '</body></html>\n')


def process(plan_path, annotations_path, queue_path, workspace, verify=False):
    root, _, _ = locate(workspace)
    dest = root / 'index.html'
    require(not dest.is_symlink(), 'linked HTML is forbidden')
    if verify:
        require(dest.is_file(), 'missing dashboard')
    else:
        require(not dest.exists(), 'dashboard already exists')
    first = assemble(plan_path, annotations_path, queue_path, root)
    html = render(first)
    # Detect source mutation before publishing; never silently regenerate an existing report.
    require(assemble(plan_path, annotations_path, queue_path, root) == first,
            'source changed while preparing dashboard')
    if verify:
        require(dest.read_bytes() == html.encode('utf-8'), 'dashboard differs from verified inputs')
    else:
        with dest.open('x', encoding='utf-8') as stream:
            stream.write(html)
    return {'clips': len(first['rows']),
            'calculated': sum(r['math']['status']=='conditional' for r in first['rows']),
            'blocked': sum(r['math']['status']=='blocked' for r in first['rows']),
            'verified': verify, 'action_graded': False}


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
