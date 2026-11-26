import copy
import unittest
from pathlib import Path
from plo5_review_pipeline import exact_study_links

class ExactLinksTests(unittest.TestCase):
    def setUp(self):
        self.review={'job_id':'a'*32,'source_sha256':'b'*64}
        self.obs={'table_id':1,'pts':10.1,'sha256':'c'*64}
        self.roster={'window_01/table_01_001.png':(Path('x'),self.obs)}
        self.study={'variant':5,'status':'VISUAL_CONDITIONAL_STUDY_ONLY',**self.review,'video_verified':False,'strategic_error_established':False,'gto_solution':False,'prints':[{**self.obs,'file':'prints/00001.png','source_crop':'old.png','draft_id':'d1','classification':'NO_MATCH'}]}
    def test_exact(self):
        links=exact_study_links(self.review,self.roster,self.study);self.assertEqual(next(iter(links.values()))['anchor'],'print-00001')
    def test_no_link_without_exact_match(self):
        for key,value in [('table_id',2),('pts',10.100001),('sha256','d'*64),('classification','SEM_DECISAO_VINCULADA'),('draft_id',None)]:
            s=copy.deepcopy(self.study);s['prints'][0][key]=value
            self.assertEqual(exact_study_links(self.review,self.roster,s),{})
    def test_duplicate_key(self):
        s=copy.deepcopy(self.study);s['prints'].append({**s['prints'][0],'file':'prints/00002.png'});self.assertEqual(exact_study_links(self.review,self.roster,s),{})
    def test_wrong_source(self):
        self.study['source_sha256']='x'
        with self.assertRaisesRegex(ValueError,'identity'):exact_study_links(self.review,self.roster,self.study)
    def test_unsafe_path(self):
        self.study['prints'][0]['file']='../../bad.png'
        with self.assertRaisesRegex(ValueError,'path'):exact_study_links(self.review,self.roster,self.study)
    def test_absent(self):self.assertEqual(exact_study_links(self.review,self.roster,None),{})

if __name__=='__main__':unittest.main()
