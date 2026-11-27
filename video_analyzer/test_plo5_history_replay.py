import unittest
from plo5_history_replay import reconstruct
from plo5_pre_gto_context import cards

HEADER="PokerStars Hand #1: 5 Card Omaha Pot Limit ($1/$2 USD) - 2026/11/27\nTable 'Example' 6-max Seat #2 is the button\nSeat 2: Hero ($200 in chips)\nSeat 5: Villain ($200 in chips)\nHero: posts small blind $1\nVillain: posts big blind $2\n*** HOLE CARDS ***\nDealt to Hero [As Ks Qh Jd Tc]\n"
FOLD=HEADER+"Hero: folds\nUncalled bet ($1) returned to Villain\nVillain collected $2 from pot\n*** SUMMARY ***\nTotal pot $2 | Rake $0\n"
SHOW=HEADER+"Hero: calls $1\nVillain: checks\n*** FLOP *** [2c 3d 4h]\nVillain: bets $4\nHero: calls $4\n*** TURN *** [2c 3d 4h] [5s]\nVillain: checks\nHero: checks\n*** RIVER *** [2c 3d 4h 5s] [6s]\nVillain: checks\nHero: checks\n*** SHOW DOWN ***\nHero: shows [As Ks Qh Jd Tc]\nVillain: shows [Ah Kh Qs Jc Td]\nHero collected $5.50 from pot\nVillain collected $5.50 from pot\n*** SUMMARY ***\nTotal pot $12 | Rake $1\nBoard [2c 3d 4h 5s 6s]\n"

def run(s):return reconstruct(dict(id='1',hero='Hero',holding=cards('As Ks Qh Jd Tc'.split()),raw=s))

class TextReplayTests(unittest.TestCase):
    def test_fold(self):
        r=run(FOLD);self.assertEqual(r['positions'],{'Hero':'SB','Villain':'BB'});self.assertEqual(r['net_cents'],{'SB':-100,'BB':100});self.assertEqual(r['hero_net_bb'],-.5);self.assertFalse(r['strategy_authorized'])
    def test_showdown_and_rake(self):
        r=run(SHOW);self.assertEqual(r['rake_cents'],100);self.assertEqual(r['net_cents'],{'BB':-50,'SB':-50});self.assertEqual(r['hero_decisions'][1]['pot_odds_gross'],[1,3]);self.assertFalse(r['rebuy_observed'])
    def test_raise_to_and_allin(self):
        s=HEADER.replace('$200 in chips','$4 in chips')+"Hero: raises $2 to $4 and is all-in\nVillain: calls $2 and is all-in\n*** FLOP *** [2c 3d 4h]\n*** TURN *** [2c 3d 4h] [5s]\n*** RIVER *** [2c 3d 4h 5s] [6s]\n*** SHOW DOWN ***\nHero: shows [As Ks Qh Jd Tc]\nVillain: shows [Ah Kh Qs Jc Td]\nHero collected $4 from pot\nVillain collected $4 from pot\n*** SUMMARY ***\nTotal pot $8 | Rake $0\n"
        r=run(s);self.assertEqual(r['events'][0]['amount'],300);self.assertEqual(r['net_cents'],{'SB':0,'BB':0})
    def test_threeway_positions_and_sidepot(self):
        h="PokerStars Hand #1: 5 Card Omaha Pot Limit ($1/$2 USD)\nTable 'Example' 6-max Seat #2 is the button\nSeat 2: Hero ($20 in chips)\nSeat 4: Short ($12 in chips)\nSeat 6: Villain ($20 in chips)\nShort: posts small blind $1\nVillain: posts big blind $2\n*** HOLE CARDS ***\nDealt to Hero [As Ks Qh Jd Tc]\nHero: raises $5 to $7\nShort: raises $5 to $12 and is all-in\nVillain: calls $10\nHero: calls $5\n*** FLOP *** [2c 3d 4h]\nVillain: bets $8 and is all-in\nHero: calls $8 and is all-in\n*** TURN *** [2c 3d 4h] [5s]\n*** RIVER *** [2c 3d 4h 5s] [6s]\n*** SHOW DOWN ***\nHero: shows [As Ks Qh Jd Tc]\nShort: shows [7c 8d 9h Ts Js]\nVillain: shows [Ah Kh Qs Jc Td]\nShort collected $36 from main pot\nHero collected $8 from side pot\nVillain collected $8 from side pot\n*** SUMMARY ***\nTotal pot $52 | Rake $0\n"
        r=run(h);self.assertEqual(r['positions'],{'Short':'SB','Villain':'BB','Hero':'BTN'});self.assertEqual(r['net_cents'],{'SB':2400,'BB':-1200,'BTN':-1200})
    def test_report_integrates_replay(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from plo5_history_intake import report
        with TemporaryDirectory() as d:
            p=Path(d)/'hands.txt';p.write_text(FOLD+'\n'+SHOW.replace('#1','#2').replace('Hero: calls $4','Hero: calls $3'))
            out=Path(d)/'report.html';r=report(p,out);self.assertEqual(r['consistent_text_replays'],1);self.assertIn('Resultado líquido',out.read_text());self.assertIn('Histórico não conciliado',out.read_text())
    def test_reject(self):
        for s in (FOLD.replace('$2 from pot','$3 from pot'),FOLD.replace('returned to Villain','returned to Hero'),SHOW.replace('Villain: shows [Ah Kh Qs Jc Td]\n',''),SHOW.replace('Hero: calls $4','Hero: calls $3'),SHOW.replace('[5s]','[As]',1),SHOW.replace('Hero collected $5.50','Hero collected $7').replace('Villain collected $5.50','Villain collected $4'),FOLD.replace('Hero: folds','Hero: raises $100 to $102')):
            with self.subTest(s=s[-150:]),self.assertRaises(ValueError):run(s)
if __name__=='__main__':unittest.main()
