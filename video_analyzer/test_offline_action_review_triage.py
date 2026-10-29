"""Offline synthetic tests: never infer poker EV from OCR."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parent))
from offline_action_review_triage import build, run

FIXTURE = Path(__file__).parent / 'synthetic_four_tables_review_fixture.json'

@pytest.fixture
def data():
    return json.loads(FIXTURE.read_text())

def test_four_tables(data):
    q = build(data)
    assert q['total_candidates'] == 8
    assert {c['table_id'] for c in q['candidates']} == {1,2,3,4}
    assert {c['variant'] for c in q['candidates']} == {'PLO5','PLO6'}

def test_no_math_or_clip_claims(data):
    q = build(data)
    assert q['ready_for_equity_or_ev'] is False
    assert q['clip_export_authorized'] is False
    assert all(c['actor_identified'] is False and c['clip_export_authorized'] is False
               for c in q['candidates'])

def test_deterministic_order(data):
    assert build(data) == build(copy.deepcopy(data))
    pts = [c['review_priority_points'] for c in build(data)['candidates']]
    assert pts == sorted(pts, reverse=True)

def test_preview_bounds(data):
    hands = {h['hand_id']:h for h in data['hands']}
    for c in build(data)['candidates']:
        h = hands[c['hand_id']]
        assert h['start_seconds'] <= c['preview_start_seconds'] < c['preview_end_seconds'] <= h['end_seconds']

@pytest.mark.parametrize('field,value', [('analysis_status','ev_ready'),('hands_reconstructed',True),
                                         ('ready_for_equity_or_ev',True),('schema_version',True),
                                         ('source_boundaries_sha256','fake')])
def test_bad_provenance(data,field,value):
    data[field] = value
    with pytest.raises(ValueError): build(data)

@pytest.mark.parametrize('field,value', [('actor_identified',True),('action_legality_verified',True),
                                         ('value','hero_raise'),('timestamp_seconds',-1)])
def test_bad_action(data,field,value):
    next(e for e in data['hands'][0]['events'] if e['field']=='action')[field]=value
    with pytest.raises(ValueError): build(data)

def test_existing_output_rejected(tmp_path):
    target=tmp_path/'queue.json'
    result=run(FIXTURE,target)
    assert result['source_timeline_sha256']==hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    with pytest.raises(ValueError): run(FIXTURE,target)

def test_symlink_source_rejected(tmp_path):
    src=tmp_path/'src.json';src.symlink_to(FIXTURE)
    with pytest.raises(ValueError): run(src,tmp_path/'out.json')

def test_duplicate_json_key_rejected(tmp_path):
    src=tmp_path/'bad.json';src.write_text('{"a":1,"a":2}')
    with pytest.raises(ValueError): run(src,tmp_path/'out.json')
