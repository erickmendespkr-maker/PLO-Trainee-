"""Synthetic regression tests for Poker Cortes financial guard."""
import unittest

try:
    from .poker_cortes_financial_guard import review_stack_samples
except ImportError:
    from poker_cortes_financial_guard import review_stack_samples


def s(t, v, independent=True):
    return {'time_seconds': t, 'stack_bb': v, 'source_frame': f'f{t}',
            'independent_read': independent}


class GuardTests(unittest.TestCase):
    def test_large_ocr_bust(self):
        r = review_stack_samples([s(0, 320.5), s(1, .5)])
        self.assertIn('LARGE_STACK_JUMP_RECHECK_OCR', r['flags'])
        self.assertIsNone(r['confirmed_loss_bb'])

    def test_rebuy_not_win(self):
        self.assertIn('STACK_INCREASE_CANNOT_ASSUME_POT_WIN',
                      review_stack_samples([s(0, 10), s(1, 100)])['flags'])

    def test_blind_not_loss(self):
        self.assertFalse(review_stack_samples([s(0, 100), s(1, 99)])['clip_loss_label_authorized'])

    def test_no_independent_read(self):
        self.assertIn('INDEPENDENT_VISUAL_READ_MISSING',
                      review_stack_samples([s(0, 100, False), s(1, 90)])['flags'])

    def test_stable(self):
        self.assertEqual(review_stack_samples([s(0, 100), s(1, 100)])['flags'], [])

    def test_bad_timestamps(self):
        with self.assertRaises(ValueError):
            review_stack_samples([s(1, 100), s(1, 90)])

    def test_nan(self):
        with self.assertRaises(ValueError):
            review_stack_samples([s(0, 100), s(1, float('nan'))])

    def test_bool(self):
        with self.assertRaises(ValueError):
            review_stack_samples([s(0, 100), s(1, True)])

    def test_bad_frame(self):
        x = s(1, 90)
        x['source_frame'] = ''
        with self.assertRaises(ValueError):
            review_stack_samples([s(0, 100), x])

    def test_short(self):
        with self.assertRaises(ValueError):
            review_stack_samples([s(0, 100)])

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            review_stack_samples([s(0, 100), s(1, 90)], max_jump_bb=0)

    def test_normalized_delta(self):
        self.assertEqual(review_stack_samples([s(0, 100), s(1, 80)])['observed_stack_delta_bb'], -20)


if __name__ == '__main__':
    unittest.main()
