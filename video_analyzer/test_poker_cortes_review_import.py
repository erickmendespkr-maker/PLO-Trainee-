import tempfile
import unittest
from pathlib import Path
from poker_cortes_review_import import import_report, seconds, write_jsonl

SHA = 'a'*64
HEAD = 'inicio;fim;mesa;status;perda_bb;pote_confirmado;rebuy_visto\n'

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'relatorio_analise.csv'
    def tearDown(self):
        self.tmp.cleanup()
    def load(self, rows, **kwargs):
        self.path.write_text(HEAD+rows, encoding='utf-8')
        return import_report(self.path, video_sha256=SHA, duration_seconds=3600, **kwargs)
    def test_four_tables(self):
        rows=''.join(f'00:00:0{i};00:00:1{i};{i};PERDA;50;SIM;NAO\n' for i in range(1,5))
        result=self.load(rows)
        self.assertEqual(len(result),4)
        self.assertTrue(all(r['confirmed_loss_bb'] is None and not r['verified_by_human'] for r in result))
    def test_source_claim_does_not_confirm(self):
        r=self.load('00:00:01;00:00:11;2;PERDA CONFIRMADA;300;SIM;NAO\n')[0]
        self.assertFalse(r['strategic_analysis_authorized'])
        self.assertEqual(r['ocr_reported_loss_bb'],300)
    def test_rebuy_not_confirmed(self):
        self.assertEqual(self.load('00:00:01;00:00:11;1;GANHO;0;NAO;SIM\n')[0]['review_status'],'UNVERIFIED')
    def test_duplicate(self):
        with self.assertRaisesRegex(ValueError,'duplicado'):
            self.load('00:00:01;00:00:11;1;A;1;;\n'*2)
    def test_invalid_interval(self):
        with self.assertRaises(ValueError):self.load('00:00:11;00:00:01;1;A;1;;\n')
    def test_outside_duration(self):
        with self.assertRaises(ValueError):self.load('00:59:59;01:00:01;1;A;1;;\n')
    def test_invalid_table(self):
        with self.assertRaises(ValueError):self.load('00:00:01;00:00:11;5;A;1;;\n')
    def test_nonfinite(self):
        with self.assertRaises(ValueError):self.load('00:00:01;00:00:11;1;A;NaN;;\n')
    def test_bad_hash(self):
        self.path.write_text(HEAD)
        with self.assertRaises(ValueError):import_report(self.path,video_sha256='wrong',duration_seconds=60)
    def test_export(self):
        data=self.load('00:00:01;00:00:11;1;A;31;;\n')
        dest=Path(self.tmp.name)/'out.jsonl'
        self.assertEqual(write_jsonl(data,dest),1)
        self.assertIn('UNVERIFIED',dest.read_text())
    def test_hh_mm_ss(self):
        self.assertEqual(seconds('01:02:03.250'),3723.25)
    def test_bad_time(self):
        with self.assertRaises(ValueError):seconds('99:99')
    def test_comma_decimal(self):
        self.assertEqual(self.load('00:00:01;00:00:11;1;A;30,5;;\n')[0]['ocr_reported_loss_bb'],30.5)

if __name__=='__main__':unittest.main()
