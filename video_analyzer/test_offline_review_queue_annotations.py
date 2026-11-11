import copy
import json
from pathlib import Path
import tempfile
import unittest
import offline_review_queue_annotations as a

class TestAnnotations(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.queue=self.root/'queue.json'
  self.q={'schema_version':1,'analysis_status':'unverified_real_video_review_candidates',
          'source_video_sha256':'a'*64,'source_layout_sha256':'b'*64,'source_probe_sha256':'c'*64,
          'hands_reconstructed':False,'ready_for_equity_or_ev':False,
          'automatic_clip_selection_authorized':False,
          'events':[{'event_index':0,'table_id':1,'between_samples_seconds':[5,15],
                     'hand_boundary_verified':False,'action_or_cards_verified':False,
                     'ready_for_math':False,'status':'needs_human_review',
                     'event_kinds':['pot_ocr_change_unverified']}]}
  self.save()
 def save(self):self.queue.write_text(json.dumps(self.q),'utf-8')
 def draft(self):return a.template(self.q,a.sha(self.queue))
 def complete(self):
  d=self.draft();x=d['annotations'][0]
  x.update(review_status='reviewed_complete',hand_id='hand_1',hand_start_seconds=3,
           hand_end_seconds=17,variant='PLO5',hero_cards=['As','Kd','Qc','Jh','Ts'],
           board_cards=['2c','3d','4h'],hero_action='call',pot_before_action_bb=100,
           to_call_bb=20,review_note='Reviewed source frame and actions')
  return d
 def test_template(self):
  d=self.draft();self.assertEqual(d['annotations'][0]['review_status'],'pending')
  self.assertFalse(d['ready_for_equity_or_ev'])
 def test_complete_still_not_verified(self):
  x=a.validate(self.q,self.complete(),a.sha(self.queue))
  self.assertFalse(x['hands_independently_verified']);self.assertFalse(x['ready_for_equity_or_ev'])
 def test_duplicate_cards(self):
  d=self.complete();d['annotations'][0]['board_cards'][0]='As'
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_invalid_action(self):
  d=self.complete();d['annotations'][0]['hero_action']='all-in now'
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_bad_boundary(self):
  d=self.complete();d['annotations'][0]['hand_start_seconds']=16;d['annotations'][0]['hand_end_seconds']=17
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_no_unapproved_partial_cards(self):
  d=self.draft();d['annotations'][0]['hero_cards']=['As']
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_wrong_sha(self):
  d=self.draft();d['source_queue_sha256']='0'*64
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_promoted_queue(self):
  self.q['ready_for_equity_or_ev']=True
  with self.assertRaises(ValueError):a.template(self.q,'a'*64)
 def test_boolean_money(self):
  d=self.complete();d['annotations'][0]['to_call_bb']=True
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_wrong_table(self):
  d=self.complete();d['annotations'][0]['table_id']=2
  with self.assertRaises(ValueError):a.validate(self.q,d,a.sha(self.queue))
 def test_new_output_and_refuse_overwrite(self):
  out=self.root/'template.json'
  a.run('template',self.queue,None,out)
  with self.assertRaises(ValueError):a.run('template',self.queue,None,out)
 def test_validate_file(self):
  d=self.complete();p=self.root/'filled.json';p.write_text(json.dumps(d))
  out=self.root/'validated.json';a.run('validate',self.queue,p,out)
  self.assertFalse(json.loads(out.read_text())['ready_for_equity_or_ev'])
 def test_real_queue_template(self):
  p=Path('/mnt/data/plo_cycle277_work/real_first_2min_review_queue.json')
  if p.exists():
   q=a.read(p);t=a.template(q,a.sha(p));self.assertEqual(len(t['annotations']),21)

if __name__=='__main__':unittest.main()
