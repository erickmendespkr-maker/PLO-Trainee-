"""Fail-closed aggregation of technical and exact-pixel evidence for offline clips.

Does not validate cards, poker actions, ranges, equity or EV.
"""
from pathlib import Path
from offline_clip_audit_bundle import audit_clip_bundle
from offline_clip_frame_identity import audit_exact_frames


def audit_visual_gate(manifest, source_path, clip_path, *, source_first_frame, max_frames=60):
    if type(source_first_frame) is not int or source_first_frame < 0:
        raise ValueError('invalid source_first_frame')
    if type(max_frames) is not int or not 1 <= max_frames <= 60:
        raise ValueError('invalid max_frames')
    for filename in (source_path, clip_path):
        path = Path(filename)
        if path.is_symlink() or not path.is_file():
            raise ValueError('regular input file required')
    technical = audit_clip_bundle(manifest, clip_path)
    if technical.get('status') != 'TECHNICAL_CLIP_AUDITS_PASSED_ONLY':
        raise ValueError('technical audit not passed')
    if technical.get('approved_for_publication') is not False:
        raise ValueError('unexpected technical approval')
    visual = audit_exact_frames(source_path, clip_path,
                                source_first_frame=source_first_frame, max_frames=max_frames)
    if visual.get('approved_for_publication') is not False or visual.get('visual_hand_verified') is not False:
        raise ValueError('unexpected visual approval')
    if type(visual.get('clip_frames')) is not int or visual['clip_frames'] < 1:
        raise ValueError('empty visual audit')
    if visual['clip_frames'] != technical['pts_audit']['frame_count']:
        raise ValueError('frame count disagreement')
    if visual['matching_frames'] + visual['mismatch_count'] != visual['clip_frames']:
        raise ValueError('inconsistent pixel counts')
    if visual['status'] not in ('EXACT_DECODED_FRAMES_MATCH', 'FRAME_CONTENT_MISMATCH'):
        raise ValueError('unknown visual status')
    if (visual['status'] == 'EXACT_DECODED_FRAMES_MATCH') != (visual['mismatch_count'] == 0):
        raise ValueError('inconsistent visual status')
    return {
        'status': 'PIXEL_AND_TECHNICAL_CANDIDATE_ONLY' if visual['mismatch_count'] == 0 else 'FRAME_CONTENT_MISMATCH',
        'technical_audit': technical, 'visual_audit': visual,
        'approved_for_publication': False, 'source_timeline_verified': False,
        'visual_hand_verified': False, 'ev_verified': False,
        'required_next_checks': ['source_pts_alignment', 'human_hand_review', 'conditional_ev_validation'],
    }
