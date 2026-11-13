"""Combine independent offline clip audits without promoting their evidence level."""
from pathlib import Path
from offline_clip_ffprobe_audit import audit_clip
from offline_clip_pts_audit import audit_decoded_pts


def audit_clip_bundle(manifest, clip_path, *, ffprobe='ffprobe', ffmpeg='ffmpeg'):
    """Fail closed if either independent technical audit fails.

    This is not proof of source-frame alignment, visual hand identity or EV.
    """
    path = Path(clip_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular non-symlink MP4 required')
    container = audit_clip(manifest, path, ffprobe=ffprobe, ffmpeg=ffmpeg)
    pts = audit_decoded_pts(path, ffprobe=ffprobe)
    if container.get('approved_for_publication') is not False or pts.get('approved_for_publication') is not False:
        raise ValueError('audit must not approve publication')
    if container.get('source_timeline_verified') is not False or pts.get('source_timeline_verified') is not False:
        raise ValueError('unsupported source timeline verification')
    if type(pts.get('frame_count')) is not int or pts['frame_count'] < 1:
        raise ValueError('invalid frame count')
    return {
        'status': 'TECHNICAL_CLIP_AUDITS_PASSED_ONLY',
        'approved_for_publication': False,
        'source_timeline_verified': False,
        'visual_hand_verified': False,
        'ev_verified': False,
        'container_audit': container,
        'pts_audit': pts,
        'required_next_checks': ['source_pts_alignment', 'independent_ledger_authentication', 'visual_hand_review', 'ev_evidence_gate'],
    }
