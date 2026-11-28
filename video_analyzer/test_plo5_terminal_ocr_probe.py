"""No OCR shortcut can certify a PLO5 settlement."""
import unittest
from plo5_terminal_ocr_probe import fold_text_candidate, probe


class TerminalOCRProbeTests(unittest.TestCase):
    def test_unambiguous_fold_words_only(self):
        for raw in ('fold,', 'âfolds', 'FOLDED', ' fold '):
            with self.subTest(raw=raw):
                self.assertTrue(fold_text_candidate(raw, 0.40))

    def test_uncertain_or_unrelated_is_not_evidence(self):
        for raw, confidence in (('fold', 0.20), ('unfold', 0.95),
                                ('folding', 0.85), ('check', 0.98),
                                ('', 0.8), ('fold', None)):
            with self.subTest(raw=raw, conf=confidence):
                self.assertFalse(fold_text_candidate(raw, confidence))

    def test_invalid_budget_rejected_before_video_open(self):
        with self.assertRaisesRegex(ValueError, 'table/seat'):
            probe('missing.mp4', 5, 'top', 0, 1)
        with self.assertRaisesRegex(ValueError, 'sample budget'):
            probe('missing.mp4', 1, 'top', 0, 1, fps=20)
        with self.assertRaisesRegex(ValueError, 'Local MP4'):
            probe('missing.mp4', 1, 'top', 0, 1)


if __name__ == '__main__':
    unittest.main()
