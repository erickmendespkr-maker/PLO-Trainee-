"""Joint fail-closed pixel-provenance and OCR-label agreement audit for recorded PLO.

CLI: python offline_joint_pixel_ocr_audit.py VIDEO BUNDLE OCR GOLD NEW_DIRECTORY

Consumes the original *unreviewed* four-table evidence. Does not recognize poker
hands, certify human labels, authorize Monte Carlo/EV or select clips. All files
are created in a new directory only after both independent audits succeed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import offline_region_sample_pixel_audit as pixels
import offline_verified_ocr_benchmark as ocr


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(video_path, bundle_path, ocr_path, gold_path, output_path, *,
        tolerance_seconds=0.5, ffprobe='ffprobe', ffmpeg='ffmpeg'):
    video, bundle, proposals, labels, output = map(
        Path, (video_path, bundle_path, ocr_path, gold_path, output_path))
    require(bundle.is_dir() and not bundle.is_symlink(), 'unsafe bundle directory')
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink(), 'output directory must be new')
    require(not output.resolve().is_relative_to(bundle.resolve()) and
            not bundle.resolve().is_relative_to(output.resolve()),
            'output/bundle directory collision')
    source = bundle / 'region_samples.json'
    inputs = (video, source, proposals, labels)
    require(len({str(p.resolve()) for p in inputs}) == len(inputs) and
            all(p.is_file() and not p.is_symlink() and p.stat().st_size > 0 for p in inputs),
            'unsafe, missing or overlapping input files')
    require(all(not output.resolve().is_relative_to(p.resolve()) for p in inputs),
            'output overlaps input file')
    initial = {str(p.resolve()): digest(p) for p in inputs}
    with tempfile.TemporaryDirectory(prefix='.plo_joint_ocr_', dir=output.parent) as tmp:
        stage = Path(tmp) / 'published'
        stage.mkdir()
        pixel_file = stage / 'pixel_audit.json'
        ocr_file = stage / 'ocr_agreement.json'
        pixel_result = pixels.run(video, bundle, pixel_file,
                                  ffprobe=ffprobe, ffmpeg=ffmpeg)
        ocr_result = ocr.run(video, bundle, proposals, labels, ocr_file,
                             tolerance_seconds=tolerance_seconds, ffprobe=ffprobe)
        video_sha, source_sha = initial[str(video.resolve())], initial[str(source.resolve())]
        require(pixel_result.get('status') == 'offline_region_samples_source_pixels_verified' and
                ocr_result.get('status') == 'offline_ocr_agreement_with_video_and_crop_hashes_verified',
                'unexpected audit status')
        require(pixel_result.get('recording_sha256') == video_sha and
                ocr_result.get('recording_sha256_verified_against_bytes') == video_sha and
                pixel_result.get('region_samples_sha256') == source_sha and
                ocr_result.get('source_region_samples_sha256_verified') == source_sha,
                'audits do not bind the same recording and source manifest')
        require(type(pixel_result.get('table_crops_verified')) is int and
                pixel_result['table_crops_verified'] > 0 and
                pixel_result['table_crops_verified'] == ocr_result.get('source_crop_hashes_verified') and
                pixel_result.get('samples_verified') ==
                pixel_result.get('source_frames_independently_decoded'),
                'audit coverage mismatch')
        for result in (pixel_result, ocr_result):
            require(result.get('ready_for_equity_or_ev') is False and
                    result.get('hands_reconstructed') is False and
                    result.get('automatic_clip_selection_authorized') is False,
                    'unsafe downstream promotion in an audit')
        require(ocr_result.get('real_video_ocr_accuracy_verified') is False and
                ocr_result.get('human_labels_authenticity_verified') is False,
                'OCR accuracy or label authenticity cannot be certified')
        # Re-verify complete bundle and original input hashes before publication.
        meta = ocr.video_metadata(video, ffprobe=ffprobe)
        _, _, evidence_files = ocr.validate_bundle(bundle, video_sha, meta)
        require(all(digest(p) == sha for p, sha in evidence_files) and
                all(digest(p) == sha for p, sha in ((Path(k), v) for k, v in initial.items())),
                'inputs or visual evidence changed during joint audit')
        report = {
            'schema_version': 1,
            'status': 'offline_joint_pixel_ocr_diagnostics_only',
            'recording_sha256': video_sha,
            'source_region_samples_sha256': source_sha,
            'original_ocr_report_sha256': initial[str(proposals.resolve())],
            'human_labels_sha256': initial[str(labels.resolve())],
            'pixel_audit_sha256': digest(pixel_file),
            'ocr_agreement_sha256': digest(ocr_file),
            'source_frames_independently_decoded': pixel_result['source_frames_independently_decoded'],
            'table_crops_verified_by_both_audits': pixel_result['table_crops_verified'],
            'label_agreement_summary': ocr_result.get('summary'),
            'labels_authenticated': False,
            'real_poker_ocr_accuracy_verified': False,
            'hands_reconstructed': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'warning': ('Synthetic or supplied-label agreement is not real OCR accuracy. '
                        'Manual review of cards/actions and hand boundaries remains required.')
        }
        (stage / 'joint_report.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
            encoding='utf-8')
        require(all(digest(p) == sha for p, sha in evidence_files) and
                all(digest(Path(k)) == v for k, v in initial.items()),
                'inputs changed before final publication')
        require(not output.exists() and not output.is_symlink(),
                'output appeared during processing')
        os.rename(stage, output)
    return report


def run_original_chain(video_path, layout_path, tasks_path, labels_path,
                       output_path, sample_times, *, builder=None,
                       scanner=None, auditor=None):
    """Create-only original sampler -> Tesseract -> joint audit pipeline.

    `tasks_path` contains {"schema_version":1,"tasks":[...]} with manually
    selected ROIs; labels are supplied, not authenticated. Diagnostic only.
    """
    import math
    from offline_four_table_ocr_benchmark_bridge import load as strict_load

    video, layout, tasks, labels, output = map(
        Path, (video_path, layout_path, tasks_path, labels_path, output_path))
    inputs = (video, layout, tasks, labels)
    require(all(p.is_file() and not p.is_symlink() and p.stat().st_size > 0
                for p in inputs) and
            len({str(p.resolve()) for p in inputs}) == 4,
            'unsafe or overlapping pipeline inputs')
    require(output.parent.is_dir() and not output.parent.is_symlink() and
            not output.exists() and not output.is_symlink() and
            all(not p.resolve().is_relative_to(output.resolve()) for p in inputs),
            'pipeline output must be a new directory')
    require(type(sample_times) is list and 1 <= len(sample_times) <= 8 and
            all(type(t) in (int, float) and math.isfinite(t) and t >= 0
                for t in sample_times) and
            all(a < b for a, b in zip(sample_times, sample_times[1:])),
            'invalid sample times')
    template = strict_load(tasks)
    require(type(template) is dict and set(template) == {'schema_version', 'tasks'} and
            type(template['schema_version']) is int and template['schema_version'] == 1 and
            type(template['tasks']) is list and 1 <= len(template['tasks']) <= 32,
            'invalid ROI task template')
    seen = set()
    for task in template['tasks']:
        require(type(task) is dict and set(task) ==
                {'table_id', 'sample_index', 'field', 'roi'}, 'invalid ROI task')
        table, index, field, roi = (task[k] for k in
                                    ('table_id', 'sample_index', 'field', 'roi'))
        require(type(table) is int and 1 <= table <= 4 and
                type(index) is int and 0 <= index < len(sample_times) and
                field in {'hero_cards', 'board', 'pot', 'bet', 'stack', 'action'} and
                type(roi) is dict and set(roi) == {'x', 'y', 'width', 'height'} and
                all(type(v) is int for v in roi.values()) and
                min(roi['x'], roi['y']) >= 0 and
                8 <= roi['width'] <= 2048 and 8 <= roi['height'] <= 2048,
                'invalid ROI identity or bounds')
        require((table, index, field) not in seen, 'duplicate ROI task')
        seen.add((table, index, field))
    require(type(strict_load(layout)) is dict and type(strict_load(labels)) is list,
            'invalid layout or labels')
    initial = {str(p.resolve()): digest(p) for p in inputs}
    if builder is None:
        from offline_four_table_sample_review import build as builder
    if scanner is None:
        from offline_four_table_ocr_proposals import scan as scanner
    if auditor is None:
        auditor = run
    with tempfile.TemporaryDirectory(prefix='.plo_original_chain_',
                                     dir=output.parent) as temp:
        stage = Path(temp) / 'published'
        stage.mkdir()
        bundle = stage / 'region_bundle'
        source = builder(video, layout, bundle, sample_times)
        require(type(source) is dict and
                source.get('analysis_status') ==
                'unverified_four_table_region_samples_for_manual_review_only' and
                source.get('recording_sha256') == initial[str(video.resolve())] and
                source.get('ready_for_equity_or_ev') is False and
                source.get('automatic_clip_selection_authorized') is False and
                (bundle / 'region_samples.json').is_file(),
                'sampler returned unsafe or incomplete evidence')
        source_sha = digest(bundle / 'region_samples.json')
        bound_tasks = stage / 'roi_tasks_bound.json'
        bound_tasks.write_text(json.dumps({
            'schema_version': 1, 'source_manifest_sha256': source_sha,
            'tasks': template['tasks']}, ensure_ascii=False, indent=2,
            allow_nan=False) + '\n', encoding='utf-8')
        ocr_file = stage / 'original_ocr.json'
        ocr = scanner(bundle, bound_tasks, ocr_file, recording_path=video)
        require(type(ocr) is dict and
                ocr.get('analysis_status') == 'unverified_four_table_ocr_proposals_only' and
                ocr.get('recording_sha256') == initial[str(video.resolve())] and
                ocr.get('source_region_samples_sha256') == source_sha and
                ocr.get('ready_for_equity_or_ev') is False and
                ocr.get('requires_manual_review') is True and
                ocr.get('automatic_hand_or_action_inference') is False,
                'OCR scanner returned unsafe or unrelated evidence')
        joint_dir = stage / 'joint_audit'
        joint = auditor(video, bundle, ocr_file, labels, joint_dir)
        require(type(joint) is dict and
                joint.get('status') == 'offline_joint_pixel_ocr_diagnostics_only' and
                joint.get('recording_sha256') == initial[str(video.resolve())] and
                joint.get('source_region_samples_sha256') == source_sha and
                joint.get('original_ocr_report_sha256') == digest(ocr_file) and
                joint.get('ready_for_equity_or_ev') is False and
                joint.get('hands_reconstructed') is False and
                joint.get('automatic_clip_selection_authorized') is False and
                all((joint_dir / name).is_file() for name in
                    ('joint_report.json', 'ocr_agreement.json', 'pixel_audit.json')),
                'joint audit failed or promoted unreviewed data')
        report = {
            'schema_version': 1,
            'status': 'offline_original_chain_diagnostics_only',
            'recording_sha256': initial[str(video.resolve())],
            'region_samples_sha256': source_sha,
            'original_ocr_sha256': digest(ocr_file),
            'joint_report_sha256': digest(joint_dir / 'joint_report.json'),
            'tables': len(source.get('regions', [])),
            'samples': len(source.get('samples', [])),
            'ocr_candidates': len(ocr.get('candidates', [])),
            'labels_authenticated': False,
            'real_poker_accuracy_verified': False,
            'hands_reconstructed': False,
            'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
        }
        (stage / 'pipeline_report.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n',
            encoding='utf-8')
        require(all(digest(Path(path)) == sha for path, sha in initial.items()) and
                digest(bundle / 'region_samples.json') == source_sha and
                digest(joint_dir / 'joint_report.json') == report['joint_report_sha256'] and
                not output.exists() and not output.is_symlink(),
                'pipeline inputs changed or output appeared')
        os.rename(stage, output)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('bundle')
    parser.add_argument('original_ocr_report')
    parser.add_argument('human_labels')
    parser.add_argument('new_output_directory')
    parser.add_argument('--tolerance-seconds', type=float, default=0.5)
    args = parser.parse_args(argv)
    result = run(args.recording, args.bundle, args.original_ocr_report,
                 args.human_labels, args.new_output_directory,
                 tolerance_seconds=args.tolerance_seconds)
    print(json.dumps({'status': result['status'],
                      'crops': result['table_crops_verified_by_both_audits'],
                      'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
