import unittest
from offline_review_priority import build_review_queue, FIELDS


def proposal(hand='h1', invested=30, table=1, start=0):
    return dict(hand_id=hand, hero_invested_bb=invested, table_id=table,
                start_seconds=start, end_seconds=start+20,
                field_confidence={k: 0.95 for k in FIELDS})


class ReviewPriorityTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_review_queue([])['review_queue'], [])

    def test_investment_not_loss(self):
        a, b = proposal('a', 20), proposal('b', 40)
        self.assertEqual(build_review_queue([a, b])['review_queue'][0]['hand_id'], 'b')
        self.assertEqual(build_review_queue([a, b])['ranking_basis'], 'invested_bb_not_loss_or_ev')

    def test_uncertainty_tiebreak(self):
        a, b = proposal('a'), proposal('b')
        b['field_confidence']['actions'] = .2
        q = build_review_queue([a, b])['review_queue']
        self.assertEqual(q[0]['hand_id'], 'b')
        self.assertIn('actions', q[0]['uncertain_fields'])
        self.assertFalse(q[0]['strategy_verified'])

    def test_variable_table_count(self):
        self.assertEqual(len(build_review_queue([proposal('a', table=1), proposal('b', table=4)])['review_queue']), 2)

    def test_limit(self):
        self.assertEqual(len(build_review_queue([proposal('a'), proposal('b')], limit=1)['review_queue']), 1)

    def test_duplicate(self):
        with self.assertRaises(ValueError): build_review_queue([proposal(), proposal()])

    def test_invalid_bb(self):
        for bb in [-1, float('nan'), float('inf'), True]:
            with self.subTest(bb=bb), self.assertRaises(ValueError): build_review_queue([proposal(invested=bb)])

    def test_invalid_interval(self):
        a = proposal(); a['end_seconds'] = a['start_seconds']
        with self.assertRaises(ValueError): build_review_queue([a])

    def test_invalid_confidence(self):
        a = proposal(); a['field_confidence']['pot'] = 1.2
        with self.assertRaises(ValueError): build_review_queue([a])

    def test_missing_confidence(self):
        a = proposal(); del a['field_confidence']['pot']
        with self.assertRaises(ValueError): build_review_queue([a])

    def test_determinism(self):
        a, b = proposal('a'), proposal('b')
        self.assertEqual(build_review_queue([a,b]), build_review_queue([b,a]))


if __name__ == '__main__': unittest.main()
