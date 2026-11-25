import copy
import unittest
import tempfile
from pathlib import Path
import json
import test_plo5_hand_drafts as fixtures
import test_plo5_session_export as session
from plo5_hand_drafts import build_drafts
from plo5_ground_truth import evaluate, template, score, UNKNOWN, main
from offline_video_ingest_probe import sha256


def fixture():
    h=fixtures.HERO; b=fixtures.FLOP
    args=fixtures.fixture([(1,0,h,[],None,True),(1,1,h,b,'fold',True),(1,2,fixtures.NEW,[],None,True),(2,0,h,[],None,True)])
    binding,manifest=args[:2];d=build_drafts(*args);ann=template(binding,manifest)
    ann.update(dataset_kind='synthetic_fixture',reviewer='fixture',independent_review=True)
    for row in ann['annotations']:
        row['truth']={'visible':True,'hand_id':'new' if row['pts']==2 else 'old','pot_bb':'10'}
    ann['annotations'][0]['truth'].update(hero_cards=h[::-1],board=[],hero_seat=1,hero_action_label=None,position='BTN/SB')
    ann['annotations'][1]['truth'].update(hero_cards=h,board=b,hero_action_label='call',pot_bb='12',decision_action='call')
    return binding,manifest,d,'d'*64,ann


class GroundTruthTests(unittest.TestCase):
    def test_metrics_and_boundaries(self):
        r=evaluate(*fixture());m=r['metrics'];self.assertEqual(r['sampled_frames'],4)
        self.assertEqual(m['hero_cards']['exact_matches'],2);self.assertEqual(m['board']['accuracy_all_annotated'],1)
        self.assertEqual(m['hero_action_label']['fp'],1);self.assertEqual(m['hero_action_label']['fn'],1);self.assertEqual(m['hero_action_label']['abstained'],1)
        self.assertEqual(m['position']['coverage'],0);self.assertEqual(r['money_error_bb']['pot_bb']['mae'],.5)
        self.assertEqual(r['sampled_boundary']['tp'],1);self.assertEqual(r['sampled_boundary']['tn'],1)
        self.assertEqual(r['decision_coverage']['annotated_decision_frames'],1);self.assertFalse(r['real_session_validated'])

    def test_absence_and_abstention(self):
        r=score([(None,None),(None,UNKNOWN),('call',UNKNOWN),('raise','fold'),('call','call')]);self.assertEqual((r['tp'],r['tn'],r['fp'],r['fn'],r['abstained']),(1,1,1,2,2));self.assertEqual(r['accuracy_all_annotated'],.4)
        self.assertIsNone(score([])['precision'])

    def test_unassigned_and_unannotated_no_false_boundary(self):
        args=list(fixture());d=args[2];f=d['drafts'][0]['frames'].pop();d['unassigned'].append(dict(f,table_id=1));r=evaluate(*args)
        self.assertEqual(r['sampled_boundary']['abstained'],2)
        args[4]['annotations'][1]['truth']={};r=evaluate(*args);self.assertEqual(r['sampled_boundary']['annotated'],0)

    def test_identity_and_coverage(self):
        for k in ('job_id','source_sha256','manifest_sha256','variant','reviewer','independent_review'):
            args=list(fixture());args[4][k]='' if k=='reviewer' else 'wrong'
            with self.subTest(k=k),self.assertRaises(ValueError):evaluate(*args)
        args=list(fixture());args[4]['annotations'][0]['crop_sha256']='f'*64
        with self.assertRaises(ValueError):evaluate(*args)
        args=list(fixture());args[4]['annotations'].append(args[4]['annotations'][0])
        with self.assertRaises(ValueError):evaluate(*args)

    def test_invalid_truth_and_missing_drafts(self):
        for k,v in [('hero_cards',['As']*5),('board',None),('position','unknown'),('pot_bb','NaN'),('hero_seat',True),('visible',1)]:
            args=list(fixture());args[4]['annotations'][0]['truth'][k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):evaluate(*args)
        args=list(fixture());args[2]['drafts'].pop()
        with self.assertRaises(ValueError):evaluate(*args)

    def test_all_in_label_and_blank(self):
        args=list(fixture());f=args[2]['drafts'][0]['frames'][0];f['actions'][0]['reading']={'candidate':None,'status':'uniform_blank_candidate'}
        f=args[2]['drafts'][0]['frames'][1];f['actions'][0]['reading']={'candidate':{'action':'all_in'}};args[4]['annotations'][1]['truth']['hero_action_label']='all_in'
        m=evaluate(*args)['metrics']['hero_action_label'];self.assertEqual((m['tn'],m['tp'],m['abstained']),(1,1,0))

    def test_bound_media_cli_and_decision_coverage(self):
        t=session.SessionTests;t.setUpClass();self.addCleanup(t.tearDownClass)
        ann_path=t.root/'annotations.json';main([str(t.db),t.jid,str(ann_path)])
        ann=json.loads(ann_path.read_text());self.assertFalse(ann['independent_review']);ann.update(dataset_kind='synthetic_fixture',reviewer='fixture',independent_review=True)
        for row in ann['annotations']:
            row['truth']={'visible':True}
            if row['file'] in [r['action_file'] for r in t.request['bundle']['reports']]:row['truth']['decision_action']='call'
        ann_path.write_text(json.dumps(ann));bp=t.root/'bundle.json';bp.write_text(json.dumps(t.request['bundle']));out=t.root/'truth_report.json'
        main([str(t.db),t.jid,str(out),'--drafts',str(t.dp),'--annotations',str(ann_path),'--bundle',str(bp)])
        r=json.loads(out.read_text());self.assertEqual(r['decision_coverage']['conditionally_comparable'],2);self.assertEqual(r['annotation_sha256'],sha256(ann_path));self.assertEqual(r['metrics']['visible']['exact_matches'],6);self.assertFalse(r['real_session_validated'])
        with self.assertRaises(ValueError):main([str(t.db),t.jid,str(out)])
        b=copy.deepcopy(t.request['bundle']);b['reports'][0]['action_pts']+=.01
        with self.assertRaises(ValueError):evaluate(t.binding,t.manifest,t.drafts,t.dh,ann,b)


if __name__=='__main__':unittest.main()
