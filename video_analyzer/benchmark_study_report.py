"""Synthetic reporting-only benchmark; not whole-session video performance."""
import copy
import json
import time
import tracemalloc
from pathlib import Path
from plo5_study_report import build
from test_plo5_study_report import example,multiway_case
import test_plo5_decision_analysis as fixtures


def benchmark(n=1000):
    if type(n) is not int or not 1<=n<=1000:raise ValueError('Invalid benchmark size')
    t=fixtures.BridgeTests();t.setUp()
    try:p=example(multiway_case(),'multiway',t)
    finally:t.doCleanups()
    b=p['bundle'];r=b['reports'][0];b['reports']=[];b['expected_decisions']=[];p['integrations']=[]
    # Repeat one explicitly synthetic card context to measure cache hits; no range solver included.
    for i in range(n):
        item=copy.deepcopy(r);item['action_file']=f'a{i:04d}.jpg';item['context_file']=f'c{i:04d}.jpg';b['reports'].append(item);b['expected_decisions'].append({'draft_id':item['draft_id'],'action_file':item['action_file']})
    results={}
    for mode in ('quick','deep'):
        tracemalloc.start();start=time.perf_counter();cpu=time.process_time();out=build(p,mode);elapsed=time.perf_counter()-start;cpu=time.process_time()-cpu;_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        results[mode]={'wall_seconds':elapsed,'cpu_seconds':cpu,'python_traced_peak_bytes':peak,'decisions':out['declared_decisions'],'card_cache':out['card_cache'],'solver_reruns':out['solver_reruns'],'json_bytes':len(json.dumps(out,ensure_ascii=False).encode('utf-8'))};assert out['declared_decisions']==n and out['card_cache']['hits']==n-1 and out['card_cache']['misses']==1
    return {'variant':5,'synthetic_fixture':True,'reporting_only':True,'repeated_card_contexts':1,'report_count':n,'results':results,'video_processing_measured':False}

if __name__=='__main__':print(json.dumps(benchmark(),indent=2))
