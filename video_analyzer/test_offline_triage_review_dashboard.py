"""Synthetic integration tests: triage -> reviewed ROI viewer -> offline dashboard."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parent))
from offline_action_review_triage import build as triage_build
from offline_triage_review_dashboard import assemble, build, page

FIXTURE = Path(__file__).parent / 'synthetic_four_tables_review_fixture.json'
# 1x1 valid PNG fixture; no real recorded poker content.
PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082')


def json_file(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return path


@pytest.fixture
def setup(tmp_path):
    timeline = json.loads(FIXTURE.read_text())
    timeline_path = json_file(tmp_path / 'timeline.json', timeline)
    queue = triage_build(timeline)
    queue['source_timeline_sha256'] = hashlib.sha256(timeline_path.read_bytes()).hexdigest()
    queue_path = json_file(tmp_path / 'queue.json', queue)
    viewer_dir = tmp_path / 'viewer'
    (viewer_dir / 'assets').mkdir(parents=True)
    hands = []
    for h in timeline['hands']:
        events = []
        for e in h['events']:
            idx = e['proposal_index']
            rel = f'assets/roi_{idx:03d}.png'
            (viewer_dir / rel).write_bytes(PNG)
            events.append({'proposal_index': idx, 'timestamp_seconds': e['timestamp_seconds'],
                           'field': e['field'], 'value': e['value'], 'review': e['review'],
                           'raw_ocr_text': '<img src=x onerror=alert(1)>',
                           'roi_png': rel, 'roi_png_sha256': hashlib.sha256(PNG).hexdigest()})
        hands.append({'hand_id': h['hand_id'], 'table_id': h['table_id'],
                      'variant': h['variant'], 'start_seconds': h['start_seconds'],
                      'end_seconds': h['end_seconds'], 'ready_for_equity_or_ev': False,
                      'events': events})
    viewer = {'schema_version': 1, 'analysis_status': 'offline_read_only_action_roi_viewer',
              'source_action_timeline_sha256': queue['source_timeline_sha256'],
              'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
              'hands': hands}
    report_path = json_file(viewer_dir / 'action_roi_report.json', viewer)
    return timeline_path, queue_path, viewer_dir, report_path


def test_four_table_integration(setup, tmp_path):
    result = build(*setup[:3], tmp_path / 'out')
    assert result['candidate_count'] == 8
    assert result['ready_for_equity_or_ev'] is False
    assert result['clip_export_authorized'] is False
    assert len(result['assets_sha256']) == 8
    assert (tmp_path / 'out' / 'index.html').exists()
    assert (tmp_path / 'out' / 'manifest.json').exists()


def test_html_escapes_untrusted_ocr(setup, tmp_path):
    build(*setup[:3], tmp_path / 'out')
    html = (tmp_path / 'out' / 'index.html').read_text()
    assert '<img src=x onerror=alert(1)>' not in html
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert 'Ir para' in html and 'video/mp4' in html
    assert 'http://' not in html and 'https://' not in html


def test_manifest_hashes(setup, tmp_path):
    m = build(*setup[:3], tmp_path / 'out')
    assert m['dashboard_html_sha256'] == hashlib.sha256((tmp_path / 'out' / 'index.html').read_bytes()).hexdigest()
    for path, sha in m['assets_sha256'].items():
        assert hashlib.sha256((tmp_path / 'out' / path).read_bytes()).hexdigest() == sha


def test_deterministic_html(setup, tmp_path):
    build(*setup[:3], tmp_path / 'a')
    build(*setup[:3], tmp_path / 'b')
    assert (tmp_path / 'a' / 'index.html').read_bytes() == (tmp_path / 'b' / 'index.html').read_bytes()


def test_existing_output_refused(setup, tmp_path):
    build(*setup[:3], tmp_path / 'out')
    with pytest.raises(ValueError):
        build(*setup[:3], tmp_path / 'out')


def test_queue_hash_mismatch(setup, tmp_path):
    queue = json.loads(setup[1].read_text());queue['source_timeline_sha256'] = '0'*64
    json_file(setup[1], queue)
    with pytest.raises(ValueError, match='timeline hash'):
        build(*setup[:3], tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_forged_priority_rejected(setup, tmp_path):
    queue = json.loads(setup[1].read_text());queue['candidates'][0]['review_priority_points'] += 999
    json_file(setup[1], queue)
    with pytest.raises(ValueError, match='triage differs'):
        build(*setup[:3], tmp_path / 'out')


def test_missing_viewer_action(setup, tmp_path):
    viewer = json.loads(setup[3].read_text())
    for h in viewer['hands']:
        h['events'] = [e for e in h['events'] if e['field'] != 'action']
    json_file(setup[3], viewer)
    with pytest.raises(ValueError, match='viewer event count mismatch'):
        build(*setup[:3], tmp_path / 'out')


def test_changed_action_value(setup, tmp_path):
    viewer = json.loads(setup[3].read_text())
    for h in viewer['hands']:
        for e in h['events']:
            if e['field'] == 'action':
                e['value'] = 'raise'
    json_file(setup[3], viewer)
    with pytest.raises(ValueError, match='viewer event not in source timeline'):
        build(*setup[:3], tmp_path / 'out')


def test_tampered_roi_detected(setup, tmp_path):
    viewer = json.loads(setup[3].read_text())
    e = next(e for h in viewer['hands'] for e in h['events'] if e['field'] == 'action')
    (setup[2] / e['roi_png']).write_bytes(PNG + b'changed')
    with pytest.raises(ValueError, match='modified ROI'):
        build(*setup[:3], tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_symlink_roi_refused(setup, tmp_path):
    viewer = json.loads(setup[3].read_text())
    e = next(e for h in viewer['hands'] for e in h['events'] if e['field'] == 'action')
    p = setup[2] / e['roi_png']; p.unlink();p.symlink_to(FIXTURE)
    with pytest.raises(ValueError, match='modified ROI'):
        build(*setup[:3], tmp_path / 'out')


def test_duplicate_json_keys_rejected(setup, tmp_path):
    setup[1].write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match='duplicate JSON key'):
        build(*setup[:3], tmp_path / 'out')


def test_html_does_not_claim_ev(setup, tmp_path):
    build(*setup[:3], tmp_path / 'out')
    s = (tmp_path / 'out' / 'index.html').read_text()
    assert 'equity e EV não verificados' in s
    assert 'Não autoriza exportação' in s


def test_wrong_roi_path_rejected(setup, tmp_path):
    viewer = json.loads(setup[3].read_text())
    e = next(e for h in viewer['hands'] for e in h['events'] if e['field'] == 'action')
    e['roi_png'] = '../../secret.png'
    json_file(setup[3], viewer)
    with pytest.raises(ValueError, match='invalid viewer event'):
        build(*setup[:3], tmp_path / 'out')


def test_duplicate_viewer_event_rejected(setup, tmp_path):
    viewer = json.loads(setup[3].read_text())
    viewer['hands'][0]['events'].append(copy.deepcopy(viewer['hands'][0]['events'][0]))
    json_file(setup[3], viewer)
    with pytest.raises(ValueError, match='viewer event count mismatch'):
        build(*setup[:3], tmp_path / 'out')


def test_output_inside_viewer_refused(setup):
    with pytest.raises(ValueError, match='output inside evidence'):
        build(*setup[:3], setup[2] / 'inside')


def test_queue_over_cap(setup, tmp_path):
    queue = json.loads(setup[1].read_text())
    queue['candidates'] *= 9
    queue['total_candidates'] = len(queue['candidates'])
    json_file(setup[1], queue)
    with pytest.raises(ValueError, match='too many candidates'):
        build(*setup[:3], tmp_path / 'out')


def test_invalid_viewer_status(setup, tmp_path):
    viewer = json.loads(setup[3].read_text());viewer['ready_for_equity_or_ev'] = True
    json_file(setup[3], viewer)
    with pytest.raises(ValueError, match='invalid viewer provenance'):
        build(*setup[:3], tmp_path / 'out')
