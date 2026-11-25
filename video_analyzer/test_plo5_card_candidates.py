import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from PIL import Image, ImageDraw, ImageFont
import plo5_card_candidates as c

PROFILE = {'variant':5,'rank_roi':[2,2,32,32],'suit_roi':[2,34,32,32],
           'tables':[{'table_id':1,'hero':[[i*48,80,44,70] for i in range(5)],
                      'board':[[i*48,0,44,70] for i in range(5)]}]}
REGIONS = [{'table_id':1,'width':240,'height':160}]
HERO = ['As','Kd','Qh','Jc','Ts']
BOARD = ['2c','3d','4h','5s','6c']


def draw_glyph(label, font):
    im=Image.new('RGB',(32,32),'white')
    d=ImageDraw.Draw(im)
    bounds=d.textbbox((0,0),label,font=font)
    d.text(((32-bounds[2]+bounds[0])//2-bounds[0],(32-bounds[3]+bounds[1])//2-bounds[1]),label,font=font,fill='black')
    return im


class CardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp=tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root=Path(tmp.name)
        cls.font=ImageFont.truetype('DejaVuSans.ttf',26)
        for kind,labels in [('rank',c.RANKS),('suit',c.SUITS)]:
            for label in labels:
                symbol=dict(c='♣',d='♦',h='♥',s='♠')[label] if kind=='suit' else label
                draw_glyph(symbol,cls.font).save(cls.root/f'{kind}_{label}.png')
        cls.templates,cls.hashes=c.load_templates(cls.root)

    def image(self,hero=HERO,board=BOARD[:3]):
        im=Image.new('RGB',(240,160),(20,100,40))
        for field,cards in [('hero',hero),('board',board)]:
            for rect,token in zip(PROFILE['tables'][0][field],cards):
                if token is None:
                    continue
                x,y,w,h=rect
                im.paste('white',(x,y,x+w,y+h))
                for kind,label,dy in [('rank',token[0],2),('suit',token[1],34)]:
                    with Image.open(self.root/f'{kind}_{label}.png') as g:
                        im.paste(g,(x+2,y+dy))
        return im

    def scan(self,image):
        rows=[[c.read_card(image,r,PROFILE,self.templates) for r in PROFILE['tables'][0][f]] for f in ('hero','board')]
        return c.summarize(*rows)

    def test_all_rank_suit_templates(self):
        self.assertEqual(len(self.hashes),17)
        for kind,labels in [('rank',c.RANKS),('suit',c.SUITS)]:
            for label in labels:
                with Image.open(self.root/f'{kind}_{label}.png') as im:
                    self.assertEqual(c.match(im,self.templates[kind])['label'],label)

    def test_five_private_and_streets(self):
        c.validate_profile(PROFILE,REGIONS)
        for n in (0,3,4,5):
            result=self.scan(self.image(board=BOARD[:n]))
            self.assertEqual(result['hero_cards'],HERO)
            self.assertEqual(result['board_cards'],BOARD[:n])
            self.assertFalse(result['human_confirmed'])

    def test_duplicate_and_missing_cards(self):
        self.assertTrue(self.scan(self.image(board=['As','3d','4h']))['duplicate_conflict'])
        self.assertIsNone(self.scan(self.image(hero=HERO[:4]))['hero_cards'])
        self.assertIsNone(self.scan(self.image(board=['2c',None,'4h']))['board_cards'])
        self.assertIsNone(self.scan(self.image(board=BOARD[:2]))['board_cards'])

    def test_blank_and_unknown_glyph(self):
        self.assertIsNone(c.match(Image.new('RGB',(32,32),'white'),self.templates['rank'])['label'])
        image=self.image(board=[])
        image.paste('white',(0,0,44,70))
        self.assertIsNone(self.scan(image)['board_cards'])
        # A tie between matching templates must not choose a label.
        with Image.open(self.root/'rank_A.png') as im:
            g=c.glyph(im)
            self.assertIsNone(c.match(im,{'A':g,'K':g})['label'])

    def test_profile_excludes_plo6_and_overlap(self):
        with self.assertRaises(ValueError):
            c.validate_profile(dict(PROFILE,variant=6),REGIONS)
        for table in [dict(PROFILE['tables'][0],hero=PROFILE['tables'][0]['hero']+[[0,0,44,70]]),
                      dict(PROFILE['tables'][0],board=PROFILE['tables'][0]['hero'])]:
            with self.assertRaises(ValueError):
                c.validate_profile(dict(PROFILE,tables=[table]),REGIONS)

    def test_real_mp4_bound_job(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('FFmpeg required')
        from local_ingest import ingest_local
        from plo5_ingest_job import run_job
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            self.image().save(root/'frame.png')
            video=root/'source.mp4'
            subprocess.run(['ffmpeg','-v','error','-loop','1','-i',str(root/'frame.png'),'-t','2','-r','5','-c:v','libx264','-crf','12','-pix_fmt','yuv420p',str(video)],check=True,capture_output=True)
            regions=root/'regions.json';regions.write_text(json.dumps({'tables':[dict(REGIONS[0],x=0,y=0)]}))
            profile=root/'profile.json';profile.write_text(json.dumps(PROFILE))
            db=root/'jobs.db'
            job=ingest_local(video,root/'uploads',db)
            result=run_job(db,job['job_id'],regions,root/'out',pixel_checks=1)
            report=c.analyze_job(db,job['job_id'],profile,self.root)
            self.assertEqual(len(report['observations']),3)
            for row in report['observations']:
                self.assertEqual(row['hero_cards'],HERO)
                self.assertEqual(row['board_cards'],BOARD[:3])
            self.assertFalse(report['cards_verified'])
            self.assertFalse(report['equity_ev_authorized'])
            crop=next((Path(result['result_path']).parent/'evidence/ingest').glob('*.jpg'))
            crop.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'crop mismatch'):
                c.analyze_job(db,job['job_id'],profile,self.root)


class ChangeTests(unittest.TestCase):
    def test_changes_require_repeated_preflop_and_distinct_pts(self):
        def rows(seq,table=1):
            return [dict(table_id=table,pts=i,hero_cards=h,board_cards=b,file=f'{table}_{i}') for i,(h,b) in enumerate(seq)]
        a,b=HERO,BOARD
        positive=rows([(a,[]),(a,[]),(b,[]),(b,[])])
        hints=c.change_hints(positive+rows([(b,[])]*4,2))
        self.assertEqual(len(hints),1)
        self.assertEqual(hints[0]['interval_pts'],[1,2])
        self.assertFalse(hints[0]['hand_boundary_verified'])
        for seq in [[(a,[]),(a,[]),(b,[])],[(a,[]),(a,[]),(b,BOARD[:3]),(b,BOARD[:3])],
                    [(a,[]),(a,[]),(None,[]),(b,[]),(b,[])],[(a,[]),(list(reversed(a)),[]),(a,[]),(a,[])]]:
            self.assertEqual(c.change_hints(rows(seq)),[])
        self.assertEqual(c.change_hints(positive+[dict(positive[-1])]),[])
        positive[-1]['pts']=50
        self.assertEqual(c.change_hints(positive),[])


if __name__=='__main__':
    unittest.main()
