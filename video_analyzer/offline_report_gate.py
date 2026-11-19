"""Conservative offline review gate for PokerInfra conditional EV reports."""
import math
import re
SHA=re.compile(r'^[a-f0-9]{64}$')
def num(x): return type(x) in (int,float) and math.isfinite(x)
def build_review_packet(hand,report,*,video_sha256,duration_seconds):
    if not isinstance(hand,dict) or not isinstance(report,dict): raise ValueError('invalid objects')
    if not isinstance(video_sha256,str) or not SHA.fullmatch(video_sha256): raise ValueError('invalid sha')
    if not num(duration_seconds) or duration_seconds<=0: raise ValueError('invalid duration')
    table=hand.get('table_id'); start=hand.get('start_pts_seconds'); end=hand.get('end_pts_seconds')
    if type(table) is not int or not 1<=table<=4: raise ValueError('invalid table')
    if not num(start) or not num(end) or not 0<=start<end<=duration_seconds: raise ValueError('invalid timestamps')
    if hand.get('source_video_sha256')!=video_sha256: raise ValueError('video mismatch')
    if hand.get('review_status')!='HUMAN_REVIEWED' or hand.get('hand_boundary_verified') is not True: raise ValueError('unverified boundaries')
    if hand.get('cards_verified') is not True or hand.get('action_verified') is not True: raise ValueError('unverified evidence')
    if report.get('variant') not in ('PLO5','PLO6') or hand.get('variant')!=report.get('variant'): raise ValueError('variant mismatch')
    if hand.get('hero_cards')!=report.get('hero') or hand.get('board_cards')!=report.get('board'): raise ValueError('cards mismatch')
    if report.get('is_gto') is not False or report.get('decision_status')!='REVIEW_REQUIRED' or report.get('video_evidence_status')!='NOT_VERIFIED': raise ValueError('unsafe classification')
    if not isinstance(report.get('opponents'),list) or len(report['opponents'])!=1: raise ValueError('multiway unsupported by simplified call EV')
    ev=report.get('conditional_call_ev')
    if not isinstance(ev,dict) or ev.get('is_gto') is not False or not num(ev.get('call_ev_bb')): raise ValueError('invalid EV')
    q=report.get('equity')
    if not num(q) or not 0<=q<=1: raise ValueError('invalid equity')
    return {'schema_version':1,'source_video_sha256':video_sha256,'table_id':table,
        'start_pts_seconds':start,'end_pts_seconds':end,'variant':report['variant'],
        'equity':q,'conditional_call_ev_bb':ev['call_ev_bb'],
        'confidence':report.get('uncertainty_audit'),
        'analysis_status':'CONDITIONAL_MODEL_REVIEW_REQUIRED',
        'clip_status':'BOUNDARIES_REVIEWED_EXPORT_NOT_VERIFIED',
        'assumptions':['heads_up','fixed_opponent_hand_or_uniform_random','full_equity_realization','no_future_bets','no_side_pots'],
        'is_gto':False,'is_definitive_error':False}
