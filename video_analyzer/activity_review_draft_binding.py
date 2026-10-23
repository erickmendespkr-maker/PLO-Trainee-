"""Fail-closed identity gate for offline decision review drafts.

Only binds a draft to its source queue. It does NOT authenticate video,
validate poker actions, or authorize equity/EV.
"""


def check_draft_binding(template, draft):
    if not isinstance(template, dict) or not isinstance(draft, dict):
        raise ValueError('Expected review template and draft objects')
    if set(draft) != set(template):
        raise ValueError('Unexpected/missing root fields')
    for key in set(template) - {'entries', 'analysis_status'}:
        if draft[key] != template[key] or type(draft[key]) is not type(template[key]):
            raise ValueError(f'Protected field modified: {key}')
    if draft['analysis_status'] != 'manual_review_draft_unverified_no_ev':
        raise ValueError('Draft must remain EV-blocked')
    entries = draft['entries']
    originals = template['entries']
    if not isinstance(entries, list) or len(entries) != len(originals):
        raise ValueError('Entry count mismatch')
    for original, entry in zip(originals, entries):
        if not isinstance(entry, dict) or set(entry) != set(original):
            raise ValueError('Invalid entry structure')
        for key in original:
            if key not in ('reviewed_fields', 'reviewer_notes') and (entry[key] != original[key] or type(entry[key]) is not type(original[key])):
                raise ValueError(f'Protected entry field modified: {key}')
    return entries
