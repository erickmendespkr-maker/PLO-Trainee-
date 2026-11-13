"""Audit an offline clip against a verified review ledger, not its own sidecar.

A caller-supplied ledger head is an optional external checkpoint against rollback.
The ledger is not proof that OCR or human review is correct.
"""
from pathlib import Path
from offline_review_registry import verify_ledger
from offline_review_binding import audit_against_review


def audit_against_ledger(mp4_path, ledger_path, *, hand_id, table_id,
                         source_sha256, expected_head_sha256=None):
    entries = verify_ledger(Path(ledger_path))
    if not entries:
        raise ValueError('empty review ledger')
    head = entries[-1]['entry_sha256']
    if expected_head_sha256 is not None and head != expected_head_sha256:
        raise ValueError('ledger head checkpoint mismatch')
    matches = [entry for entry in entries if
               entry['review']['hand_id'] == hand_id and
               entry['review']['table_id'] == table_id and
               entry['review']['source_sha256'] == source_sha256]
    if not matches:
        raise ValueError('no matching reviewed hand in ledger')
    selected = matches[-1]
    result = audit_against_review(mp4_path, selected['review'])
    return {**result, 'ledger_entry_sha256': selected['entry_sha256'],
            'ledger_head_sha256': head, 'ledger_sequence': selected['sequence'],
            'ledger_chain_verified': True,
            'visual_hand_verified': False, 'gto_solution': False}
