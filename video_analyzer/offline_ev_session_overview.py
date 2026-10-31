"""Read-only offline HTML overview of conditional EV batch clips.

Usage: python offline_ev_session_overview.py OUTPUT_DIR
This is not a poker strategy verdict or an OCR authorization.
"""
import argparse
from html import escape
import os
from pathlib import Path
import tempfile

import offline_mc_input_contract as contract


def overview(folder):
    folder = Path(folder)
    contract.check(folder.is_dir() and not folder.is_symlink(), 'invalid folder')
    target = folder / 'session_overview.html'
    contract.check(not target.exists() and not target.is_symlink(), 'overview exists')
    batch_file = folder / 'batch_report.json'
    batch = contract.read_json(batch_file)
    contract.check(type(batch) is dict and batch.get('schema_version') == 1 and
                   batch.get('status') == 'offline_conditional_ev_batch_unverified_not_strategy_verdict' and
                   batch.get('automatic_ocr_math_authorization') is False and
                   type(batch.get('clips')) is list and len(batch['clips']) <= 20 and
                   type(batch.get('skipped')) is list and len(batch['skipped']) <= 40 and
                   type(batch.get('rendered_count')) is int and
                   batch['rendered_count'] == len(batch['clips']) and
                   type(batch.get('candidate_count')) is int and
                   batch['candidate_count'] == len(batch['clips']) + len(batch['skipped']),
                   'invalid batch report')
    checked = [(batch_file, contract.sha256(batch_file))]
    html = ['<!doctype html><html lang="pt-BR"><meta charset="utf-8">',
            '<title>PLO Trainee - sessão offline</title>',
            '<h1>PLO Trainee - sessão offline</h1>',
            '<p><strong>Dados não verificados.</strong> Cartas, ranges, ações e tempos '
            'são declarações humanas. EV condicional não comprova erro; '
            'confiança do revisor não é calibrada.</p>',
            '<p>Candidatas: ', str(batch['candidate_count']), ' · Clipes: ',
            str(batch['rendered_count']), ' · Ignoradas: ', str(len(batch['skipped'])),
            ' · <a href="batch_report.json">JSON completo</a></p>']
    ids = set()
    for entry in batch['clips']:
        contract.check(type(entry) is dict, 'invalid clip')
        clip_id = entry.get('clip_id')
        contract.check(type(clip_id) is str and contract.ID.fullmatch(clip_id) and
                       clip_id not in ('.', '..') and clip_id not in ids, 'unsafe clip ID')
        ids.add(clip_id)
        mp4_name, json_name = clip_id + '.mp4', clip_id + '.json'
        contract.check(entry.get('clip_filename') == mp4_name and
                       entry.get('clip_report_filename') == json_name, 'unsafe filename')
        mp4, detail_path = folder / mp4_name, folder / json_name
        contract.check(mp4.is_file() and not mp4.is_symlink() and
                       0 < mp4.stat().st_size <= 1_000_000_000, 'invalid MP4')
        detail = contract.read_json(detail_path)
        digest = contract.sha256(mp4)
        contract.check(entry.get('clip_sha256') == digest and
                       detail.get('rendered_clip_sha256') == digest and
                       detail.get('clip_filename') == mp4_name and
                       detail.get('status') == 'offline_conditional_ev_clip_not_strategy_verdict' and
                       detail.get('automatic_ocr_math_authorization') is False and
                       detail.get('source_video_sha256') == batch.get('source_video_sha256') and
                       detail.get('source_summary_sha256') == batch.get('source_summary_sha256') and
                       detail.get('table_id') == entry.get('table_id') and
                       detail.get('hand_id') == entry.get('hand_id'), 'clip provenance mismatch')
        checked.extend([(mp4, digest), (detail_path, contract.sha256(detail_path))])
        html.extend(['<section><h2>Mesa ', escape(str(entry['table_id'])),
                     ' · Mão ', escape(str(entry['hand_id'])), '</h2><p>',
                     escape(str(detail.get('variant'))), ' · Ação declarada: ',
                     escape(str(detail.get('action_taken_claim_unverified'))),
                     ' · diferença EV condicional: ',
                     escape(str(entry.get('conditional_gap_chips_not_regret'))),
                     ' fichas</p><p><a href="', escape(mp4_name, quote=True),
                     '">MP4</a> · <a href="', escape(json_name, quote=True),
                     '">Detalhes e hipóteses</a></p></section>'])
    if batch['skipped']:
        html.append('<h2>Decisões ignoradas</h2><ul>')
        for item in batch['skipped']:
            contract.check(type(item) is dict and item.get('reason') in (
                'below_conditional_gap_threshold', 'overlapping_clip_same_table',
                'max_clips_reached'), 'invalid skipped entry')
            html.extend(['<li>', escape(str(item.get('clip_id'))), ': ',
                         escape(item['reason']), '</li>'])
        html.append('</ul>')
    html.append('<p>Índice estático offline. Consulte os JSON para seed, ranges e intervalos.</p></html>')
    with tempfile.TemporaryDirectory(prefix='plo_overview_', dir=folder) as temp:
        draft = Path(temp) / 'overview.html'
        draft.write_text(''.join(html), encoding='utf-8')
        contract.check(all(contract.sha256(p) == sha for p, sha in checked),
                       'source changed during overview')
        contract.check(not target.exists() and not target.is_symlink(), 'overview appeared')
        os.link(draft, target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir')
    print(overview(parser.parse_args().output_dir))
