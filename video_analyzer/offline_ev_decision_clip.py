"""Export an offline MP4 excerpt with a *conditional*, visibly labeled EV overlay.

Usage: python offline_ev_decision_clip.py SUMMARY.json EV.json DECISION.json VIDEO.mp4 OUT_DIR CLIP_ID

The timestamp/action and visual review are unverified human claims. This module
never recognizes a poker action, validates strategy, or authorizes OCR as truth.
It binds the video bytes, visual-summary ledger, EV report and manual annotation
with SHA-256; the resulting clip is an educational hypothetical, not a verdict.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import offline_mc_input_contract as contract

MAX_VIDEO_SECONDS = 7200


def number(value, label, low, high):
    contract.check(type(value) in (int, float) and math.isfinite(value) and low <= value <= high,
                   f'{label}: invalid finite number')
    return float(value)


def validate(summary, ev, decision, summary_sha, ev_sha, video_sha, duration):
    """Validate cross-file provenance and mathematical accounting; no video semantics."""
    contract.check(type(summary) is dict and summary.get('schema_version') == 1 and
                   summary.get('status') == 'offline_hand_visual_summary_unverified_not_math_ready' and
                   summary.get('video_content_not_semantically_verified') is True and
                   summary.get('reviewer_claims_not_authenticated') is True and
                   summary.get('equity_or_ev_calculated') is False and
                   type(summary.get('eligible_for_equity')) is int and summary['eligible_for_equity'] == 0 and
                   summary.get('source_video_sha256_claim') == video_sha and
                   type(summary.get('hands')) is list and
                   type(summary.get('hand_count')) is int and
                   summary['hand_count'] == len(summary['hands']), 'unverified summary or video SHA mismatch')
    contract.check(type(ev) is dict and ev.get('schema_version') == 1 and
                   ev.get('status') == 'conditional_chip_ev_estimates_not_strategy_verdict' and
                   ev.get('source_summary_sha256') == summary_sha and
                   ev.get('source_video_sha256_claim') == video_sha and
                   ev.get('automatic_ocr_math_authorization') is False and
                   ev.get('input_origin_claim') == 'independent_manual_transcription_not_authenticated' and
                   ev.get('equity_calculated') is True and ev.get('ev_calculated') is True and
                   ev.get('model') == 'single_decision_showdown_no_future_betting_zero_rake' and
                   ev.get('rake_chips') == 0 and
                   type(ev.get('seed')) is int and type(ev.get('simulations')) is int and
                   ev['simulations'] >= 1000 and ev.get('variant') in ('PLO5', 'PLO6') and
                   ev.get('street') in ('flop', 'turn', 'river') and
                   type(ev.get('source_scenario_sha256')) is str and
                   contract.SHA.fullmatch(ev['source_scenario_sha256']) and
                   type(ev.get('source_action_sha256')) is str and
                   contract.SHA.fullmatch(ev['source_action_sha256']), 'invalid or unbound conditional EV report')
    contract.check(type(decision) is dict and set(decision) == {
        'schema_version', 'source_summary_sha256', 'source_ev_sha256',
        'hand_id', 'table_id', 'decision_pts_seconds', 'action_taken_claim',
        'action_origin', 'reviewer_confidence_claim', 'notes',
        'clip_before_seconds', 'clip_after_seconds'}, 'invalid decision schema')
    contract.check(type(decision['schema_version']) is int and decision['schema_version'] == 1 and
                   decision['source_summary_sha256'] == summary_sha and
                   decision['source_ev_sha256'] == ev_sha and
                   decision['action_origin'] == 'manual_review_unverified' and
                   decision['action_taken_claim'] in ('fold', 'call', 'check', 'raise') and
                   all(type(decision[k]) is str and contract.ID.fullmatch(decision[k])
                       for k in ('hand_id', 'table_id')) and
                   decision['hand_id'] == ev.get('hand_id') and
                   decision['table_id'] == ev.get('table_id'), 'decision identity/provenance mismatch')
    matches = [h for h in summary['hands'] if type(h) is dict and
               h.get('hand_id') == decision['hand_id'] and h.get('table_id') == decision['table_id']]
    contract.check(len(matches) == 1 and matches[0].get('math_ready') is False and
                   matches[0].get('eligible_for_equity') is False and
                   type(matches[0].get('declared_fields')) is list, 'unverified hand not uniquely linked')
    pts = number(decision['decision_pts_seconds'], 'decision PTS', 0, duration)
    confidence = number(decision['reviewer_confidence_claim'], 'reviewer confidence', 0, 1)
    before = number(decision['clip_before_seconds'], 'clip before', 0.5, 30)
    after = number(decision['clip_after_seconds'], 'clip after', 0.5, 30)
    contract.check(type(decision['notes']) is str and 20 <= len(decision['notes'].strip()) <= 1000,
                   'explicit reviewer notes required')
    # Only action-specific reviewed evidence anchors a decision time. Cards or
    # nearby table activity cannot be used to claim an observed action.
    evidence = []
    for field in matches[0]['declared_fields']:
        if (type(field) is dict and field.get('field') == 'action' and
            field.get('visual_status_unverified') == 'seen_by_reviewer' and
            type(field.get('evidence_pts_seconds')) is list):
            evidence.extend(field['evidence_pts_seconds'])
    contract.check(any(type(t) in (int, float) and math.isfinite(t) and
                       abs(pts - t) <= 0.5 for t in evidence),
                   'no reviewer-seen action evidence within 0.5s of decision')
    pot = number(ev.get('pot_before_action_chips'), 'pot', 0.000001, 1e9)
    call = number(ev.get('to_call_chips'), 'to call', 0, 1e9)
    equity = number(ev.get('equity_fraction'), 'equity', 0, 1)
    lohi = ev.get('equity_confidence_interval_95_approx')
    contract.check(type(lohi) is list and len(lohi) == 2, 'equity CI absent')
    lo, hi = [number(x, 'equity CI', 0, 1) for x in lohi]
    contract.check(lo <= equity <= hi, 'invalid equity CI')
    ev_call = number(ev.get('ev_call_or_check_chips'), 'call EV', -1e9, 2e9)
    expected = equity * (pot + call) - call
    contract.check(math.isclose(ev_call, expected, abs_tol=1e-6, rel_tol=1e-9) and
                   ev.get('ev_fold_chips') == 0 and
                   ev.get('call_action_label') == ('check' if call == 0 else 'call'),
                   'EV report accounting mismatch')
    interval = ev.get('ev_call_or_check_confidence_interval_95_approx_chips')
    contract.check(type(interval) is list and len(interval) == 2 and
                   all(type(v) in (int, float) and math.isfinite(v) for v in interval) and
                   all(math.isclose(v, e * (pot + call) - call, abs_tol=1e-6, rel_tol=1e-9)
                       for v, e in zip(interval, (lo, hi))), 'EV interval accounting mismatch')
    candidates = {'fold': 0.0, ev['call_action_label']: ev_call}
    raise_model = ev.get('ev_raise_model')
    if raise_model is not None:
        contract.check(type(raise_model) is dict and raise_model.get('confidence_interval_95') is None and
                       raise_model.get('opponent_can_match_raise_assumed') is True,
                       'invalid conditional raise model')
        r = number(raise_model.get('raise_total_chips'), 'raise total', call + 1e-9, 1e9)
        f = number(raise_model.get('fold_probability_assumed'), 'fold probability', 0, 1)
        ec = number(raise_model.get('called_equity_fraction_assumed_not_simulated'), 'called equity', 0, 1)
        er = number(raise_model.get('ev_chips'), 'raise EV', -1e9, 2e9)
        contract.check(math.isclose(er, f * pot + (1-f)*(ec*(pot + r + r-call)-r),
                                    abs_tol=1e-6, rel_tol=1e-9), 'raise EV accounting mismatch')
        candidates['raise'] = er
    action = decision['action_taken_claim']
    contract.check(action in candidates, 'chosen action not modeled for this decision')
    # Prioritization is *conditional* only. Confidence is reviewer-provided,
    # not an empirical model reliability or an action-quality judgment.
    gap = max(candidates.values()) - candidates[action]
    contract.check(math.isfinite(gap) and gap >= -1e-6, 'invalid modeled gap')
    start = max(0.0, pts - before)
    end = min(duration, pts + after)
    contract.check(end - start >= 0.5, 'clip interval too short')
    return {
        'schema_version': 1, 'status': 'offline_conditional_ev_clip_not_strategy_verdict',
        'hand_id': decision['hand_id'], 'table_id': decision['table_id'],
        'variant': ev['variant'], 'street': ev['street'],
        'source_summary_sha256': summary_sha, 'source_ev_sha256': ev_sha,
        'source_video_sha256': video_sha,
        'decision_pts_seconds_claim': pts, 'action_taken_claim_unverified': action,
        'reviewer_confidence_claim_not_calibrated': confidence,
        'action_evidence_seen_by_reviewer_not_authenticated': True,
        'clip_start_seconds': start, 'clip_duration_seconds': end - start,
        'conditional_action_ev_chips': candidates,
        'conditional_gap_to_highest_modeled_ev_chips_not_regret': max(0.0, gap),
        'conditional_priority_score_chips_not_strategy_verdict': max(0.0, gap),
        'equity_fraction': equity, 'equity_mc_interval_95_approx': [lo, hi],
        'seed': ev['seed'], 'simulations': ev['simulations'],
        'scenario_assumptions': ev.get('scenario_assumptions'),
        'action_assumptions': ev.get('action_assumptions'),
        'manual_decision_notes': decision['notes'].strip(),
        'automatic_ocr_math_authorization': False,
        'warning': ('All actions, ranges, cards, timestamps and reviewer confidence are unverified claims. '
                    'EV and priority are conditional simplified chip models, not poker errors. '
                    'Monte Carlo intervals exclude range, visual and model uncertainty; raise EV has no interval.')}


def video_duration(path):
    contract.check(path.is_file() and not path.is_symlink() and path.suffix.lower() in ('.mp4', '.webm', '.mov'),
                   'invalid video path/type')
    cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
           'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True)
    return number(float(p.stdout.strip()), 'video duration', 0.5, MAX_VIDEO_SECONDS)


def render(video, manifest, out_dir, clip_id):
    contract.check(type(clip_id) is str and contract.ID.fullmatch(clip_id), 'invalid clip ID')
    contract.check(out_dir.is_dir() and not out_dir.is_symlink(), 'output directory must exist')
    mp4 = out_dir / (clip_id + '.mp4')
    report = out_dir / (clip_id + '.json')
    contract.check(not mp4.exists() and not mp4.is_symlink() and
                   not report.exists() and not report.is_symlink(), 'output already exists')
    text = (f"PLO {manifest['variant']} | {manifest['street']} | Mesa {manifest['table_id']}\n"
            f"Acao declarada: {manifest['action_taken_claim_unverified']} | Equity hipotetica: {manifest['equity_fraction']:.1%}\n"
            f"Diferenca EV modelada: {manifest['conditional_gap_to_highest_modeled_ev_chips_not_regret']:.2f} fichas\n"
            "Hipoteses manuais; nao e veredito. OCR/acao nao verificados.")
    with tempfile.TemporaryDirectory(prefix='plo_clip_', dir=out_dir) as temp:
        tempdir = Path(temp)
        (tempdir / 'overlay.txt').write_text(text, encoding='utf-8')
        temp_mp4 = tempdir / 'clip.mp4'
        cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
               '-ss', f"{manifest['clip_start_seconds']:.6f}", '-i', str(video),
               '-t', f"{manifest['clip_duration_seconds']:.6f}",
               '-map', '0:v:0', '-map', '0:a:0?',
               '-vf', 'drawtext=textfile=overlay.txt:expansion=none:fontcolor=white:fontsize=16:box=1:boxcolor=black@0.75:boxborderw=5:x=10:y=10',
               '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(temp_mp4)]
        subprocess.run(cmd, cwd=tempdir, capture_output=True, text=True, timeout=180, check=True)
        contract.check(temp_mp4.is_file() and temp_mp4.stat().st_size > 0,
                       'ffmpeg did not produce MP4')
        # Detect input mutation after processing; avoid publishing mismatched bytes.
        contract.check(contract.sha256(video) == manifest['source_video_sha256'],
                       'video changed during clip rendering')
        manifest = dict(manifest, clip_filename=mp4.name, overlay_burned_in=True,
                        rendered_clip_sha256=contract.sha256(temp_mp4))
        temp_report = tempdir / 'report.json'
        temp_report.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
                               encoding='utf-8')
        # Fail closed on unexpected output collision.
        contract.check(not mp4.exists() and not report.exists(), 'output appeared during render')
        os.link(temp_mp4, mp4)
        try:
            os.link(temp_report, report)
        except BaseException:
            mp4.unlink(missing_ok=True)
            raise
    return mp4, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('summary_json', 'ev_json', 'decision_json', 'video', 'output_dir', 'clip_id'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    summary, ev, decision, video = map(Path, (args.summary_json, args.ev_json,
                                            args.decision_json, args.video))
    out_dir = Path(args.output_dir)
    contract.check(len({p.resolve() for p in (summary, ev, decision, video)}) == 4,
                   'inputs must be distinct')
    duration = video_duration(video)
    hashes = [contract.sha256(p) for p in (summary, ev, decision, video)]
    plan = validate(contract.read_json(summary), contract.read_json(ev),
                    contract.read_json(decision), hashes[0], hashes[1], hashes[3], duration)
    contract.check(hashes == [contract.sha256(p) for p in (summary, ev, decision, video)],
                   'input changed during planning')
    plan['source_decision_sha256'] = hashes[2]
    mp4, report = render(video, plan, out_dir, args.clip_id)
    print(json.dumps({'status': plan['status'], 'clip': str(mp4), 'report': str(report)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
