import json,tempfile,unittest
from pathlib import Path
from plo5_visual_validation import compare,run,digest

class VisualValidationTests(unittest.TestCase):
    def test_matching(self):
        self.assertEqual(compare(['Ks','Js'],['Ks','Js']),'correct')
        self.assertEqual(compare([],[]),'correct')
        self.assertEqual(compare(None,None),'correct')
    def test_wrong(self):
        self.assertEqual(compare('2.5','25'),'wrong')
        self.assertEqual(compare(['Ks'],['Kh']),'wrong')
    def test_abstention_not_wrong(self):
        self.assertEqual(compare('2.5',None),'abstained')
        self.assertEqual(compare([],None),'abstained')
    def test_false_positive(self):
        self.assertEqual(compare(None,'call'),'false_positive')
    def test_manifest_binding(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);m={'source_sha256':'a'*64,'frames':[]};raw=json.dumps(m).encode();(p/'manifest.json').write_bytes(raw)
            a={'variant':5,'platform':'pppoker','source_sha256':'b'*64,'manifest_sha256':digest(raw)};(p/'a.json').write_text(json.dumps(a))
            with self.assertRaisesRegex(ValueError,'Annotation binding mismatch'):run(p,p/'a.json','unused')
    def test_variant(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);raw=json.dumps({'source_sha256':'a'*64}).encode();(p/'manifest.json').write_bytes(raw)
            (p/'a.json').write_text(json.dumps({'variant':6,'platform':'pppoker','source_sha256':'a'*64,'manifest_sha256':digest(raw)}))
            with self.assertRaisesRegex(ValueError,'Annotation binding mismatch'):run(p,p/'a.json','unused')
if __name__=='__main__':unittest.main()
