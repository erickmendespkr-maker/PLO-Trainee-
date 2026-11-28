"""Sample real video ROI input equivalence; no hand or action certification."""
import argparse, collections, io, json, os, subprocess, time
from statistics import median
from PIL import Image, ImageOps
from plo5_visual_continuity import seat_ocr_key

STARTS=(0,378,755,1131)
STACKS={'pppoker':((156,156,222,171),(303,269,370,284),(303,466,370,481),(159,627,218,640),(8,466,75,481),(8,269,75,284)),
        'suprema':((155,108,223,124),(305,218,372,232),(305,437,372,452),(158,598,222,615),(5,437,74,452),(5,218,74,232))}
ACTIONS={'pppoker':((188,90,232,105),(294,202,339,217),(294,399,339,415),(146,560,190,577),(40,399,85,415),(40,202,85,217)),
         'suprema':((168,79,210,94),(320,187,360,203),(320,407,360,423),(168,569,210,585),(20,407,61,423),(20,187,61,203))}

def detect(image,table):
    x=STARTS[table-1]
    def rgb(box):
        pixels=list(image.crop(box).convert('RGB').getdata())
        return tuple(median(c[i] for c in pixels) for i in range(3))
    header=rgb((x+120,5,x+245,22));green=blue=0
    for px,py in ((.25,.43),(.75,.43),(.30,.52),(.70,.52),(.30,.66),(.70,.66),(.5,.45),(.5,.75)):
        u,v=x+round(372*px),round(696*py);r,g,b=rgb((u-3,v-3,u+4,v+4))
        green+=g>=r+25 and g>=b+12 and 60<=g<=190
        blue+=b>=g+10 and g>=r+5 and 30<=b<=145
    if green>=4 and blue<=1 and max(header)<65 and max(header)-min(header)<=15:return 'pppoker'
    if blue>=4 and green<=1 and min(header)>=235:return 'suprema'
    return None

def preprocess(image,platform,field):
    gray=image.convert('L');gray=gray.crop((3,1,gray.width-3,gray.height-2));lo,hi=gray.getextrema()
    if hi-lo<15:return None
    gray=ImageOps.autocontrast(gray)
    if field=='stack' or platform=='suprema':gray=ImageOps.invert(gray)
    gray=gray.resize((gray.width*6,gray.height*6),Image.Resampling.LANCZOS)
    return ImageOps.expand(gray,border=24,fill=255)

def ocr(im,p,f):
    im=preprocess(im,p,f)
    if im is None:return None
    stream=io.BytesIO();im.save(stream,format='PNG')
    return subprocess.run(['tesseract','stdin','stdout','--psm','7' if f=='stack' else '8','tsv'],input=stream.getvalue(),capture_output=True,timeout=15,check=True,env=dict(os.environ,OMP_THREAD_LIMIT='1')).stdout

def run(video):
    framebytes=1504*696*3;old=collections.OrderedDict();new=collections.OrderedDict();counter=collections.Counter();examples=[];seen=set();t0=time.perf_counter()
    for start in (0,920,1450):
        proc=subprocess.Popen(['ffmpeg','-v','error','-ss',str(start),'-i',video,'-t','20','-vf','fps=1','-pix_fmt','rgb24','-f','rawvideo','-'],stdout=subprocess.PIPE)
        while True:
            raw=proc.stdout.read(framebytes)
            if not raw:break
            assert len(raw)==framebytes
            im=Image.frombytes('RGB',(1504,696),raw);counter['frames']+=1
            for t,x in enumerate(STARTS,1):
                p=detect(im,t)
                if not p:continue
                counter[p+'_table_samples']+=1
                for f,boxes in [('stack',STACKS),('action',ACTIONS)]:
                    for a,b,c,d in boxes[p]:
                        patch=im.crop((x+a,b,x+c,d));counter['rois']+=1
                        k0=(p,f,patch.size,patch.tobytes());k1=seat_ocr_key(patch,p,f,effective_gray=True)
                        if k0 in old:counter['legacy_hits']+=1;old.move_to_end(k0)
                        else:counter['legacy_misses']+=1;old[k0]=None
                        if k1 in new:
                            counter['effective_hits']+=1;prev_k,prev_patch=new[k1];new.move_to_end(k1)
                            if prev_k!=k0:
                                counter['distinct_raw_same_effective']+=1
                                q,r=preprocess(prev_patch,p,f),preprocess(patch,p,f)
                                assert (q is None)==(r is None)
                                if q is not None:
                                    assert q.size==r.size and q.tobytes()==r.tobytes()
                                    counter['nonblank_equivalence_checks']+=1
                                    if k1 not in seen and len(examples)<12:examples.append((prev_patch,patch,p,f));seen.add(k1)
                        else:counter['effective_misses']+=1;new[k1]=(k0,patch)
                        while len(old)>1024:old.popitem(last=False)
                        while len(new)>1024:new.popitem(last=False)
        assert proc.wait()==0
    for a,b,p,f in examples:
        assert ocr(a,p,f)==ocr(b,p,f);counter['actual_tsv_parity_pairs']+=1
    counter['legacy_key_bytes_final']=sum(len(k[-1]) for k in old);counter['effective_key_bytes_final']=sum(len(k[-1]) for k in new)
    print(json.dumps(dict(counter,elapsed_seconds=round(time.perf_counter()-t0,3)),indent=2))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('video');run(a.parse_args().video)
