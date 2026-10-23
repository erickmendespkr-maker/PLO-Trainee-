"""Create evidence-separated, unverified explanations for OFFLINE PLO review clips.

Revalidates the original MP4s and deterministically replays the hypothetical
Monte Carlo before producing a JSON sidecar. Does not select, rank, or label
strategic mistakes; never changes video bytes or approves a model for play.
"""
import argparse
import json
import math
from pathlib import Path

from activity_hypothetical_math import MODEL, digest
from activity_math_clip_context import build_math_clip_context

STATUS = 'human_selected_structured_explanations_unverified'


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Invalid numeric explanation field: ' + name)
    return float(value)


def _percent(value):
    return f'{100 * _number(value, "equity"):.1f}%'


def build_explanations(manifest, clips_dir, worksheet, request, report):
    """Revalidate source evidence and partition review, assumptions and results."""
    context = build_math_clip_context(manifest, clips_dir, worksheet, request, report)
    scenarios = {(s['table_id'], s['hand_id'], s['event_index']): s
                 for s in worksheet['scenarios']}
    output = []
    for clip in context['clips']:
        key = (clip['table_id'], clip['hand_id'], clip['event_index'])
        scenario = scenarios[key]
        reviewed = scenario['reviewed_visible_inputs']
        base = [
            'REVISÃO OFFLINE — SEM DIAGNÓSTICO DE ERRO',
            f'Mesa {clip["table_id"]} | evento {clip["event_index"]} | '
            f'PTS {_number(clip["decision_timestamp"], "timestamp"):.2f}s',
            'Dados de cartas/ações: revisão humana, NÃO auditados no vídeo.',
        ]
        math_data = clip['hypothetical_math']
        if math_data is None:
            assumptions = None
            result = None
            lines = base + [
                'Sem cálculo de equity/EV para este trecho.',
                'Sem range adversário validado; não inferir erro.',
            ]
        else:
            if math_data['model'] != MODEL or math_data['variant'] not in ('PLO5', 'PLO6'):
                raise ValueError('Unexpected hypothetical model')
            ci = math_data['equity_sampling_ci95']
            ev_ci = math_data['call_ev_sampling_ci95']
            if (not isinstance(ci, list) or len(ci) != 2
                    or not isinstance(ev_ci, list) or len(ev_ci) != 2):
                raise ValueError('Invalid Monte Carlo interval')
            if (not 0 <= _number(ci[0], 'CI low') <= _number(math_data['equity'], 'equity')
                    <= _number(ci[1], 'CI high') <= 1):
                raise ValueError('Invalid equity interval bounds')
            if _number(ev_ci[0], 'EV CI low') > _number(ev_ci[1], 'EV CI high'):
                raise ValueError('Invalid EV interval bounds')
            weights = [entry['weight'] for entry in math_data['opponent_range']]
            total_weight = sum(_number(w, 'range weight') for w in weights)
            if not total_weight > 0:
                raise ValueError('Empty weighted opponent hypothesis')
            assumptions = {
                'model': MODEL,
                'opponent_range_origin': 'user_supplied_hypothesis_not_observed',
                'range_combinations': len(weights),
                'range_total_weight': total_weight,
                'trials': math_data['trials'], 'seed': math_data['seed'],
                'rake_included': False, 'future_betting_included': False,
                'opponent_behavior_verified': False,
            }
            result = {
                'variant': math_data['variant'],
                'equity': math_data['equity'],
                'equity_sampling_ci95': ci,
                'call_ev_vs_fold': math_data['call_ev_vs_fold'],
                'call_ev_sampling_ci95': ev_ci,
                'pot_before_call': math_data['pot_before_call'],
                'call_amount': math_data['call_amount'],
                'interpretation': 'conditional_heads_up_all_in_call_what_if_not_real_hand_ev',
            }
            lines = base + [
                f'{math_data["variant"]}: hipótese heads-up all-in; range fornecido.',
                f'Equity hipotética {_percent(math_data["equity"])}; '
                f'IC amostral {_percent(ci[0])}–{_percent(ci[1])}.',
                f'EV call vs fold: {math_data["call_ev_vs_fold"]:+.2f} '
                '(unidades do pote).',
                'Sem rake/apostas futuras; IC NÃO cobre erro do range.',
                'NÃO é EV real, nem prova de acerto ou erro.',
            ]
        output.append({
            'filename': clip['filename'], 'table_id': key[0], 'hand_id': key[1],
            'event_index': key[2], 'decision_timestamp': clip['decision_timestamp'],
            'original_mp4_sha256': clip['original_mp4_sha256'],
            'observed_review': {
                'status': 'human_attested_not_independently_video_verified',
                'action': reviewed['observed_action'],
                'hero_cards': reviewed['hero_cards'], 'board': reviewed['board'],
                'pot_before_action': reviewed['pot_before_action'],
                'call_amount': reviewed['call_amount'],
                'unconfirmed_fields': scenario['unconfirmed_fields'],
                'human_explanation': clip['human_review_explanation'],
            },
            'hypotheses': assumptions,
            'conditional_result': result,
            'display_card_lines': lines,
            'strategic_error_established': False,
            'eligible_for_ev_ranking': False,
            'video_evidence_verified': False,
        })
    return {
        'schema_version': 1, 'analysis_status': STATUS,
        'source_math_context_sha256': digest(context),
        'source_clip_manifest_sha256': digest(manifest),
        'source_worksheet_sha256': digest(worksheet),
        'source_request_sha256': digest(request),
        'source_math_report_sha256': digest(report),
        'recording_sha256': context['recording_sha256'],
        'ready_for_equity_or_ev': False, 'authorized_for_ev_based_ranking': False,
        'source_visual_content_verified': False,
        'clips': output,
        'warning': ('Human review is not independent video verification. Monte Carlo '
                    'is conditional on user-supplied ranges and a simplified all-in '
                    'model. No actual-hand EV, error diagnosis, or automatic ranking.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('clip_manifest_json', 'clips_dir', 'worksheet_json',
                'request_json', 'hypothetical_report_json', 'output_json'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    paths = [Path(p) for p in (args.clip_manifest_json, args.worksheet_json,
                                args.request_json, args.hypothetical_report_json)]
    output = Path(args.output_json)
    if (output.exists() or output.is_symlink()
            or output.resolve() in {p.resolve() for p in paths}
            or any(not p.is_file() or p.is_symlink() for p in paths)
            or not Path(args.clips_dir).is_dir() or Path(args.clips_dir).is_symlink()):
        raise ValueError('Require regular inputs and a new distinct output file')
    inputs = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    result = build_explanations(inputs[0], args.clips_dir, *inputs[1:])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'clips': len(result['clips']), 'ev_ranking_authorized': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
