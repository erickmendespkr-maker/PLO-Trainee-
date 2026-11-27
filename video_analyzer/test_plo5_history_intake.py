import tempfile
import unittest
from pathlib import Path
from plo5_history_intake import intake,report

HAND='PokerStars Hand #1: 5 Card Omaha Pot Limit ($1/$2 USD)\nDealt to Hero <x> [As Kd Qh Jc Ts]\n*** SUMMARY ***\nTotal pot $3 | Rake $0\n'
class HistoryTests(unittest.TestCase):
    def test_supported_and_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'h.txt';p.write_text(HAND+'\n'+HAND+HAND.replace('#1','#2').replace(' Ts] ','] ').replace(' Ts]',']'))
            r=intake(p);self.assertEqual(len(r['hands']),1);self.assertEqual(len(r['rejected']),2);self.assertFalse(r['strategy_authorized'])
            out=Path(t)/'r.html';report(p,out);self.assertIn('Hero &lt;x&gt;',out.read_text());self.assertNotIn('Hero <x>',out.read_text())
    def test_unsupported(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'h.txt';p.write_text('<xml/>')
            with self.assertRaises(ValueError):intake(p)
if __name__=='__main__':unittest.main()
