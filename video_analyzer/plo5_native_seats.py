"""Experimental persistent Tesseract seat OCR, retaining legacy ROI preprocessing.
Opt-in only; validate parity against the local CLI and traineddata before use.
"""
import ctypes as C
from queue import LifoQueue
from PIL import Image, ImageOps
from plo5_fast_money import NativeOCR
from plo5_seat_evidence import LABELS, parse
from plo5_pre_gto_context import need


def preprocess(image,platform,field):
    gray=image.convert('L');gray=gray.crop((3,1,gray.width-3,gray.height-2));lo,hi=gray.getextrema()
    if hi-lo<15:return None
    gray=ImageOps.autocontrast(gray)
    if field=='stack' or platform=='suprema':gray=ImageOps.invert(gray)
    gray=gray.resize((gray.width*6,gray.height*6),Image.Resampling.LANCZOS)
    return ImageOps.expand(gray,border=24,fill=255)


def result(tsv,platform,field):
    words=[];conf=[]
    for line in tsv.splitlines():
        cols=line.split('\t',11)
        if len(cols)==12 and cols[0]=='5' and cols[11].strip():words.append(cols[11]);conf.append(float(cols[10])/100)
    raw=' '.join(words);confidence=min(conf) if conf else None;candidate=None
    if confidence is not None and confidence>=.75:candidate=parse(raw,platform,'stack') if field=='stack' else LABELS.get(raw.strip().lower())
    return dict(raw=raw,confidence=confidence,candidate=candidate)


class NativeSeatOCR(NativeOCR):
    def decode(self,image,platform,field):
        im=preprocess(image,platform,field)
        if im is None:return dict(raw='',confidence=None,candidate=None)
        buf=C.create_string_buffer(im.tobytes());l=self.lib;a=self.api;need(bool(a),'OCR engine closed')
        l.TessBaseAPIClearAdaptiveClassifier(a);l.TessBaseAPISetPageSegMode(a,7 if field=='stack' else 8)
        l.TessBaseAPISetImage(a,C.cast(buf,C.c_void_p),im.width,im.height,1,im.width);l.TessBaseAPISetSourceResolution(a,70);text=None
        try:
            text=l.TessBaseAPIGetTsvText(a,0);need(bool(text),'Native OCR failed');return result(C.string_at(text).decode('utf-8'),platform,field)
        finally:
            if text:l.TessDeleteText(text)
            l.TessBaseAPIClear(a)


class NativeSeatPool:
    exact_gray_roi = True  # Same grayscale crop as the built-in CLI decoder.
    def __init__(self,workers):
        need(type(workers) is int and 1<=workers<=3,'Invalid workers');self.engines=[];self.available=LifoQueue()
        try:
            for _ in range(workers):
                e=NativeSeatOCR();self.engines.append(e);self.available.put(e)
        except BaseException:self.close();raise
    def __call__(self,image,platform,field):
        e=self.available.get()
        try:return e.decode(image,platform,field)
        finally:self.available.put(e)
    def close(self):
        for e in self.engines:e.close()
        self.engines=[]
