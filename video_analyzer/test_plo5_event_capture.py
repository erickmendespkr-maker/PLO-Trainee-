import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np
from plo5_event_capture import Tracker,signatures,changed,run,ROIS

class EventCaptureTests(unittest.TestCase):
    def setUp(self):
        self.a=np.zeros((696,372,3),dtype=np.uint8)
        self.b=self.a.copy();x,y,u,v=ROIS['suprema']['board'];self.b[y:v,x:u]=255
    def test_delta(self):
        self.assertIn('board',changed(signatures(self.a,'suprema'),signatures(self.b,'suprema')))
        self.assertEqual(changed(signatures(self.a,'suprema'),signatures(self.a,'suprema')),[])
    def test_stable_capture(self):
        t=Tracker(8);self.assertEqual(t.step(4,'suprema',self.a,0,0)[0][0],'initial_or_gap')
        self.assertEqual(t.step(4,'suprema',self.b,1,1),[])
        e=t.step(4,'suprema',self.b,2,2)[0]
        self.assertEqual(e[0],'stable_change_candidate');self.assertEqual(e[2][0],0);self.assertEqual(e[3][0],1);self.assertIn(e[4][0],(1,2));self.assertIn('board',e[1])
    def test_transient(self):
        t=Tracker(8);t.step(4,'suprema',self.a,0,0);t.step(4,'suprema',self.b,1,1)
        self.assertEqual(t.step(4,'suprema',self.a,2,2),[])
    def test_gap(self):
        t=Tracker(8);t.step(4,'suprema',self.a,0,0);t.step(4,'suprema',self.b,1,1)
        e=t.step(4,'suprema',self.b,2,3)[0];self.assertEqual(e[0],'initial_or_gap');self.assertIsNone(e[2])
    def test_platform(self):
        t=Tracker(8);t.step(4,'suprema',self.a,0,0)
        self.assertEqual(t.step(4,None,self.a,1,1),[])
        self.assertEqual(t.step(4,'pppoker',self.b,2,2)[0][0],'initial_or_gap')
    def test_timeout(self):
        t=Tracker(2);t.step(4,'suprema',self.a,0,0);t.step(4,'suprema',self.b,1,1)
        c=self.b.copy();c[236:318,60:320]=100;t.step(4,'suprema',c,2,2)
        self.assertEqual(t.step(4,'suprema',self.b,3,3)[0][0],'unstable_change_candidate')
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);src=p/'a.mp4';src.write_bytes(b'a');out=p/'existing';out.mkdir()
            with self.assertRaisesRegex(ValueError,'New output'):run(src,out)
    def test_invalid_window(self):
        with self.assertRaises(ValueError):run('a','b',seconds=61)
if __name__=='__main__':unittest.main()
