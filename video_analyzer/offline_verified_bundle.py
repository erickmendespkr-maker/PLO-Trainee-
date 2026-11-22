"""Offline export followed by read-only integrity audit.

A successful integrity audit proves only byte/duration consistency, never
that cards, actions or strategic conclusions were correctly reconstructed.
"""
try:
    from .offline_review_bundle_export import export_review_bundle
    from .offline_bundle_integrity import verify_bundle
except ImportError:
    from offline_review_bundle_export import export_review_bundle
    from offline_bundle_integrity import verify_bundle


def export_and_verify_bundle(source, clip_path, analysis, *, clip_start_s,
                             clip_end_s, ffmpeg='ffmpeg', ffprobe='ffprobe',
                             tolerance_s=0.25):
    """Export a new MP4/JSON pair and audit it without changing either file.

    On audit failure, preserve both outputs for diagnosis and return a failed
    status. Callers must not treat this as an approved clip.
    """
    exported = export_review_bundle(
        source, clip_path, analysis, clip_start_s=clip_start_s,
        clip_end_s=clip_end_s, ffmpeg=ffmpeg, ffprobe=ffprobe)
    audit = verify_bundle(exported['clip'], ffprobe=ffprobe,
                          tolerance_s=tolerance_s)
    return {
        'status': ('EXPORTED_INTEGRITY_OK_TEMPORAL_ONLY'
                   if audit['status'] == 'INTEGRITY_OK_TEMPORAL_ONLY'
                   else 'EXPORTED_INTEGRITY_FAILED'),
        'clip': exported['clip'],
        'report': exported['report'],
        'audit': audit,
        'visual_verification': False,
        'strategic_verification': False,
    }
