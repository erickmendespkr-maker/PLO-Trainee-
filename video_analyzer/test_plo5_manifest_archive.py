import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from plo5_manifest_archive import inspect_archive


BANKS=Path(__file__).resolve().parents[1]/'calibration'


class ManifestArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.video=self.root/'source.mp4';self.video.write_bytes(b'private video fixture')
        self.ppp=BANKS/'ppp_macro18.json';self.suprema=BANKS/'suprema_bank.json'
        self.output=self.root/'restored'
        self.session={'version':'plo5-windowed-candidates-v1','variant':5,
                      'source_sha256':hashlib.sha256(self.video.read_bytes()).hexdigest(),
                      'card_bank_sha256':{'pppoker':hashlib.sha256(self.ppp.read_bytes()).hexdigest(),
                                           'suprema':hashlib.sha256(self.suprema.read_bytes()).hexdigest()},
                      'frames':2,'hands_reconstructed':False,'strategy_authorized':False}
        self.data={'variant':5,'source_sha256':self.session['source_sha256'],
                   'hands_reconstructed':False,'strategy_authorized':False,
                   'frames':[{'pts':'0'}, {'pts':'1/2'}]}

    def pack(self, *, data=None, win_sha=None, extras=None, session_override=None):
        archive=self.root/'session.zip'
        d=self.data if data is None else data
        raw=json.dumps(d).encode()
        session=dict(self.session)
        if session_override:session.update(session_override)
        session['windows']=[dict(file='window_00001.json',start=0,seconds=2,
                                 frames=len(d['frames']),sha256=win_sha or hashlib.sha256(raw).hexdigest())]
        with ZipFile(archive,'w') as z:
            z.writestr('session.json',json.dumps(session))
            z.writestr('window_00001.json',raw)
            for key,value in (extras or {}).items():z.writestr(key,value)
        return archive

    def restore(self, archive):
        return inspect_archive(archive,self.video,self.ppp,self.suprema,self.output)

    def test_valid_archive_restores_only_observations(self):
        a=self.pack();result=self.restore(a)
        self.assertEqual(result['windows'],1)
        self.assertEqual(result['frames'],2)
        self.assertFalse(result['hands_reconstructed'])
        self.assertFalse(result['financial_result_verified'])
        self.assertEqual(set(p.name for p in self.output.iterdir()),{'session.json','window_00001.json'})
        with self.assertRaisesRegex(ValueError,'New local destination'):
            self.restore(a)

    def test_checksum_tampering_fails_atomically(self):
        a=self.pack(win_sha='0'*64)
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):self.restore(a)
        self.assertFalse(self.output.exists())

    def test_source_video_is_bound(self):
        a=self.pack();self.video.write_bytes(b'another source')
        with self.assertRaisesRegex(ValueError,'provenance mismatch'):self.restore(a)
        self.assertFalse(self.output.exists())

    def test_mismatching_valid_bank_rejected(self):
        a=self.pack()
        with self.assertRaisesRegex(ValueError,'provenance mismatch'):
            inspect_archive(a,self.video,BANKS/'ppp_bank.json',self.suprema,self.output)
        self.assertFalse(self.output.exists())

    def test_path_traversal_and_extra_members_rejected(self):
        for extra in ({'../../outside':'bad'},{'window_00002.json':'{}'}):
            with self.subTest(extra=extra):
                a=self.pack(extras=extra)
                with self.assertRaisesRegex(ValueError,'member'):
                    self.restore(a)
                self.assertFalse(self.output.exists())

    def test_out_of_order_pts_rejected(self):
        d=dict(self.data,frames=[{'pts':'1/2'},{'pts':'0'}]);a=self.pack(data=d)
        with self.assertRaisesRegex(ValueError,'timestamp'):
            self.restore(a)
        self.assertFalse(self.output.exists())

    def test_no_false_authorization_flags(self):
        a=self.pack(session_override={'hands_reconstructed':True})
        with self.assertRaisesRegex(ValueError,'provenance mismatch'):self.restore(a)
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
