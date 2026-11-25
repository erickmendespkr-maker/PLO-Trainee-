import copy
import unittest
from plo5_hand_drafts import build_drafts

HERO=['As','Kd','Qh','Jc','Ts']
NEW=['2s','3c','4d','5h','6s']
FLOP=['2c','3d','4h']


def fixture(sequence):
    identity={'job_id':'a'*32,'variant':5,'source_sha256':'b'*64,'manifest_sha256':'c'*64}
    binding={**identity,'reports':{'evidence/ingest/manifest.json':identity['manifest_sha256']}}
    manifest={'source_sha256':identity['source_sha256'],'samples':[]}
    reports=[dict(identity,status=status,equity_ev_authorized=False,hands_reconstructed=False,observations=[]) for status in (
        'unverified_calibrated_card_candidates','unverified_position_and_money_candidates','unverified_action_label_episodes','unverified_table_presence_and_board_reset_candidates')]
    reports[0]['change_hints']=[]; reports[3]['candidates']=[]
    for i,(tid,pts,hero,board,action,visible) in enumerate(sequence):
        f=f'table_{tid:02d}_sample_{i:03d}.jpg'; digest=f'{i:064x}'
        manifest['samples'].append({'file':f,'table_id':tid,'actual_frame_timestamp_seconds':pts,'sha256':digest})
        base={'file':f,'table_id':tid,'pts':pts,'crop_sha256':digest}
        reports[0]['observations'].append(dict(base,hero_cards=hero,board_cards=board))
        reports[1]['observations'].append(dict(base,hero_seat_declared=1,seats=[{'seat':1},{'seat':2}],derived_candidates={'pot_bb':'10'}))
        for seat in (1,2):
            label=action if seat==1 else 'call'
            reports[2]['observations'].append(dict(base,seat=seat,hero_seat_declared=1,reading={'candidate':{'action':label} if label else None},same_frame_context=None))
        reports[3]['observations'].append(dict(base,visible=visible))
    return (binding,manifest,*reports)


class DraftTests(unittest.TestCase):
    def test_fold_and_streets_preserved(self):
        args=fixture([(1,0,HERO,[],None,True),(1,1,HERO,FLOP,'fold',True),(1,2,None,FLOP+['5s'],None,True),(1,3,None,FLOP+['5s','6c'],None,True)])
        r=build_drafts(*args); self.assertEqual(len(r['drafts']),1)
        d=r['drafts'][0]; self.assertEqual(d['hero_seat_candidate'],1)
        self.assertEqual([f['street_candidate'] for f in d['frames']],['board_empty_candidate','flop_candidate','turn_candidate','river_candidate'])
        self.assertEqual([f['after_hero_fold_label'] for f in d['frames']],[False,False,True,True])
        self.assertIsNone(d['hand_id']); self.assertFalse(r['equity_ev_authorized'])

    def test_table_isolation_and_gap(self):
        r=build_drafts(*fixture([(1,0,HERO,[],'fold',True),(2,1,NEW,[],None,True),(1,25,HERO,[],None,True)]))
        self.assertEqual([d['table_id'] for d in r['drafts']],[1,1,2]); self.assertFalse(r['drafts'][1]['frames'][0]['after_hero_fold_label'])

    def test_boundary_and_interior(self):
        args=fixture([(1,0,HERO,[],None,True),(1,1,HERO,FLOP,None,True),(1,2,None,None,None,True),(1,3,NEW,[],None,True)])
        args[-1]['candidates']=[{'table_id':1,'interval_pts':[1,3],'evidence_files':[args[1]['samples'][i]['file'] for i in (1,3)],'hand_boundary_verified':False}]
        r=build_drafts(*args); self.assertEqual([len(d['frames']) for d in r['drafts']],[2,1]);self.assertEqual(len(r['unassigned']),1)

    def test_conflicts_and_missing_frames(self):
        r=build_drafts(*fixture([(1,0,HERO,[],None,True),(1,1,NEW,[],None,True),(1,2,NEW,[],None,False),(1,3,NEW,[],None,True),(1,3,NEW,[],None,True)]))
        self.assertEqual(len(r['drafts']),2);self.assertEqual(len(r['unassigned']),3)

    def test_reject_mismatched_reports_and_seats(self):
        base=fixture([(1,0,HERO,[],None,True)])
        for mutation in ('source','crop','seat','missing','variant','duplicate'):
            args=copy.deepcopy(base)
            if mutation=='source':args[2]['source_sha256']='0'*64
            elif mutation=='crop':args[2]['observations'][0]['crop_sha256']='f'*64
            elif mutation=='seat':args[4]['observations'][0]['hero_seat_declared']=2
            elif mutation=='missing':args[3]['observations'].clear()
            elif mutation=='variant':args[2]['variant']=6
            elif mutation=='duplicate':args[2]['observations'][0]['hero_cards']=['As']*5
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):build_drafts(*args)

    def test_unknown_board_not_fabricated(self):
        r=build_drafts(*fixture([(1,0,HERO,None,None,True)])); d=r['drafts'][0]
        self.assertNotIn('hero_seat_candidate',d); self.assertIsNone(d['frames'][0]['street_candidate'])


    def test_real_mp4_all_four_recognizers(self):
        import json
        import shutil
        import subprocess
        import tempfile
        from pathlib import Path
        from PIL import Image, ImageDraw, ImageFont
        from test_plo5_card_candidates import PROFILE as CP, draw_glyph
        from test_plo5_action_candidates import PROFILE as AP
        from plo5_card_candidates import RANKS, SUITS
        from plo5_hand_drafts import analyze_job
        from local_ingest import ingest_local
        from plo5_ingest_job import run_job
        if not all(shutil.which(x) for x in ('ffmpeg','ffprobe','tesseract')):
            self.skipTest('Media/OCR tools required')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); templates=root/'templates'; templates.mkdir()
            font=ImageFont.truetype('DejaVuSans.ttf',26)
            for kind,labels in [('rank',RANKS),('suit',SUITS)]:
                for label in labels:
                    symbol=dict(c='♣',d='♦',h='♥',s='♠')[label] if kind=='suit' else label
                    draw_glyph(symbol,font).save(templates/f'{kind}_{label}.png')
            image=Image.new('RGB',(640,560),(20,100,40)); draw=ImageDraw.Draw(image)
            for rect,token in zip(CP['tables'][0]['hero'],HERO):
                x,y,w,h=rect; image.paste('white',(x,y,x+w,y+h))
                for kind,label,dy in [('rank',token[0],2),('suit',token[1],34)]:
                    with Image.open(templates/f'{kind}_{label}.png') as g: image.paste(g,(x+2,y+dy))
            action=copy.deepcopy(AP); t=action['tables'][0]
            for rect in [t['pot'],t['blinds']]+[s[k] for s in t['seats'] for k in ('stack','bet','dealer','action')]:
                rect[1]+=330
            fields=[(t['pot'],'10 BB'),(t['blinds'],'0.5/1 BB')]
            for seat,stack,bet,label,marker in zip(t['seats'],('120 BB','70 BB'),('3 BB','1 BB'),('FOLD','CALL'),('D','')):
                fields.extend((seat[k],v) for k,v in [('stack',stack),('bet',bet),('action',label),('dealer',marker)])
            for rect,label in fields:
                x,y,w,h=rect; image.paste('white',(x,y,x+w,y+h)); draw.text((x+8,y+8),label,font=font,fill='black')
            context=copy.deepcopy(action)
            for seat in context['tables'][0]['seats']: del seat['action']
            calibration={'felt_rgb':[20,100,40],'tolerance':35,'board_strip':{'offset_x':0,'offset_y':0,'step_x':48,'width':8,'height':8,'white_min_rgb':200,'min_white_fraction':.8}}
            def save(name,obj):
                p=root/name; p.write_text(json.dumps(obj)); return p
            image.save(root/'frame.png'); video=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(root/'frame.png'),'-t','2','-r','5','-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
            regions=save('regions.json',{'tables':[{'table_id':1,'x':0,'y':0,'width':640,'height':560}]})
            db=root/'jobs.db'; job=ingest_local(video,root/'uploads',db)
            run_job(db,job['job_id'],regions,root/'out',pixel_checks=1)
            report=analyze_job(db,job['job_id'],save('cards.json',CP),templates,save('context.json',context),save('action.json',action),save('cal.json',calibration))
            self.assertEqual(len(report['drafts']),1,report['unassigned'])
            frames=report['drafts'][0]['frames']; self.assertEqual(len(frames),3)
            self.assertTrue(all(f['hero_cards']==HERO and f['context']['pot_bb']=='10' and f['hero_fold_label'] for f in frames),frames)
            self.assertEqual([f['after_hero_fold_label'] for f in frames],[False,True,True])
            self.assertEqual(len(report['template_sha256s']),17)
            self.assertFalse(report['hands_reconstructed'])


if __name__=='__main__':unittest.main()
