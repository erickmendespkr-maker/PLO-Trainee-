"""Input safety and conservative evidence semantics for offline hand timelines."""
import unittest
from video_analyzer.offline_hand_timeline import Observation, propose_intervals


class TimelineInputSafetyTests(unittest.TestCase):
    def test_invalid_duration_rejected(self):
        for duration in (None, '60', True, float('nan'), 0, -1):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                propose_intervals([], duration)

    def test_invalid_observation_fields_rejected(self):
        changes = [
            {'table_id': None}, {'table_id': '  '}, {'table_id': 4},
            {'street': None}, {'street': 'showdown'},
            {'timestamp': None}, {'timestamp': '1'}, {'timestamp': True},
            {'timestamp': float('inf')}, {'timestamp': -1}, {'timestamp': 61},
            {'confidence': None}, {'confidence': '0.9'}, {'confidence': True},
            {'confidence': float('nan')}, {'confidence': 1.1},
            {'board': None}, {'board': ['Ah', 'Kd', '2c']},
            {'board': ('Ah', 'Kd')}, {'board': ('Ah', '', '2c')},
            {'board': ('Ah', None, '2c')},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                propose_intervals([Observation(**{
                    **{'table_id':'1','timestamp':1,'street':'flop','board':('Ah','Kd','2c'),'confidence':.8}, **change})], 60)

    def test_separate_tables_and_uncertainty(self):
        rows = [Observation('2', 1, 'flop', ('Ah','Kd','2c'), .9),
                Observation('1', 1, 'flop', ('Ah','Kd','2c'), .8),
                Observation('2', 3, 'turn', ('Ah','Kd','2c','4s'), .7),
                Observation('1', 4, 'preflop', (), .6)]
        result = propose_intervals(rows, 60)
        self.assertEqual([r['table_id'] for r in result], ['1','2'])
        self.assertEqual([r['reason'] for r in result], ['street_reset','board_change'])
        self.assertEqual([r['confidence_upper_bound'] for r in result], [.6,.7])
        self.assertTrue(all(r['verified_by_human'] is False and r['hand_id'] is None and r['boundary_exact'] is False for r in result))

    def test_duplicate_timestamp_rejected_per_table(self):
        with self.assertRaises(ValueError):
            propose_intervals([Observation('1', 2, 'flop'), Observation('1', 2, 'turn')], 60)
        self.assertEqual(propose_intervals([Observation('1', 2, 'flop'), Observation('2', 2, 'turn')], 60), [])


if __name__ == '__main__':
    unittest.main()
