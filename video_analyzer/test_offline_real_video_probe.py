"""No real user footage in repository tests."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
import offline_real_video_probe as app

class TestRealProbe(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name)
  self.config={'slots':[dict(table_id=i+1,x=i*320,y=0,width=320,height=480) for i in range(4)],
               'felt_rgb':[42,50,86],'tolerance':40}
  self.path=self.root/'config.json';self.write()
 def write(self):self.path.write_text(json.dumps(self.config),encoding='utf-8')
 def test_valid_layout(self):self.assertEqual(len(app.config_read(self.path,(1280,480))['slots']),4)
 def test_overlap_rejected(self):
  self.config['slots'][1]['x']=100;self.write()
  with self.assertRaises(ValueError):app.config_read(self.path,(1280,480))
 def test_duplicate_table_rejected(self):
  self.config['slots'][1]['table_id']=1;self.write()
  with self.assertRaises(ValueError):app.config_read(self.path,(1280,480))
 def test_bool_id_rejected(self):
  self.config['slots'][1]['table_id']=True;self.write()
  with self.assertRaises(ValueError):app.config_read(self.path,(1280,480))
 def test_out_of_bounds_rejected(self):
  self.config['slots'][3]['x']=1000;self.write()
  with self.assertRaises(ValueError):app.config_read(self.path,(1280,480))
 def test_duplicate_json_key_rejected(self):
  self.path.write_text('{"slots":[],"slots":[],"felt_rgb":[1,2,3],"tolerance":40}')
  with self.assertRaises(ValueError):app.config_read(self.path,(1280,480))
 def test_presence_heuristic(self):
  image=Image.new('RGB',(1280,480),(42,50,86));ImageDraw.Draw(image).rectangle((960,0,1279,479),fill=(200,50,50))
  labels=[app.classify(image,s,[42,50,86],40)['proposal'] for s in self.config['slots']]
  self.assertEqual(labels,['likely_visible']*3+['absent_or_uncertain'])
 def test_ocr_never_verified(self):
  raw='level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t80\t12.5\n5\t1\t1\t1\t1\t2\t10\t0\t10\t10\t60\tBB\n'
  with patch.object(app,'cmd',return_value=type('P',(),{'stdout':raw.encode()})()):
   v=app.pot_ocr(Image.new('RGB',(1280,480),'black'),self.config['slots'][0])
  self.assertEqual(v['candidate_bb'],12.5);self.assertEqual(v['status'],'needs_human_review')
 def test_synthetic_video_end_to_end_and_no_overwrite(self):
  d=self.root/'images';d.mkdir()
  for i in range(3):
   im=Image.new('RGB',(1280,480),(42,50,86));ImageDraw.Draw(im).rectangle((960,0,1279,479),fill=(150,70,70));im.save(d/f'frame_{i:03d}.png')
  video=self.root/'clip.mp4'
  p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-framerate','1',
   '-i',str(d/'frame_%03d.png'),'-an','-c:v','mpeg4','-q:v','5',str(video)],capture_output=True,timeout=40)
  self.assertEqual(p.returncode,0,p.stderr)
  output=self.root/'results.json';r=app.analyze(video,self.path,output,[.5,1.5])
  self.assertEqual([sum(t['proposal']=='likely_visible' for t in s['table_proposals']) for s in r['samples']],[3,3])
  self.assertFalse(r['hands_reconstructed']);self.assertFalse(r['equity_ev_authorized'])
  with self.assertRaises(ValueError):app.analyze(video,self.path,output,[.5])
 def test_out_of_order_times_rejected(self):
  with self.assertRaises(ValueError):app.analyze('missing.mp4',self.path,self.root/'out.json',[10,3])

if __name__=='__main__':unittest.main()
