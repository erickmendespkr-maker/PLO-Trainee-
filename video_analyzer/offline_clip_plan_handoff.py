"""Convert human-confirmed clip plans to the existing offline FFmpeg exporter requests."""
import math

def build_export_requests(plan, video_sha256):
    if not isinstance(plan,dict) or plan.get('schema_version')!=1 or plan.get('analysis_verified') is not False:
        raise ValueError('invalid clip plan')
    if plan.get('source_video_sha256')!=video_sha256 or not isinstance(video_sha256,str) or len(video_sha256)!=64 or any(c not in '0123456789abcdef' for c in video_sha256):
        raise ValueError('source mismatch')
    clips=plan.get('clip_plans')
    if not isinstance(clips,list) or len(clips)>200: raise ValueError('invalid clips')
    result=[]; seen=set()
    for c in clips:
        if not isinstance(c,dict) or c.get('boundaries_verified') is not True or c.get('strategy_verified') is not False or c.get('analysis_label')!='INSUFFICIENT_DATA':
            raise ValueError('unreviewed or promoted clip')
        table=c.get('table_id'); start=c.get('clip_start_seconds'); end=c.get('clip_end_seconds')
        box=c.get('crop_xywh'); hand_id=c.get('hand_id')
        if type(table) is not int or table not in (1,2,3,4) or any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<=start<end or end-start>180:
            raise ValueError('invalid table or interval')
        if not isinstance(box,(list,tuple)) or len(box)!=4 or any(type(v) is not int or v<0 or v%2 for v in box) or box[2]<2 or box[3]<2:
            raise ValueError('invalid even crop')
        if not isinstance(hand_id,str) or not 1<=len(hand_id)<=128 or hand_id in seen:
            raise ValueError('invalid or duplicate hand ID')
        seen.add(hand_id)
        result.append({'schema_version':1,'hand_id':hand_id,'table_id':table,
            'start_seconds':start,'end_seconds':end,
            'crop':dict(zip(('x','y','width','height'),box)),
            'explanation':'Corte de vídeo gravado para revisão humana. Dados estratégicos insuficientes.',
            'source_video_sha256':video_sha256,'reviewer_confirmed_offline':True})
    return {'schema_version':1,'source_video_sha256':video_sha256,
        'export_requests':result,'analysis_verified':False,'is_gto':False}
