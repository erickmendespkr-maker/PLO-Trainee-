import copy
import json
from pathlib import Path
import tempfile
import unittest

import offline_hand_boundary_benchmark as m

SHA = 'a' * 64


def p(table=1, start=1, end=5, **kwargs):
    return dict(table_id=table, start_seconds=start, end_seconds=end,
                status='needs_manual_review', **kwargs)


def g(table=1, start=1, end=5):
    return dict(table_id=table, start_seconds=start, end_seconds=end)


def proposals(*items):
    return dict(schema_version=1, status='unverified_offline_hand_boundary_proposals',
                ready_for_equity_or_ev=False, recording_sha256=SHA, boundaries=list(items))


def labels(*items):
    return dict(schema_version=1, status='human_annotated_hand_boundaries',
                recording_sha256=SHA, hands=list(items))


class BoundaryBenchmarkTests(unittest.TestCase):
    def score(self, pp, gg, tolerance=0.5):
        return m.evaluate(proposals(*pp), labels(*gg), tolerance_seconds=tolerance)

    def test_perfect_four_tables(self):
        r=self.score([p(t, t, t+2) for t in range(1,5)],
                     [g(t, t, t+2) for t in range(1,5)])
        self.assertEqual((r['summary']['matched'],r['summary']['precision'],
                          r['summary']['recall']), (4,1,1))
        self.assertFalse(r['ready_for_equity_or_ev'])

    def test_jitter_within_tolerance(self):
        r=self.score([p(start=1.4,end=5.3)], [g()])
        self.assertEqual(r['summary']['matched'],1)
        self.assertAlmostEqual(r['matches'][0]['start_error_seconds'],0.4)

    def test_endpoint_outside_tolerance(self):
        self.assertEqual(self.score([p(end=5.6)],[g()])['summary']['matched'],0)

    def test_table_isolation(self):
        r=self.score([p(2)],[g(1)])
        self.assertEqual(r['summary']['false_positive_proposals'],1)
        self.assertEqual(r['summary']['missed_human_hands'],1)

    def test_no_proposals(self):
        r=self.score([],[g()])
        self.assertIsNone(r['summary']['precision'])
        self.assertEqual(r['summary']['recall'],0)

    def test_no_labels(self):
        r=self.score([p()],[])
        self.assertEqual(r['summary']['precision'],0)
        self.assertIsNone(r['summary']['recall'])

    def test_empty_both(self):
        r=self.score([],[])
        self.assertIsNone(r['summary']['f1'])
        self.assertIsNone(r['summary']['recall_wilson95'])

    def test_one_to_one_not_reused(self):
        r=self.score([p(start=1,end=5),p(start=5,end=9)],[g()])
        self.assertEqual((r['summary']['matched'],r['summary']['false_positive_proposals']),(1,1))

    def test_choose_smaller_error(self):
        r=self.score([p(start=1,end=2),p(start=2,end=3)],[g(start=1.9,end=2.9)],tolerance=1)
        self.assertEqual(r['matches'][0]['proposal_index'],1)

    def test_maximize_cardinality_before_error(self):
        r=self.score([p(start=1.0,end=2),p(start=2,end=3)],
                     [g(start=1,end=2),g(start=2,end=3)])
        self.assertEqual(r['summary']['matched'],2)

    def test_out_of_order_input(self):
        r=self.score([p(start=10,end=12),p(start=1,end=3)],
                     [g(start=1,end=3),g(start=10,end=12)])
        self.assertEqual(r['summary']['matched'],2)

    def test_duplicate_candidate(self):
        with self.assertRaises(ValueError): self.score([p(),p()],[g()])

    def test_overlapping_human_hands(self):
        with self.assertRaises(ValueError): self.score([],[g(),g(start=4,end=8)])

    def test_overlapping_proposals_rejected(self):
        with self.assertRaises(ValueError):
            self.score([p(),p(start=4,end=8)],[g()])

    def test_promoted_input_rejected(self):
        x=proposals(p());x['ready_for_equity_or_ev']=True
        with self.assertRaises(ValueError):m.evaluate(x,labels(g()))

    def test_wrong_recording_sha(self):
        x=labels(g());x['recording_sha256']='b'*64
        with self.assertRaises(ValueError):m.evaluate(proposals(p()),x)

    def test_boolean_table_rejected(self):
        with self.assertRaises(ValueError):self.score([p(table=True)],[g()])

    def test_boolean_tolerance_rejected(self):
        with self.assertRaises(ValueError):self.score([p()],[g()],True)

    def test_nan_and_infinity_rejected(self):
        for value in (float('nan'),float('inf'),-1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                self.score([p(start=value)],[g()])

    def test_short_or_reversed_interval_rejected(self):
        for end in (1,0,1.01):
            with self.subTest(end=end),self.assertRaises(ValueError):
                self.score([p(start=1,end=end)],[g()])

    def test_confidence_not_probability(self):
        r=self.score([p(confidence_uncalibrated=0.8,source_sample_indices=[1,2])],[g()])
        self.assertFalse(r['proposal_confidence_calibrated'])
        with self.assertRaises(ValueError):
            self.score([p(confidence_uncalibrated=1.5)],[g()])

    def test_invalid_source_sample_indices(self):
        with self.assertRaises(ValueError):
            self.score([p(source_sample_indices=[0,0])],[g()])

    def test_unknown_fields_rejected(self):
        x=proposals(p());x['boundaries'][0]['hidden_cards']=['As']
        with self.assertRaises(ValueError):m.evaluate(x,labels(g()))

    def test_create_only_report_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a=root/'a.json';b=root/'b.json';out=root/'result.json'
            a.write_text(json.dumps(proposals(p())));b.write_text(json.dumps(labels(g())))
            r=m.run(a,b,out)
            self.assertEqual(r['summary']['matched'],1)
            self.assertEqual(len(r['source_proposals_sha256']),64)
            self.assertEqual(json.loads(out.read_text())['summary']['matched'],1)
            with self.assertRaises(ValueError):m.run(a,b,out)

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'bad.json';f.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):m.load(f)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'original.json';f.write_text('{}')
            link=Path(d)/'link.json';link.symlink_to(f)
            with self.assertRaises(ValueError):m.load(link)

    def test_limit_rows(self):
        with self.assertRaises(ValueError):
            self.score([p(start=i*10,end=i*10+5) for i in range(513)],[])

    def test_invalid_human_label_extra_fields(self):
        x=labels(g());x['hands'][0]['source']='unverified'
        with self.assertRaises(ValueError):m.evaluate(proposals(p()),x)

    def test_wilson_interval(self):
        r=self.score([p()],[g()])
        lo,hi=r['summary']['recall_wilson95']
        self.assertGreater(lo,0)
        self.assertEqual(hi,1)


class RandomizedProperties(unittest.TestCase):
    def test_1000_random_small_cases_against_exhaustive_noncrossing(self):
        import random
        rng = random.Random(265)
        for _ in range(1000):
            def sequence():
                t = rng.uniform(0, 2)
                out = []
                for _ in range(rng.randrange(5)):
                    length = rng.uniform(.1, 3)
                    out.append((t, t + length, len(out)))
                    t += length + rng.uniform(0, 2)
                return out
            pred, gold = sequence(), sequence()
            tol = rng.uniform(.1, 3)
            actual = m._match(pred, gold, tol)
            def exhaustive(i,j):
                if i >= len(pred) or j >= len(gold):
                    return (0,0.0)
                best=max(exhaustive(i+1,j),exhaustive(i,j+1))
                ds=abs(pred[i][0]-gold[j][0]);de=abs(pred[i][1]-gold[j][1])
                if ds <= tol + 1e-9 and de <= tol + 1e-9:
                    k,neg=exhaustive(i+1,j+1)
                    best=max(best,(k+1,neg-ds-de))
                return best
            score=(len(actual),-sum(abs(p[0]-g[0])+abs(p[1]-g[1]) for p,g in actual))
            expected=exhaustive(0,0)
            self.assertEqual(score[0],expected[0])
            self.assertAlmostEqual(score[1],expected[1],places=7)

    def test_1000_random_cases_against_unrestricted_maximum_matching(self):
        import random
        rng = random.Random(2651)
        for _ in range(1000):
            def sequence():
                t = rng.uniform(0, 2)
                out = []
                for i in range(rng.randrange(6)):
                    length = rng.uniform(.1, 3)
                    out.append((t, t+length, i))
                    t += length + rng.uniform(0, 2)
                return out
            pred, gold = sequence(), sequence()
            tolerance = rng.uniform(.1, 5)
            def best(i, used):
                if i == len(pred):
                    return 0
                maximum = best(i+1, used)
                for j, g in enumerate(gold):
                    if j not in used and abs(pred[i][0]-g[0]) <= tolerance and \
                            abs(pred[i][1]-g[1]) <= tolerance:
                        maximum = max(maximum, 1 + best(i+1, used | {j}))
                return maximum
            self.assertEqual(len(m._match(pred,gold,tolerance)),best(0,set()))


if __name__=='__main__': unittest.main()
