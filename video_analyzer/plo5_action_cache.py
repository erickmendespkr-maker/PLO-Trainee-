"""Exact action-label ROI reuse for existing offline read_action decoders."""
from hashlib import sha256
from math import isfinite
from plo5_visual_codes import pixels,code,need
from plo5_singleflight import SingleFlight


class ActionCache:
    """The decoder must only consume the specified ROI, as read_action does.
    Always rebind coordinates to the current observation, not cached location.
    """
    def __init__(self,reader,capacity=512):
        self.reader=reader;self.memo=SingleFlight(capacity)
    def read(self,image,rect,threshold):
        need(image.mode=='RGB' and type(rect) in (list,tuple) and len(rect)==4 and all(type(x) is int for x in rect),'Invalid action ROI')
        need(type(threshold) in (int,float) and isfinite(threshold) and 0<=threshold<=1,'Invalid threshold')
        x,y,w,h=rect;patch=pixels(image,(x,y,x+w,y+h))
        # Include threshold, geometry and exact RGB; read_action does not inspect outside ROI.
        key=('action-ocr-v1',threshold,patch[0],patch[2])
        result=self.memo.get(key,lambda:self.reader(image,list(rect),threshold))
        need(result['roi_rgb_sha256']==sha256(patch[2]).hexdigest(),'Action decoder pixel mismatch')
        return dict(result,roi=list(rect),visual_code=code('action-ocr-v1','action',patch),human_confirmed=False)
    def stats(self):return self.memo.stats()
