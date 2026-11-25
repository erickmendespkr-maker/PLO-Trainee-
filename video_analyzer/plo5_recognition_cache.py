"""Bounded exact-pixel OCR reuse for offline PLO5 observations.

No skipped observations, approximate matching, or confirmed hand inference.
"""
from collections import OrderedDict
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from PIL import Image
from plo5_visual_calibration import LAYOUTS, present, read_money
from plo5_financial_observations import read_gold_stack
from plo5_action_candidates import read_action
from plo5_leak_review import need


class ExactReader:
    def __init__(self, capacity=512):
        need(type(capacity) is int and 0<=capacity<=2048,'Invalid cache capacity')
        self.capacity=capacity;self.cache=OrderedDict();self.lock=Lock();self.hits=0;self.misses=0

    def read(self,image,field):
        need(image.mode=='RGB' and image.size in LAYOUTS and field in ('pot','stack','action'),'Invalid recognition region')
        rect=LAYOUTS[image.size][field]
        if field=='stack':
            if image.size==(402,748):rect=(166,642,237,656);reader=read_gold_stack
            else:
                x,y,x2,y2=rect;rect=(x+4,y+2,x2-4,y2-2);reader=lambda im:read_money(im,'stack')
        elif field=='pot':reader=lambda im:read_money(im,'pot')
        else:
            x,y,x2,y2=rect;reader=lambda im:read_action(im,[x,y,x2-x,y2-y],.75)
        # Use bytes, not similarity or even a digest alone, as equality key.
        key=(image.size,field,rect,image.crop(rect).tobytes())
        with self.lock:
            if key in self.cache:
                self.hits+=1;self.cache.move_to_end(key);return deepcopy(self.cache[key])
            self.misses+=1
        result=reader(image)
        if self.capacity:
            with self.lock:
                self.cache[key]=deepcopy(result);self.cache.move_to_end(key)
                while len(self.cache)>self.capacity:self.cache.popitem(last=False)
        return result

    def scan(self,image):
        visible=present(image);result={'visible':visible,'pot':None,'stack':None,'action':None}
        if visible is True:
            for field in ('pot','stack','action'):result[field]=self.read(image,field)
        return result

    def stats(self):
        with self.lock:return {'hits':self.hits,'misses':self.misses,'entries':len(self.cache),'capacity':self.capacity,'key_pixel_bytes':sum(len(k[-1]) for k in self.cache)}


def scan_paths(paths,*,capacity=512,workers=2):
    need(type(paths) is list and 1<=len(paths)<=512 and type(workers) is int and 1<=workers<=3,'Invalid batch')
    reader=ExactReader(capacity)
    def scan(path):
        with Image.open(path) as im:return reader.scan(im.convert('RGB'))
    with ThreadPoolExecutor(max_workers=workers) as pool:rows=list(pool.map(scan,paths))
    return rows,reader.stats()


def run_bound(job,window,output,*,capacity=512,workers=2):
    """Re-read all three fields on bound crops, keeping the full observation roster."""
    from pathlib import Path
    from plo5_financial_observations import bound_window, amount, deltas
    from plo5_ingest_job import read_bound_evidence
    from offline_video_ingest_probe import sha256
    from plo5_session_export import write
    out=Path(output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    r,rh,b,paths=bound_window(job,window);observations=r['observations'];rows,stats=scan_paths([paths[x['file']] for x in observations],capacity=capacity,workers=workers)
    result=[]
    for x,y in zip(observations,rows):
        need(x['visible']==y['visible'],'Visibility differs from bound observation')
        result.append({'file':x['file'],'table_id':x['table_id'],'pts':x['pts'],'crop_sha256':x['sha256'],'visible':y['visible'],'pot_reading':y['pot'],'stack_reading':y['stack'],'action_reading':y['action'],'pot_bb':amount(y['pot']),'stack_bb':amount(y['stack'])})
    indexed={x['file']:x for x in result};changes=[{'segment_id':s['segment_id'],'table_id':s['table_id'],'changes':deltas(s,indexed),'financial_result_bb':None} for s in r['segments']]
    need(read_bound_evidence(job['database'],job['job_id'])==b and sha256(window)==rh and sha256(job['annotations'])==r['annotation_sha256'] and all(sha256(paths[x['file']])==x['crop_sha256'] for x in result),'Inputs changed')
    report={'variant':5,'status':'CACHED_DISPLAY_CANDIDATES_ONLY','job_id':b['job_id'],'source_sha256':b['source_sha256'],'timeline_sha256':rh,'observations':result,'segments':changes,'cache':stats,'samples':len(result),'pot_candidates':sum(x['pot_bb'] is not None for x in result),'stack_candidates':sum(x['stack_bb'] is not None for x in result),'unresolved_changes':sum(len(x['changes']) for x in changes),'financial_result_verified':False,'hands_reconstructed':False,'ev_loss_bb':None,'automatic_clip_selection_authorized':False}
    write(out,report);return report


if __name__=='__main__':
    import argparse
    from plo5_session_export import load
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job');p.add_argument('window');p.add_argument('output');p.add_argument('--capacity',type=int,default=512);p.add_argument('--workers',type=int,default=2);a=p.parse_args();run_bound(load(a.job)[0],a.window,a.output,capacity=a.capacity,workers=a.workers)
