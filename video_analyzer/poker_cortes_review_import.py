"""Import Poker Cortes CSV as UNVERIFIED evidence for offline PLO Trainee review.

No OCR result, stack change, or automatic payout classification becomes a confirmed
loss, a verified hand, or an EV calculation through this importer.
"""
import csv
import hashlib
import json
import math
import re
from pathlib import Path

_TIME = re.compile(r'^(?:(\d+):)?([0-5]?\d):([0-5]\d)(?:\.(\d{1,3}))?$')


def seconds(value):
    match = _TIME.fullmatch(value.strip())
    if not match:
        raise ValueError('timestamp inválido')
    hours, minutes, secs, millis = match.groups()
    return int(hours or 0)*3600 + int(minutes)*60 + int(secs) + int((millis or '').ljust(3, '0'))/1000


def _finite_number(raw):
    if raw is None or not raw.strip():
        return None
    value = float(raw.strip().replace(',', '.'))
    if not math.isfinite(value):
        raise ValueError('número não finito')
    return value


def import_report(csv_path, *, video_sha256, duration_seconds, max_tables=4):
    """Return review candidates; reject invalid records without partially approving any."""
    if not re.fullmatch(r'[a-fA-F0-9]{64}', video_sha256):
        raise ValueError('SHA-256 inválido')
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError('duração inválida')
    if not 1 <= max_tables <= 4:
        raise ValueError('limite de mesas inválido')
    path = Path(csv_path)
    raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';')
        required = {'inicio', 'fim', 'mesa', 'status'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('colunas obrigatórias ausentes')
        output = []
        seen = set()
        for line, row in enumerate(reader, 2):
            if None in row:
                raise ValueError(f'linha {line}: colunas excedentes')
            try:
                start, end = seconds(row['inicio']), seconds(row['fim'])
                table = int(row['mesa'])
                loss = _finite_number(row.get('perda_bb'))
                if not (0 <= start < end <= duration_seconds):
                    raise ValueError('intervalo fora do vídeo')
                if not 1 <= table <= max_tables:
                    raise ValueError('mesa fora do limite')
                if loss is not None and loss < 0:
                    raise ValueError('perda negativa')
            except (TypeError, ValueError) as exc:
                raise ValueError(f'linha {line}: {exc}') from exc
            key = (table, start, end)
            if key in seen:
                raise ValueError(f'linha {line}: intervalo duplicado')
            seen.add(key)
            output.append({
                'source': 'poker_cortes_turbo_3_3_csv',
                'source_csv_sha256': raw_hash,
                'source_row': line,
                'video_sha256': video_sha256.lower(),
                'table_id': table,
                'start_seconds': start,
                'end_seconds': end,
                'ocr_reported_loss_bb': loss,
                'source_status': row['status'].strip(),
                'source_pot_confirmed': (row.get('pote_confirmado') or '').strip(),
                'source_rebuy_seen': (row.get('rebuy_visto') or '').strip(),
                'review_status': 'UNVERIFIED',
                'confirmed_loss_bb': None,
                'verified_by_human': False,
                'strategic_analysis_authorized': False,
            })
    return output


def write_jsonl(candidates, destination):
    target = Path(destination)
    with target.open('w', encoding='utf-8', newline='\n') as stream:
        for candidate in candidates:
            stream.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + '\n')
    return len(candidates)
