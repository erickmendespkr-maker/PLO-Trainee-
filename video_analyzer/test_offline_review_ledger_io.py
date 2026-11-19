import tempfile
import unittest
from pathlib import Path
from offline_review_ledger_io import validate_ledger, save_ledger, load_ledger

def fixture():
    sha = 'a' * 64
    return dict(schema_version=1, video_sha256=sha, duration_seconds=60, confirmed_hands=0, strategy_verified=False,
                entries=[dict(proposal_id='id1', video_sha256=sha, table_id=2, start_observed_seconds=1,
                              end_observed_seconds=3, review_status='pending_human_review', hand_verified=False,
                              clip_export_allowed=False, loss_bb=None, equity=None, ev=None)])

class LedgerIOTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'ledger.json'
            save_ledger(fixture(), p)
            self.assertEqual(load_ledger(p), fixture())
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'ledger.json'
            save_ledger(fixture(), p)
            with self.assertRaises(FileExistsError): save_ledger(fixture(), p)
    def test_duplicate(self):
        v = fixture(); v['entries'].append(dict(v['entries'][0]))
        with self.assertRaises(ValueError): validate_ledger(v)
    def test_promoted(self):
        for field, value in [('hand_verified', True), ('clip_export_allowed', True), ('loss_bb', 40), ('equity', 0.6), ('ev', 5)]:
            with self.subTest(field=field):
                v = fixture(); v['entries'][0][field] = value
                with self.assertRaises(ValueError): validate_ledger(v)
    def test_provenance(self):
        v = fixture(); v['entries'][0]['video_sha256'] = 'b' * 64
        with self.assertRaises(ValueError): validate_ledger(v)
    def test_timestamps(self):
        for a,b in [(4,2), (1,61), (float('nan'),3)]:
            with self.subTest(a=a,b=b):
                v=fixture(); v['entries'][0].update(start_observed_seconds=a,end_observed_seconds=b)
                with self.assertRaises(ValueError): validate_ledger(v)
    def test_invalid_table(self):
        v=fixture(); v['entries'][0]['table_id']=5
        with self.assertRaises(ValueError): validate_ledger(v)
    def test_empty(self):
        v=fixture(); v['entries']=[]
        self.assertTrue(validate_ledger(v))
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ledger.json'; p.symlink_to(Path(d)/'target')
            with self.assertRaises(FileExistsError): save_ledger(fixture(),p)
    def test_invalid_strategy(self):
        v=fixture(); v['strategy_verified']=True
        with self.assertRaises(ValueError): validate_ledger(v)

if __name__ == '__main__': unittest.main()
