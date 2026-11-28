"""Verify and restore original PLO5 windowed observations for offline reanalysis.

This is an archive *integrity* and source-provenance check, not independent
validation of OCR labels, positions, hands or financial outcomes. Restored
manifest data stays local and is never committed with the application code.
"""
import argparse
import hashlib
import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from plo5_fourcolor_cards import load_bank
from plo5_video_stream import digest


MAX_WINDOWS = 128
MAX_MEMBER = 32 * 1024 * 1024
MAX_ARCHIVE_CONTENT = 64 * 1024 * 1024


def inspect_archive(archive, video, ppp, suprema, target):
    """Atomically restore a Macro22-compatible session after full hash checking.

    Requires both banks to match the declared archive hashes. Never transcodes
    frames, supplies absent evidence, infers betting actions, or enables strategy.
    """
    archive, video, ppp, suprema, target = map(Path, (archive, video, ppp, suprema, target))
    if not (archive.is_file() and not archive.is_symlink() and archive.suffix.lower()=='.zip'
            and 0<archive.stat().st_size<=MAX_ARCHIVE_CONTENT):
        raise ValueError('Invalid local observation archive')
    if not (video.is_file() and not video.is_symlink() and video.suffix.lower()=='.mp4'):
        raise ValueError('Local source MP4 required')
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError('New local destination required')
    # Always validate the actual template structure, not just a self-declared hash.
    load_bank(ppp)
    load_bank(suprema)
    actual_banks = {'pppoker': digest(ppp), 'suprema': digest(suprema)}
    actual_video = digest(video)
    try:
        with ZipFile(archive) as z:
            members = z.infolist()
            if (not 2<=len(members)<=MAX_WINDOWS+1 or len(set(v.filename for v in members))!=len(members)
                    or any(v.is_dir() or v.file_size>MAX_MEMBER or v.flag_bits & 1
                           or v.filename!='session.json' and not (
                               v.filename.startswith('window_') and v.filename.endswith('.json')
                               and len(v.filename)==17) for v in members)
                    or sum(v.file_size for v in members)>MAX_ARCHIVE_CONTENT):
                raise ValueError('Unsafe observation archive member roster')
            declared = json.loads(z.read('session.json'))
            if not (type(declared) is dict and declared.get('variant')==5
                    and declared.get('version')=='plo5-windowed-candidates-v1'
                    and declared.get('source_sha256')==actual_video
                    and declared.get('card_bank_sha256')==actual_banks
                    and declared.get('hands_reconstructed') is False
                    and declared.get('strategy_authorized') is False):
                raise ValueError('Observation session provenance mismatch')
            windows = declared.get('windows')
            if type(windows) is not list or not 1<=len(windows)<=MAX_WINDOWS:
                raise ValueError('Invalid observation window list')
            expected={'session.json'}|{f'window_{i:05d}.json' for i in range(1,len(windows)+1)}
            if {v.filename for v in members}!=expected:
                raise ValueError('Missing or undeclared observation member')
            restored=[]
            total=0
            next_start=None
            for i,w in enumerate(windows,1):
                name=f'window_{i:05d}.json'
                if not (type(w) is dict and w.get('file')==name and
                        type(w.get('start')) is int and type(w.get('seconds')) is int
                        and 0<=w['start'] and 2<=w['seconds']<=120 and
                        (next_start is None or next_start==w['start'])):
                    raise ValueError('Non-contiguous observation windows')
                raw=z.read(name)
                if hashlib.sha256(raw).hexdigest()!=w.get('sha256'):
                    raise ValueError('Observation window checksum mismatch')
                data=json.loads(raw)
                rows=data.get('frames')
                if not (type(data) is dict and data.get('variant')==5
                        and data.get('source_sha256')==actual_video
                        and data.get('hands_reconstructed') is False
                        and data.get('strategy_authorized') is False
                        and type(rows) is list and len(rows)==w.get('frames')):
                    raise ValueError('Observation window metadata mismatch')
                prev=None
                for row in rows:
                    if not isinstance(row,dict) or 'pts' not in row:
                        raise ValueError('Invalid observation frame')
                    t=Fraction(row['pts'])
                    if not (w['start']<=t<w['start']+w['seconds'] and (prev is None or t>prev)):
                        raise ValueError('Unordered or out-of-window observation timestamp')
                    prev=t
                total+=len(rows)
                restored.append((name,raw))
                next_start=w['start']+w['seconds']
            if total != declared.get('frames'):
                raise ValueError('Observation frame count mismatch')
            # Stage output only after *all* members and source hashes are verified.
            with tempfile.TemporaryDirectory(dir=target.parent,prefix='.plo5-observations-') as tmp:
                staged=Path(tmp)/'restored';staged.mkdir()
                (staged/'session.json').write_bytes(z.read('session.json'))
                for name,raw in restored:
                    (staged/name).write_bytes(raw)
                if target.exists() or target.is_symlink():
                    raise ValueError('Destination appeared during restore')
                os.rename(staged,target)
    except BadZipFile as exc:
        raise ValueError('Corrupt observation ZIP') from exc
    return dict(status='RESTORED_UNVERIFIED_VISUAL_CANDIDATES',source_sha256=actual_video,
                card_bank_sha256=actual_banks,windows=len(windows),frames=total,
                hands_reconstructed=False,financial_result_verified=False,
                strategy_authorized=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive');p.add_argument('video');p.add_argument('output')
    p.add_argument('--ppp',required=True);p.add_argument('--suprema',required=True)
    a=p.parse_args(argv)
    print(json.dumps(inspect_archive(a.archive,a.video,a.ppp,a.suprema,a.output),indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
