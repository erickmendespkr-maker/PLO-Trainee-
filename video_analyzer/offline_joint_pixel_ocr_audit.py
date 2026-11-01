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
