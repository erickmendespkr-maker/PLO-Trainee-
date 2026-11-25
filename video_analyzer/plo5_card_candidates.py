"""Calibrated offline PLO5 rank/suit candidates; never verified poker facts."""
import argparse
from collections import defaultdict, Counter
import hashlib
import io
import json
import math
from pathlib import Path

from PIL import Image
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, unique_pairs
from offline_video_ingest_probe import sha256, require
from plo5_ingest_job import read_bound_evidence

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
SIZE = 24


def box(rect, width, height):
    require(type(rect) is list and len(rect) == 4 and all(type(v) is int for v in rect), 'Invalid rectangle')
    x, y, w, h = rect
    require(min(x,y) >= 0 and min(w,h) >= 8 and x+w <= width and y+h <= height, 'Rectangle outside image')
    return x,y,x+w,y+h


def overlap(a,b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def validate_profile(profile, regions):
    require(type(profile) is dict and set(profile) == {'variant','rank_roi','suit_roi','tables'}, 'Invalid card profile')
    require(type(profile['variant']) is int and profile['variant'] == 5, 'PLO5 only')
    tables = profile['tables']
    require(type(tables) is list and len(tables) == len(regions), 'One profile per audited region required')
    known = {r['table_id']:r for r in regions}
    result = {}
    for t in tables:
        require(type(t) is dict and set(t) == {'table_id','hero','board'}, 'Invalid table profile')
        tid = t['table_id']
        require(type(tid) is int and tid in known and tid not in result, 'Invalid table ID')
        r = known[tid]
        rectangles = []
        for field in ('hero','board'):
            slots = t[field]
            require(type(slots) is list and len(slots) == 5, 'Exactly five calibrated slots per field required')
            for rect in slots:
                b = box(rect,r['width'],r['height'])
                rank = box(profile['rank_roi'],rect[2],rect[3])
                suit = box(profile['suit_roi'],rect[2],rect[3])
                require(not overlap(rank,suit) and not any(overlap(b,p) for p in rectangles), 'Overlapping card ROIs')
                rectangles.append(b)
        result[tid] = t
    return result


def glyph(image):
    """Dark ink on light background; normalize bounding box without stretching."""
    gray = image.convert('L')
    mask = gray.point(lambda x: 255 if x < 140 else 0)
    bounds = mask.getbbox()
    if bounds is None:
        return None
    cropped = mask.crop(bounds)
    if min(cropped.size) < 2 or max(cropped.size) < 4:
        return None
    cropped.thumbnail((SIZE-4,SIZE-4),Image.Resampling.LANCZOS)
    # Upscale small glyphs too, with the same aspect-ratio convention.
    ratio = (SIZE-4)/max(cropped.size)
    cropped = cropped.resize(tuple(max(1,round(n*ratio)) for n in cropped.size),Image.Resampling.LANCZOS)
    canvas = Image.new('L',(SIZE,SIZE))
    canvas.paste(cropped,((SIZE-cropped.width)//2,(SIZE-cropped.height)//2))
    return bytes(1 if v >= 128 else 0 for v in canvas.tobytes())


def load_templates(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), 'Invalid template directory')
    groups, hashes = {}, {}
    for kind,labels in [('rank',RANKS),('suit',SUITS)]:
        group = {}
        for label in labels:
            name = f'{kind}_{label}.png'
            p = directory/name
            require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 262144, 'Missing or unsafe template: '+name)
            raw = p.read_bytes()
            with Image.open(io.BytesIO(raw)) as im:
                require(im.format == 'PNG' and 8 <= min(im.size) <= max(im.size) <= 256, 'Invalid template image')
                g = glyph(im)
            require(g is not None and g not in group.values(), 'Empty or identical template: '+name)
            group[label] = g
            hashes[name] = hashlib.sha256(raw).hexdigest()
        groups[kind] = group
    return groups, hashes


def match(image, templates):
    g = glyph(image)
    if g is None:
        return {'label':None,'distance':None,'margin':None}
    scored = sorted((sum(a != b for a,b in zip(g,m))/max(1,sum(a or b for a,b in zip(g,m))),k) for k,m in templates.items())
    best,label = scored[0]
    margin = scored[1][0]-best
    return {'label':label if best <= .22 and margin >= .08 else None,
            'distance':round(best,6),'margin':round(margin,6)}


def read_card(image, rect, profile, templates):
    card = image.crop(box(rect,*image.size))
    gray = card.convert('L')
    white = sum(gray.histogram()[200:])/ (card.width*card.height)
    if white < .45:
        return {'status':'no_face_candidate','card':None,'light_fraction':round(white,4)}
    rank = match(card.crop(box(profile['rank_roi'],*card.size)),templates['rank'])
    suit = match(card.crop(box(profile['suit_roi'],*card.size)),templates['suit'])
    token = rank['label']+suit['label'] if rank['label'] and suit['label'] else None
    return {'status':'candidate_unverified' if token else 'uncertain_face','card':token,
            'rank':rank,'suit':suit,'light_fraction':round(white,4)}


def summarize(hero, board):
    h = [r['card'] for r in hero]
    b = [r['card'] for r in board]
    known = [c for c in h+b if c is not None]
    duplicate = len(known) != len(set(known))
    hero_cards = h if all(h) and not duplicate else None
    n = sum(c is not None for c in b)
    # Empty is a visual observation, not proof of preflop.
    board_cards = b[:n] if n in (0,3,4,5) and all(b[:n]) and all(r['status']=='no_face_candidate' for r in board[n:]) and not duplicate else None
    return {'hero_cards':hero_cards,'board_cards':board_cards,'duplicate_conflict':duplicate,
            'human_confirmed':False}


def change_hints(rows, max_gap=10.):
    require(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0 < max_gap <= 30, 'Invalid comparison gap')
    groups = defaultdict(list)
    for row in rows:
        groups[row['table_id']].append(row)
    hints = []
    for tid,items in sorted(groups.items()):
        counts = Counter(r['pts'] for r in items)
        stable, run, last = None, [], None
        for r in sorted(items,key=lambda r:r['pts']):
            pts = r['pts']
            cards = r['hero_cards']
            if counts[pts] > 1 or cards is None or r['board_cards'] != [] or (last is not None and pts-last > max_gap):
                stable,run,last = None,[],None
                continue
            last = pts
            key = tuple(sorted(cards))
            if run and run[-1][0] != key:
                if len(run) == 1 and stable and run[-1][0] != stable[-1][0]:
                    stable = None
                run = []
            run.append((key,r))
            run = run[-2:]
            if len(run) == 2:
                if stable and stable[-1][0] != key:
                    hints.append({'table_id':tid,'interval_pts':[stable[-1][1]['pts'],run[0][1]['pts']],
                                  'evidence_files':[x[1]['file'] for x in stable+run],
                                  'status':'private_card_change_candidate','hand_boundary_verified':False})
                stable = list(run)
    return hints


def analyze_job(database, job_id, profile_path, template_dir, *, max_gap=10.):
    binding = read_bound_evidence(database,job_id)
    job = OfflineJobStore(database).get(job_id)
    folder = Path(job['result_path']).parent/'evidence/ingest'
    p = Path(profile_path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= 16384, 'Unsafe card profile')
    raw = p.read_bytes()
    profile = json.loads(raw,object_pairs_hook=unique_pairs)
    manifest = read_manifest(folder/'manifest.json')
    tables = validate_profile(profile,manifest['regions'])
    templates, hashes = load_templates(template_dir)
    observations = []
    for s in manifest['samples']:
        data = (folder/s['file']).read_bytes()
        require(hashlib.sha256(data).hexdigest()==s['sha256'],'Crop changed during recognition')
        with Image.open(io.BytesIO(data)) as im:
            image = im.convert('RGB')
        t = tables[s['table_id']]
        hero,board = ([read_card(image,rect,profile,templates) for rect in t[field]] for field in ('hero','board'))
        observations.append({'table_id':s['table_id'],'pts':s['actual_frame_timestamp_seconds'],'file':s['file'],
                             'crop_sha256':s['sha256'],'hero_slots':hero,'board_slots':board,**summarize(hero,board)})
    require(sha256(p)==hashlib.sha256(raw).hexdigest() and load_templates(template_dir)[1]==hashes and read_bound_evidence(database,job_id)==binding,'Inputs changed')
    return {'schema_version':1,'variant':5,'job_id':job_id,'source_sha256':binding['source_sha256'],
            'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'profile_sha256':hashlib.sha256(raw).hexdigest(),
            'template_sha256s':hashes,'status':'unverified_calibrated_card_candidates','observations':observations,
            'change_hints':change_hints(observations,max_gap),'max_gap_seconds':max_gap,
            'cards_verified':False,'hands_reconstructed':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('database','job_id','profile','templates','output'):
        p.add_argument(name)
    p.add_argument('--max-gap',type=float,default=10.)
    a = p.parse_args(argv)
    target = Path(a.output)
    require(target.suffix=='.json' and not target.exists() and not target.is_symlink(),'New JSON output required')
    report = analyze_job(a.database,a.job_id,a.profile,a.templates,max_gap=a.max_gap)
    with target.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
