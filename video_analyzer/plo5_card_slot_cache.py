"""Exact ROI cache for the existing offline visual card signature reader."""
from plo5_singleflight import SingleFlight


class SlotCache:
    def __init__(self, layouts, reader, capacity=512):
        self.layouts=layouts; self.reader=reader; self.memo=SingleFlight(capacity)

    def read(self,image,field,i):
        if image.mode!='RGB' or image.size not in self.layouts or field not in ('hero','board') or type(i) is not int or not 0<=i<5:
            raise ValueError('Invalid slot')
        p=self.layouts[image.size];x=p[field+'_x'][i];y=p[field+'_y'];w=p[field+'_w'];rh=p[field+'_rank_h'];sh=p[field+'_suit_h']
        # Includes every pixel read by slot(): rank, suit, background and hue.
        rect=(x+2,y+2,x+w,y+rh+sh)
        key=(image.size,field,i,rect,image.crop(rect).tobytes())
        return self.memo.get(key,lambda:self.reader(image,field,i))

    def stats(self):
        return self.memo.stats()
