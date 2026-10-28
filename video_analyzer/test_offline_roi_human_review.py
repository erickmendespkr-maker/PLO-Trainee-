"""Portable synthetic tests for offline OCR human-review provenance and gating."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import zlib

from offline_roi_human_review import review, normalize, load


def png_bytes():
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class OcrReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ocr = self.root / 'ocr'
        self.ocr.mkdir()
        fields = [('pot', 'POT 125'), ('board', ''), ('action', '')]
        proposals = []
        for index, (field, raw) in enumerate(fields):
            name = f'roi_{index:03d}.png'
            (self.ocr / name).write_bytes(png_bytes())
            proposals.append({'table_id': 1 if index < 2 else 4,
                              'frame_file': f'refine_00{index}_000.jpg',
                              'decoded_source_pts_seconds': float(index + 1),
                              'source_frame_sha256': 'a' * 64, 'field': field,
                              'roi_png': name, 'roi_png_sha256': digest(self.ocr / name),
                              'raw_ocr_text': raw, 'parsed_candidate': None,
                              'status': 'needs_manual_review'})
        self.report = {'schema_version': 1, 'analysis_status': 'offline_refined_roi_ocr_proposals_only',
                       'requires_manual_review': True, 'ready_for_equity_or_ev': False,
                       'hands_reconstructed': False, 'source_sha256': 'b' * 64,
                       'proposals': proposals}
        self.report_path = self.ocr / 'roi_ocr_proposals.json'
        self.save_report()
        self.annotations_path = self.root / 'annotations.json'
        self.annotations = {'schema_version': 1,
                            'source_roi_ocr_report_sha256': digest(self.report_path),
                            'reviews': [self.entry(0, 'confirmed', '125.00'),
                                        self.entry(1, 'inconclusive', None),
                                        self.entry(2, 'corrected', 'fold', 'Observed action icon') ]}
        self.save_annotations()
        self.out = self.root / 'reviewed'

    def entry(self, index, decision, value, note=''):
        return {'proposal_index': index,
                'source_roi_png_sha256': self.report['proposals'][index]['roi_png_sha256'],
                'decision': decision, 'normalized_value': value, 'note': note}

    def save_report(self):
        self.report_path.write_text(json.dumps(self.report), encoding='utf-8')

    def save_annotations(self):
        self.annotations_path.write_text(json.dumps(self.annotations), encoding='utf-8')

    def run_review(self):
        return review(self.ocr, self.annotations_path, self.out)

    def fail_review(self, pattern=None):
        with self.assertRaisesRegex(ValueError, pattern or '.*'):
            self.run_review()
        self.assertFalse(self.out.exists())

    def test_full_review_with_gated_ev(self):
        result = self.run_review()
        self.assertEqual(result['counts'], {'confirmed': 1, 'corrected': 1,
                                            'rejected': 0, 'inconclusive': 1, 'pending': 0})
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['hands_reconstructed'])
        self.assertEqual(result['observations'][0]['normalized_value'], '125.00')
        self.assertEqual(json.loads((self.out / 'reviewed_ocr_observations.json').read_text()), result)
        self.assertEqual(digest(self.report_path), result['source_roi_ocr_report_sha256'])

    def test_pending_proposals_retained(self):
        self.annotations['reviews'] = [self.entry(0, 'confirmed', '125')]
        self.save_annotations()
        result = self.run_review()
        self.assertEqual(result['counts']['pending'], 2)
        self.assertIsNone(result['observations'][1]['normalized_value'])

    def test_empty_review_all_pending(self):
        self.annotations['reviews'] = []
        self.save_annotations()
        self.assertEqual(self.run_review()['counts']['pending'], 3)

    def test_rejected_cannot_contain_value(self):
        self.annotations['reviews'][1] = self.entry(1, 'rejected', 'As')
        self.save_annotations()
        self.fail_review('Unresolved')

    def test_correction_requires_explanation(self):
        self.annotations['reviews'][2]['note'] = ''
        self.save_annotations()
        self.fail_review('explanation')

    def test_confirm_blank_ocr_rejected(self):
        self.annotations['reviews'][1] = self.entry(1, 'confirmed', 'As Kh 2d')
        self.save_annotations()
        self.fail_review('blank OCR')

    def test_wrong_source_report_hash(self):
        self.annotations['source_roi_ocr_report_sha256'] = '0' * 64
        self.save_annotations()
        self.fail_review('provenance')

    def test_wrong_roi_hash(self):
        self.annotations['reviews'][0]['source_roi_png_sha256'] = '0' * 64
        self.save_annotations()
        self.fail_review('hash mismatch')

    def test_tampered_roi_png(self):
        with (self.ocr / 'roi_000.png').open('ab') as f:
            f.write(b'evil')
        self.fail_review('modified')

    def test_symlink_roi_png(self):
        original = self.ocr / 'roi_000.png'
        target = self.root / 'original.png'
        shutil.copyfile(original, target)
        original.unlink()
        original.symlink_to(target)
        self.fail_review('modified')

    def test_report_rejects_unsafe_path(self):
        self.report['proposals'][0]['roi_png'] = '../secret.png'
        self.save_report()
        self.fail_review('identity')

    def test_duplicate_index(self):
        self.annotations['reviews'][2] = self.entry(0, 'confirmed', '125')
        self.save_annotations()
        self.fail_review('duplicate')

    def test_boolean_index(self):
        self.annotations['reviews'][0]['proposal_index'] = True
        self.save_annotations()
        self.fail_review('index')

    def test_duplicate_json_key(self):
        self.annotations_path.write_text('{"schema_version":1,"schema_version":1}')
        self.fail_review('Duplicate')

    def test_nonfinite_json(self):
        self.annotations_path.write_text('{"schema_version":NaN}')
        self.fail_review('Nonfinite')

    def test_existing_output_never_overwritten(self):
        self.out.mkdir()
        (self.out / 'keep').write_text('original')
        with self.assertRaisesRegex(ValueError, 'new and safe'):
            self.run_review()
        self.assertEqual((self.out / 'keep').read_text(), 'original')

    def test_output_cannot_be_inside_evidence(self):
        with self.assertRaisesRegex(ValueError, 'inside OCR'):
            review(self.ocr, self.annotations_path, self.ocr / 'inside')

    def test_unexpected_annotation_fields(self):
        self.annotations['reviews'][0]['new_field'] = 'unknown'
        self.save_annotations()
        self.fail_review('fields')

    def test_numeric_amount_validation(self):
        for value in ('0', '1.5', '125.00'):
            self.assertEqual(normalize('pot', value), value)
        for value in ('-1', '1e9', '1,000', '01', '1.234', ' 5', '9999999999999'):
            with self.assertRaises(ValueError):
                normalize('pot', value)

    def test_cards_and_actions_validation(self):
        self.assertEqual(normalize('hero_cards', 'As Kd Qh Jc Tc'), 'As Kd Qh Jc Tc')
        self.assertEqual(normalize('hero_cards', 'As Kd Qh Jc Tc 9s'), 'As Kd Qh Jc Tc 9s')
        self.assertEqual(normalize('board', 'As Kd Qh'), 'As Kd Qh')
        self.assertEqual(normalize('action', 'all-in'), 'all-in')
        for field, value in [('board', 'As As'), ('hero_cards', 'As Kd'),
                             ('board', 'As Kd Qh Jc Tc 9s'), ('action', 'bet 20')]:
            with self.assertRaises(ValueError):
                normalize(field, value)

    def test_rejected_report_with_ev_ready(self):
        self.report['ready_for_equity_or_ev'] = True
        self.save_report()
        self.fail_review('status')

    def test_invalid_proposal_timestamp(self):
        self.report['proposals'][0]['decoded_source_pts_seconds'] = -1
        self.save_report()
        self.fail_review('identity')

    def test_no_ocr_source_modifications(self):
        before = {p.name: digest(p) for p in self.ocr.iterdir()}
        self.run_review()
        self.assertEqual(before, {p.name: digest(p) for p in self.ocr.iterdir()})


if __name__ == '__main__':
    unittest.main()
