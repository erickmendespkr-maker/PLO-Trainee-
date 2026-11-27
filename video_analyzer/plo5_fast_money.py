"""Experimental offline persistent money recognition; exact ROI keys, bounded workers.
CLI fallback is the default. Native Tesseract requires local version parity testing.
"""
import ctypes as C
import os
from ctypes.util import find_library
from concurrent.futures import ThreadPoolExecutor
from queue import LifoQueue
from threading import Lock
from PIL import Image, ImageOps
from plo5_mixed_money import STARTS, REGIONS, read, parse
from plo5_visual_codes import LayoutCache, pixels, code
from plo5_singleflight import SingleFlight
from plo5_pre_gto_context import need


def mask(patch, field):
    size, mode, raw = patch
    roi = Image.frombytes(mode, size, raw)
    lo, hi = roi.getextrema()
    if hi-lo < 15:return None
    scale = 6 if field == 'stack' else 5
    im = ImageOps.invert(ImageOps.autocontrast(roi)).resize((roi.width*scale,roi.height*scale),Image.Resampling.LANCZOS)
    return ImageOps.expand(im,border=24 if field=='stack' else 18,fill=255)


def result(tsv,platform,field):
    words=[];scores=[]
    for line in tsv.splitlines():
        columns=line.split('\t',11)
        if len(columns)==12 and columns[0]=='5' and columns[11].strip():
            words.append(columns[11]);scores.append(float(columns[10]))
    raw=' '.join(words);confidence=min(scores)/100 if scores else None
    return dict(value_bb=parse(raw,platform,field) if confidence is not None and confidence>=.65 else None,raw=raw,confidence=confidence)


class NativeOCR:
    def __init__(self,library=None):
        need(os.environ.get('OMP_THREAD_LIMIT')=='1','Set OMP_THREAD_LIMIT=1 before starting Python')
        path=library or find_library('tesseract');need(path is not None,'Native Tesseract unavailable')
        self.lib=C.CDLL(path);p=C.c_void_p;i=C.c_int;s=C.c_char_p
        for name,args,ret in [('TessBaseAPICreate',[],p),('TessBaseAPIInit3',[p,s,s],i),('TessBaseAPISetPageSegMode',[p,i],None),('TessBaseAPISetImage',[p,p,i,i,i,i],None),('TessBaseAPISetSourceResolution',[p,i],None),('TessBaseAPIGetTsvText',[p,i],p),('TessDeleteText',[p],None),('TessBaseAPIClearAdaptiveClassifier',[p],None),('TessBaseAPIClear',[p],None),('TessBaseAPIDelete',[p],None)]:
            f=getattr(self.lib,name);f.argtypes=args;f.restype=ret
        self.api=self.lib.TessBaseAPICreate();need(bool(self.api),'Cannot create OCR engine')
        if self.lib.TessBaseAPIInit3(self.api,None,b'eng')!=0:
            self.close();raise ValueError('Cannot initialize OCR engine')
        self.lib.TessBaseAPISetPageSegMode(self.api,7)
    def read(self,patch,platform,field):
        im=mask(patch,field)
        if im is None:return dict(value_bb=None,raw='',confidence=None)
        buf=C.create_string_buffer(im.tobytes());l=self.lib;a=self.api
        need(bool(a),'OCR engine closed')
        l.TessBaseAPIClearAdaptiveClassifier(a)
        l.TessBaseAPISetImage(a,C.cast(buf,C.c_void_p),im.width,im.height,1,im.width)
        l.TessBaseAPISetSourceResolution(a,70)
        text=None
        try:
            text=l.TessBaseAPIGetTsvText(a,0);need(bool(text),'Native OCR failed')
            return result(C.string_at(text).decode('utf-8'),platform,field)
        finally:
            if text:l.TessDeleteText(text)
            l.TessBaseAPIClear(a)
    def close(self):
        if self.api:self.lib.TessBaseAPIDelete(self.api);self.api=None


class FastMoneyReader:
    """One persistent thread pool, one engine per worker, exact cache shared by slots.
    Single caller; no concurrent scan/close. No cross-backend cache reuse.
    """
    def __init__(self,capacity=512,workers=2,*,backend='cli',library=None):
        need(type(workers) is int and 1<=workers<=3,'Invalid workers');need(backend in ('cli','native'),'Invalid backend')
        self.cache=SingleFlight(capacity);self.layout=LayoutCache(capacity);self.backend=backend;self.closed=False
        self.engines=[];self.available=LifoQueue();self.lock=Lock();self.calls=0
        try:
            if backend=='native':
                for _ in range(workers):
                    e=NativeOCR(library);self.engines.append(e);self.available.put(e)
            self.pool=ThreadPoolExecutor(max_workers=workers)
        except BaseException:
            for e in self.engines:e.close()
            raise
    def scan(self,image):
        need(not self.closed,'Reader closed');platforms=self.layout.scan(image)
        def task(j):
            t,p,f=j
            if p is None:r=dict(value_bb=None,raw='',confidence=None,source='NO_LAYOUT',visual_code=None)
            else:
                x=STARTS[t-1];a,b,c,d=REGIONS[p][f];patch=pixels(image,(x+a,b,x+c,d),'L');profile=p+'-1504x696-money-v1'
                def produce():
                    with self.lock:self.calls+=1
                    if self.backend=='cli':return dict(read(image,t,p,f),source='OCR_FALLBACK')
                    e=self.available.get()
                    try:return dict(e.read(patch,p,f),source='OCR_NATIVE_EXPERIMENTAL')
                    finally:self.available.put(e)
                r=dict(self.cache.get((profile,f,*patch),produce),visual_code=code(profile,f,patch))
            return dict(table_id=t,platform=p,field=f,**r,layout_candidate_active=p is not None,financial_result_verified=False)
        return list(self.pool.map(task,[(t,p,f) for t,p in enumerate(platforms,1) for f in ('stack','pot')]))
    def close(self):
        if self.closed:return
        self.closed=True;self.pool.shutdown(wait=True)
        for e in self.engines:e.close()
    def __enter__(self):return self
    def __exit__(self,*exc):self.close()
