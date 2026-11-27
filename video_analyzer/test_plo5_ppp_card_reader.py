import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from plo5_ppp_card_reader import PPPCardReader
from plo5_fourcolor_cards import RANKS

class PPPReaderTests(unittest.TestCase):
    def test_absent_tables_and_bank_validation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bank.json';p.write_text(json.dumps({r:[['00'*480,1.,'hero']] for r in RANKS}))
            reader=PPPCardReader(p);rows=reader.scan(Image.new('RGB',(1504,696)))
            self.assertEqual([r['table_id'] for r in rows],[1,2,3,4]);self.assertTrue(all(r['hero_cards'] is None and not r['cards_verified'] for r in rows))
            p.write_text('{}')
            with self.assertRaises(ValueError):PPPCardReader(p)
if __name__=='__main__':unittest.main()
