import unittest
from copy import deepcopy
from fractions import Fraction
from plo5_observation_checkpoints import defer_checkpoint


def cp(t, **kw):
    return dict(pts=str(t), remaining=kw.get('remaining', {'SB':95, 'BB':90}),
                pot=kw.get('pot',15), active=kw.get('active',['BB']), actor=kw.get('actor'))


class CheckpointsTests(unittest.TestCase):
    def test_duplicate_frames_do_not_exhaust_six_slots(self):
        pending=[]
        self.assertEqual(defer_checkpoint(pending,cp(0)), 'ADDED')
        for i in range(1,40):
            self.assertEqual(defer_checkpoint(pending,cp(Fraction(i,10))), 'DUPLICATE')
        self.assertEqual(len(pending),1)
        self.assertEqual(pending[0]['pts'],'0')

    def test_timeout_even_when_screen_state_unchanged(self):
        pending=[]
        self.assertEqual(defer_checkpoint(pending,cp(0)), 'ADDED')
        self.assertEqual(defer_checkpoint(pending,cp(5)), 'TIMEOUT')
        self.assertEqual(len(pending),1)

    def test_distinct_values_are_kept(self):
        for field, val in [('remaining',{'SB':90,'BB':90}), ('pot', 25),
                           ('active', ['SB','BB']), ('actor', 'BB')]:
            pending=[cp(0)]
            changed=cp(1, **{field:val})
            self.assertEqual(defer_checkpoint(pending,changed),'ADDED')
            self.assertEqual(len(pending),2)

    def test_budget_does_not_mutate(self):
        pending=[]
        for i in range(6):
            self.assertEqual(defer_checkpoint(pending,cp(Fraction(i,10),pot=i)), 'ADDED')
        saved=deepcopy(pending)
        self.assertEqual(defer_checkpoint(pending,cp(Fraction(6,10),pot=6)), 'LIMIT')
        self.assertEqual(pending,saved)

    def test_duplicate_with_full_budget_is_safe(self):
        pending=[]
        for i in range(6):
            defer_checkpoint(pending,cp(Fraction(i,10),pot=i))
        self.assertEqual(defer_checkpoint(pending,cp(Fraction(6,10),pot=5)), 'DUPLICATE')
        self.assertEqual(len(pending),6)

    def test_reject_reverse_time_and_bad_budgets(self):
        pending=[cp(1)]
        for timestamp in (0,1):
            with self.assertRaisesRegex(ValueError,'PTS must increase'):
                defer_checkpoint(pending,cp(timestamp))
        with self.assertRaisesRegex(ValueError,'time budget'):
            defer_checkpoint([],cp(1),max_span=0)
        with self.assertRaisesRegex(ValueError,'checkpoint budget'):
            defer_checkpoint([],cp(1),max_count=7)

    def test_fractional_pts(self):
        pending=[]
        self.assertEqual(defer_checkpoint(pending,cp('1/3'),max_span=Fraction(2,3)), 'ADDED')
        self.assertEqual(defer_checkpoint(pending,cp('2/3'),max_span=Fraction(2,3)), 'DUPLICATE')
        self.assertEqual(defer_checkpoint(pending,cp('4/3'),max_span=Fraction(2,3)), 'TIMEOUT')


if __name__ == '__main__':
    unittest.main()
