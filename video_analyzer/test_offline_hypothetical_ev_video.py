"""No private videos; synthetic FFmpeg output and validation tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import offline_hypothetical_ev_video as app

class HypotheticalCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.data={'schema_version':1,'analysis_status':'hypothetical_range_sensitivity_not_video_verified',
          'scenario_id':'example_1','pot_before_call_bb':150,'call_cost_bb':50,
          'break_even_equity':.25,'range_sensitive':True,
          'source_hand_reconstruction_verified':False,'strategic_error_established':False,
          'automatic_clip_selection_authorized':False,
          'range_results':[{'range_id':name,'equity':q,'equity_ci95':[q-.02,q+.02],
                            'ev_call_bb':q*200-50,'ev_call_ci95_bb':[(q-.02)*200-50,(q+.02)*200-50],
                            'conditional_label':label,'iterations':10000,'seed':42}
             for name,q,label in [('wide',.3,'positive_under_interval'),('tight',.2,'negative_under_interval')]]}
        self.source=self.root/'source.json';self.write()
    def write(self):self.source.write_text(json.dumps(self.data),'utf-8')
    def test_end_to_end_mp4_and_sidecar(self):
        result=app.render(self.source,self.root/'card.mp4')
        self.assertTrue((self.root/'card.mp4').stat().st_size>0)
        self.assertEqual(result['mp4_sha256'],app.sha(self.root/'card.mp4'))
        self.assertFalse(result['real_video_clip'])
        self.assertEqual(json.loads((self.root/'card.mp4.json').read_text())['source_report_sha256'],app.sha(self.source))
    def test_no_overwrite(self):
        dst=self.root/'card.mp4';app.render(self.source,dst)
        with self.assertRaises(ValueError):app.render(self.source,dst)
    def test_no_promoted_verification(self):
        self.data['source_hand_reconstruction_verified']=True;self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_no_promoted_error(self):
        self.data['strategic_error_established']=True;self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_no_promoted_selection(self):
        self.data['automatic_clip_selection_authorized']=True;self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_bad_equity_ev(self):
        self.data['range_results'][0]['ev_call_bb']=999;self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_bad_confidence_interval(self):
        self.data['range_results'][0]['equity_ci95']=[.1,.2];self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_bad_label(self):
        self.data['range_results'][0]['conditional_label']='negative_under_interval';self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_duplicate_range(self):
        self.data['range_results'][1]['range_id']='wide';self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_bad_range_sensitive(self):
        self.data['range_sensitive']=False;self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_injection_rejected(self):
        self.data['scenario_id']='x\nTEST';self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_bool_money_rejected(self):
        self.data['pot_before_call_bb']=True;self.write()
        with self.assertRaises(ValueError):app.validate(self.data)
    def test_duplicate_json_keys(self):
        self.source.write_text('{"schema_version":1,"schema_version":1}','utf-8')
        with self.assertRaises(ValueError):app.render(self.source,self.root/'out.mp4')
    def test_render_is_explicitly_hypothetical(self):
        text='\n'.join(app.text_lines(self.data,self.data['range_results']))
        self.assertIn('NAO E ANALISE DE VIDEO',text)
        self.assertIn('SENSIVEL AO RANGE',text)

if __name__=='__main__':unittest.main(verbosity=2)
