import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_beta_video import Fragments,run,probe,diagnostics,compare_snapshots
from plo5_beta_desktop import command
from plo5_bounded_session import run as scan_session
from test_plo5_snapshot_replay import H,V,B,seed,snap
from plo5_pre_gto_context import need


def frame(t,board,holding=H):
    return dict(pts=str(t),rgb_sha256='a'*64,file=f'f{t}',observations=[dict(table_id=i,field=f,platform='pppoker' if i==1 else None,layout_candidate_active=i==1,value_bb='1' if i==1 else None) for i in range(1,5) for f in ('stack','pot')],cards=[dict(table_id=i,platform='pppoker' if i==1 else None,rank_profile='test' if i==1 else None,hero_cards=holding if i==1 else None,board_cards=board if i==1 else None) for i in range(1,5)])


class FragmentTests(unittest.TestCase):
    def test_four_street_fragment_not_verified(self):
        out=[];tracker=Fragments(out.append)
        for i,board in enumerate(([],B[:3],B[:4],B)):tracker.add(frame(i,board))
        r=tracker.finish();self.assertEqual(r['counts']['all_streets_candidates'],1);self.assertEqual(r['counts']['street_advances'],3);self.assertEqual(r['hands_verified'],0);self.assertEqual(out[0]['board_lengths'],[0,3,4,5]);self.assertFalse(out[0]['hand_verified'])
    def test_split_gaps_unknown_and_skip(self):
        out=[];tracker=Fragments(out.append)
        for f in (frame(0,[]),frame(1,B[:4]),frame(3,B[:4]),frame(4,None),frame(5,B)):tracker.add(f)
        r=tracker.finish();self.assertEqual(r['counts']['fragments'],4);self.assertEqual([x['ended_by'] for x in out],['skipped_street','gap','unknown_cards','session_end']);self.assertEqual(r['counts']['unknown_card_samples'],1)
    def test_snapshot_comparison(self):
        f=frame(0,[]);sd=seed();r=snap(0,3,39,38,'hero_bottom');m=dict(variant=5,source_sha256='b'*64,frames=[f]);a=compare_snapshots(m,sd,[r]);self.assertEqual(a['holding'],{'match':1});self.assertEqual(a['pot'],{'mismatch':1})
        f['cards'][0]['hero_cards']=None;self.assertEqual(compare_snapshots(m,sd,[r])['holding'],{'missing':1})
    def test_gui_command_video_only(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);v=p/'a b.mp4';v.touch();s=p/'session.json';s.touch();out=p/'report';args=command(str(v),str(out),['river','flop']);self.assertIn(str(v),args);self.assertEqual(args[args.index('--streets')+1:args.index('--workers')],['flop','river']);self.assertNotIn('--seconds',args)
            self.assertIn('--session',command(str(v),str(out),['flop'],session=str(s)))
            for kw in ({'session':str(s),'seconds':'10'},{'seconds':'1'},{'workers':4}):
                with self.assertRaises(ValueError):command(str(v),str(out),['flop'],**kw)
            with self.assertRaises(ValueError):command(str(v),str(out),[])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg unavailable')
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name);self.video=self.p/'test.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','5','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(self.video)],check=True,timeout=30)
    def test_one_click_and_resume_no_rescan(self):
        self.assertEqual(probe(self.video),5);out=self.p/'out';r=run(self.video,out,streets=['river'],workers=1);self.assertEqual(r['diagnostics']['counts']['frames'],5);self.assertFalse(r['beta_ready']);self.assertEqual(r['report']['errors'],0);self.assertIn('Não significa ausência de erros',(out/'index.html').read_text());self.assertFalse(r['drivehud_beta'])
        with patch('plo5_beta_video.scan_session') as scan:
            b=run(self.video,self.p/'again',session=out/'recognition'/'session.json');scan.assert_not_called();self.assertEqual(b['diagnostics'],r['diagnostics'])
    def test_tamper_atomic_output(self):
        r=self.p/'recognition';scan_session(self.video,r,0,5,workers=1);(r/'window_00001.json').write_text('{}');out=self.p/'failed'
        with self.assertRaisesRegex(ValueError,'Window hash mismatch'):run(self.video,out,session=r/'session.json')
        self.assertFalse(out.exists())
    def test_annotated_model_integration(self):
        import os
        from plo5_video_stream import scan,digest
        from test_plo5_error_prints import FixtureReader
        self.video.unlink();subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','6','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(self.video)],check=True,timeout=30)
        root=self.p/'recognition';root.mkdir();m=scan(self.video,0,6,reader=FixtureReader());m.update(window_start=0,window_seconds=6,card_bank_sha256={});w=root/'window_00001.json';w.write_text(json.dumps(m));idx=root/'session.json';idx.write_text(json.dumps(dict(version='plo5-windowed-candidates-v1',variant=5,source_sha256=m['source_sha256'],card_bank_sha256={},windows=[dict(file=w.name,start=0,seconds=6,frames=6,sha256=digest(w))],frames=6,missing_sample_seconds=0)))
        sd=seed();sd['initial']={'hero_bottom':4,'top':4};rows=[snap(0,3,3,2,'hero_bottom'),snap(1,4,2,2,'top'),snap(2,4,2,2,None),snap(3,4,2,2,'top',B[:3],True),snap(4,6,2,0,'hero_bottom',B[:3]),snap(5,8,0,0,None,B[:3])]
        model=dict(ranges={'SB':[dict(cards=H,weight=1)],'BB':[dict(cards=V,weight=1)]},rake_bps=0,rake_cap=0,rake_on_fold=False,iterations=1)
        a=self.p/'a.json';a.write_text(json.dumps(dict(version='plo5-annotated-validation-v1',source_sha256=m['source_sha256'],hands=[dict(seed=sd,snapshots=rows,model=model)])))
        out=self.p/'out';r=run(self.video,out,session=idx,annotation=a,streets=['flop'],cache=self.p/'cache.sqlite',native=os.environ.get('PLO5_MULTIWAY_EXE'),rank=os.environ.get('PLO5_RANK_WORKER_EXE'));detail=json.loads((out/'annotated_validation.json').read_text())[0];self.assertEqual(detail['math']['estimates'][0]['estimate']['equity']['runouts'],741);self.assertEqual(r['report']['unresolved'],1);self.assertEqual(r['report']['errors'],0);self.assertFalse(detail['math']['strategy_verified'])
    def test_annotation_source_mismatch(self):
        a=self.p/'a.json';a.write_text(json.dumps(dict(version='plo5-annotated-validation-v1',source_sha256='0'*64,hands=[])));out=self.p/'failed'
        with self.assertRaisesRegex(ValueError,'Annotation source mismatch'):run(self.video,out,annotation=a,workers=1)
        self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
