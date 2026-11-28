"""Offline display-change evidence, not settlement or rebuy attribution.
Store only the preceding observation per table across window boundaries.
"""
from fractions import Fraction
from plo5_reconstruction_candidates import money, state
from plo5_pre_gto_context import need
from plo5_error_prints import frame_index


class DisplayTransitions:
    def __init__(self):
        self.previous={};self.source=None;self.last=None

    def feed(self,manifest):
        frames=frame_index(manifest);source=manifest['source_sha256'];need(self.source is None or self.source==source,'Display source changed');need(not frames or self.last is None or next(iter(frames))>self.last,'Display timestamps overlap');self.source=source;out=[]
        for pts,f in frames.items():
            self.last=pts;by={(o['table_id'],o['field']):o for o in f['observations']}
            for c in f['cards']:
                t=c['table_id'];platform=c['platform'];old=self.previous.pop(t,None)
                e=c.get('seat_evidence');marker=c.get('panel_evidence')
                if not platform or not e or platform=='suprema' and not (marker and marker.get('seated_panel_candidate') is True):continue
                if e.get('platform')!=platform:continue
                stacks={s['seat']:money(s['stack']['candidate']) for s in e['seats']};p=by.get((t,'pot'),{});h=by.get((t,'stack'),{});pot=money(p.get('value_bb'));hero=money(h.get('value_bb'))
                if h.get('platform')!=platform or p.get('platform')!=platform or hero is None or hero!=stacks.get('hero_bottom'):continue
                now=dict(pts=pts,sha=f['rgb_sha256'],platform=platform,profile=c.get('rank_profile'),cards=state(c),dealer=e['dealer']['seat'],stacks=stacks,pot=pot);self.previous[t]=now
                if old is None or pts-old['pts']>Fraction(2) or (old['platform'],old['profile'])!=(platform,now['profile']):continue
                rises={s:str(v-old['stacks'][s]) for s,v in stacks.items() if v is not None and old['stacks'].get(s) is not None and v>old['stacks'][s]}
                drop=old['pot'] is not None and pot is not None and pot<old['pot'];reset=old['cards'] is not None and now['cards'] is not None and bool(old['cards'][1]) and not now['cards'][1]
                if not (rises or drop or reset):continue
                continuity=old['cards'] is not None and now['cards'] is not None and old['cards'][0]==now['cards'][0] and now['cards'][1][:len(old['cards'][1])]==old['cards'][1] and old['dealer'] is not None and old['dealer']==now['dealer']
                out.append(dict(table_id=t,before_pts=str(old['pts']),after_pts=str(pts),before_rgb_sha256=old['sha'],after_rgb_sha256=now['sha'],stack_display_increases_bb=rises,pot_before_bb=None if old['pot'] is None else str(old['pot']),pot_after_bb=None if pot is None else str(pot),board_reset_candidate=reset,card_dealer_continuity_candidate=continuity,status='DISPLAY_CHANGE_UNATTRIBUTED',payout_verified=False,rebuy_verified=False,showdown_verified=False,financial_result_verified=False))
        return out
