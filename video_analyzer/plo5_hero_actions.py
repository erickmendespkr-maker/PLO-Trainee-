"""Offline visible Hero action-label candidates, not reconstructed actions."""
import base64,zlib
import cv2
import numpy as np
from plo5_mixed_money import STARTS,detect

BOXES={'pppoker':(149,562,188,572),'suprema':(173,572,205,582)}
TEMPLATES={'pppoker': {'fold': 'eJx1zFlugzAQgOGLsBiJpCgtoSyxbCZTA3a8kfufp6bCpC/5nmb0a2ZdvQvWwL/xV6y3wbbaN56rNVrrY+9uPXVP45ytjNN4cZH3Sim9e+TX5tvYRxhLr+VUHsUYKeWykxmqRfVVxSeihvKSz4uMQp52c/r51Qwnfj2LDIuWJTjFDwu+yKxru7pGSpZUJPcxm4NJiO3F/QUIB6w/oCFjgunAUiFgO/8JAGCMcgbjUJ5IyxM8F0XBEf9VfqA3EJRRShlnjPfAIJZfXRNd8Q==', 'bet': 'eJxdzE1LwzAAxvEvpTAYdqgHqR6muLuyHYqHgl5lMhC8evDiSYVBV5Im1aYvtrGhaVbSbOJ3MhtjhP2Ofx4etTAsd6zj71JJpVqD2iG1v6ZRi5bPDePxw1TOdWpkI1opGk1IoUNVGw7c0WEtOGOVe8sFr7hWV3Up+I+pmwQdBq7O71h/8FRSXShljDJRFqb9C9uhN87rST5y3vSkKPKcFlnyXUTpVpZ1X56ttH9qH5OhQ5IkX+coTtI4jLYI6UzfrfDS/Zh8Xg9JGOFVDVEYhzHEGwhhvNezBujx6MzGbu8ef+mGkP5BBPtwAwAIvdnMh17gzYAPAwCDVfcAAD74B+VWBw0=', 'all_in': 'eJx9yNtLwmAYBvA/KqnAIsGsLAgvMgTrxg5EB0UKNSkEyQ4GUURXgTdhdBEUtk33reV0S93Wvp2+nXD+L8266K4fPDzv+wxcdzBw/+G4br/vWLbtOPaPYf/mb/Eup287tmZZpmkY12eGYZyopnV7blk2Qnb52jx9cV5LBjR0WzdV3YO05flPhCJfinqVgBpCSM3nlNFN9BRSNUNXVR1CKElyNRi9g3BBkOXLFahIUBYzWd4XvnkMKFCSFUUWh7rZvcKW0FvkeL4U50VeFruZA3HkIlKZ6ImiwAs8OwRmjvL+585cm20XYxzHJdaKyVRnvLq672/3GLbFcsxQObybWjpuzmJ4rRDFcOKjxeyk276H+zE/06SZDt0CAFDUxjagszEwGQrFc/7g9DoFQDL9PlUBh4EmRdMUTdZJD4aTOCAIHH9r4IT3Yg1ANMgaSXgDwElA1r8BIUoOzw==', 'pot': 'eJw9yj1Lw0AYB/BvJS46KlohIRSHisVBHAQdOkmDb4gKgmvBwaUEklzezCWWNsmZXO6SS6sfyufS0N/wvP2fpVg1YAlkXYFfIPsfaGeZ1Y0A8rWuheBA7lW17vLORcMZY1UHfvTbpymva15xwRhltOGtqqKUlh1aFNr1+eGU5lmWv54WhOY5bZXlDyFZJy2K/oKoj58DdZQOehdZSkgKZEaydNFJkkR5edh6P76a7N3r2iTO5skcyCyKcAy+QRzN9k+Gd9Hu22x4qatYXuN4nYZfQQh84AXBUeQ7wcE46I/Gmh+GGIctjB2EHOBJvq+4yHNvdnrKx/P2mbPhurZtI2AB03Qs0zYd27BMwzSQvYHQP5uJCKM=', 'check': 'eJw1yulOwkAUBeCXckHUashIS0ygxg2UWBHQRIIYY5oYlzKl2gIpBVK60OnMtPKgzgB+P27uuedSukjXfhlKk+Q/U8oTpSlNFynBMbM6JQnGhNA1jHnCSwQt34jfrnVQfOLjGMcER+yK0EUTIULjiInDKGSCWkGRlEjywtAP5xhFwTxAZ/dBEK56z/VmzDTz5T2WXCCBjt/MFeConJP7xdqTrPozj3En0wkz3rVctmZfKiV1U60U6+J7QTmuZlqO6/DesUc242zpjvZq5WwF3G7sHIKSPNSguC0Ox6MlezAcMP29llnOWwdGFTSyb+rzpWRcn4tXwl1/YHHmt2kwvXpWEBo/R/pN8TMv7J92ABBacvUh0zZMrqf3INfVuhCyoLGh67D7oWsQ8k7TuT8sgMXK', 'call': 'eJxNi01LAzEURX+Rm2KLWBXEYq2tunCjpVK7UERRNy4EdVPK5GOYyUeTTGIyyTD+UTNtEQ/vwX3c88pQ+xCC/0fYUJX+x1UulnXpfOlWlH9auUF7W1Xeu2C8i2cjGROTFc/T9yLm2j2euaGqbXDWOB+ssdaaBteE0Why8Gqb425od+O/1dZo921tURRqtUpqvTPXs3NxfXiB7gfFtlGycIpIpXUhpRRyjRL7nDP+dDLvzW6HattIrgrNo5NrxpuKU8YYpR1Gvz4+B932eNonLUEFo5xyvhQi1oxQGocRtvWWX55OjlF/enOUtWhKckpITpaUpmswThHMJp3u3stDq9u7GvfTdoYwziGgGcwTCAFAEEKEcAIWECwABEmCMQYggQmMHkYIwF8yVdFN'}, 'suprema': {'fold': 'eJxdzL1KA0EUBeCXsxAU4szk3DsGdkHBn7DaaHwAC0kRSRPYbk3QztZOESLYiYKd0ezqC4iQGMjuzjruEPwh58BtvsMFAMJ+FHWjgFkriLDFBPQOq+Wdhek0Kwp7rEkTqzgWDKSXf04rJ5lXGi0GFaWGT3Jpezm7FkQ/C9HNPdaiNkrzNpIXMTDTryv56yR7ZjJ9R5weDczCW7JjLyLbdz5bOH+8u6/ktyqwB69xJ2Oad08zTB+7zkPLat59lvwx9h/c/4YNm/8d4mxSW4XaSq05p2FCz8VncUPsvOoi/YB12bVGXcrNDcaeV1/XcP4N046gzA==', 'raise': 'eJwlUE1Lw0AQ/f8X0Uh2ZpM0BrrxoxoqeDLgQVCoioGExGKpHtr0Ek3zudkQc3CTPgYG3ryZeTMAANc3jjPVACgQmE1VQJUgSh51SUrUvKozhxIkCElACeBYliI6ZBDRxOi2CrlicEp1VZ+dAVUZUxBGHTQhoohpItpP/F2yVJTPsC7yFcp9A9q+7jLnIjaj6qQMPGF5nt0/PrQm4ijo07qf6+p8y0ulCl0ufi7dfvf9d3fwASLUUq45bRhyUkbH7k4U9/ztdXFO9LG/8elt5z9xiOuj+mNZTVaV074vckZhOAX3gUE2ezutNhlLfJY0zQuu8+KL0sN8aYPKMC00QJc9tqEiWNbwAvIPuyDkUw=='}}


def observe(image,table):
    platform=detect(image,table)
    out={'table_id':table,'platform':platform,'hero_action_candidate':None,'scores':{},'action_verified':False}
    if platform not in BOXES:return out
    a,b,c,d=BOXES[platform];x=STARTS[table-1]
    region=np.asarray(image.crop((x+a-2,b-2,x+c+2,d+2)).convert('L'))
    for label,code in TEMPLATES[platform].items():
        glyph=np.frombuffer(zlib.decompress(base64.b64decode(code)),np.uint8).reshape(d-b,c-a)
        out['scores'][label]=float(cv2.minMaxLoc(cv2.matchTemplate(region,glyph,cv2.TM_CCOEFF_NORMED))[1])
    ordered=sorted(out['scores'].items(),key=lambda p:p[1],reverse=True)
    if ordered[0][1]>=.85 and (len(ordered)==1 or ordered[0][1]-ordered[1][1]>=.10):out['hero_action_candidate']=ordered[0][0]
    return out


def episodes(frames):
    """Collapse consecutive identical visible labels; not an action count."""
    from fractions import Fraction
    active={};out=[];previous=None;seen=set()
    for f in frames:
        pts=Fraction(f['pts']);file=f['file']
        if file in seen or previous is not None and pts<=previous:raise ValueError('Invalid frame sequence')
        seen.add(file)
        if previous is None or int(pts//1)-int(previous//1)!=1 or pts-previous>Fraction(3,2):active.clear()
        previous=pts;rows=f['hero_actions']
        if len(rows)!=4 or {r['table_id'] for r in rows}!={1,2,3,4}:raise ValueError('Invalid table roster')
        for r in rows:
            t=r['table_id'];p=r['platform'];label=r['hero_action_candidate'];old=active.pop(t,None)
            if p not in TEMPLATES or label not in TEMPLATES[p]:continue
            if old is None or (old['platform'],old['label'])!=(p,label):
                old={'table_id':t,'platform':p,'label':label,'first':{'file':file,'pts':str(pts)},'samples':0,'action_verified':False};out.append(old)
            old['last']={'file':file,'pts':str(pts)};old['samples']+=1;active[t]=old
    return out


def run(root):
    import hashlib,io,json
    from pathlib import Path
    from PIL import Image
    root=Path(root);p=root/'manifest.json';raw=p.read_bytes();m=json.loads(raw)
    if m.get('variant')!=5 or m.get('status')!='MIXED_LAYOUT_DISPLAY_REVIEW_ONLY':raise ValueError('Wrong manifest')
    frames=[]
    for r in m['frames']:
        name=r['file'];path=root/'prints'/name
        if Path(name).name!=name or path.is_symlink() or path.parent.is_symlink():raise ValueError('Unsafe print')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=r['sha256']:raise ValueError('Print hash mismatch')
        with Image.open(io.BytesIO(data)) as im:rows=[observe(im.convert('RGB'),t) for t in range(1,5)]
        frames.append({'file':name,'pts':r['pts'],'hero_actions':rows})
    if p.read_bytes()!=raw:raise ValueError('Manifest changed')
    return {'variant':5,'status':'VISIBLE_HERO_LABEL_CANDIDATES_ONLY','manifest_sha256':hashlib.sha256(raw).hexdigest(),'frames':frames,'episodes':episodes(frames),'actions_verified':False,'hands_reconstructed':False}


def main(argv=None):
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('output');a=p.parse_args(argv)
    r=run(a.report)
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2,allow_nan=False)
    return 0
if __name__=='__main__':raise SystemExit(main())
