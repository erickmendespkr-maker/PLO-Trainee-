"""Offline OCR probes for manually selected regions of a recorded video.

Outputs literal text and engine confidence; it does not interpret cards, pots,
actions, or player identities. Requires FFmpeg, FFprobe and Tesseract.
"""
from dataclasses import asdict, dataclass
import csv
from io import StringIO
import math
from pathlib import Path
import subprocess
import tempfile

from table_regions import Region, validate_regions
from video_segments import probe_video, _run


@dataclass(frozen=True)
class OCRProbe:
    timestamp: float
    table_id: int
    region: dict
    text: str
    word_count: int
    mean_engine_confidence: float | None
    source: str = 'tesseract_manual_roi'


def parse_tesseract_tsv(tsv):
    """Return only detected words; ignore blank TSV lines and confidence=-1."""
    rows = csv.DictReader(StringIO(tsv), delimiter='\t')
    if rows.fieldnames is None or not {'text', 'conf'}.issubset(rows.fieldnames):
        raise ValueError('Invalid Tesseract TSV')
    words = []
    confidences = []
    for row in rows:
        word = (row.get('text') or '').strip()
        if not word:
            continue
        try:
            confidence = float(row['conf'])
        except (TypeError, ValueError) as exc:
            raise ValueError('Invalid OCR confidence') from exc
        if not math.isfinite(confidence):
            raise ValueError('Nonfinite OCR confidence')
        if confidence < 0:
            continue
        words.append(word)
        confidences.append(max(0., min(100., confidence)) / 100.)
    return ' '.join(words), len(words), sum(confidences) / len(confidences) if confidences else None


def read_video_text(video_path, timestamp, region):
    """OCR one video frame in an explicitly specified pixel rectangle.

    Confidence reflects OCR engine word scores, NOT probability that poker
    state is correct. Callers must review and calibrate all outputs.
    """
    if not isinstance(region, Region):
        raise TypeError('Expected Region')
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
        raise ValueError('Invalid timestamp')
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(video_path)
    metadata = probe_video(video_path)
    if not 0 <= timestamp < metadata['duration']:
        raise ValueError('Timestamp outside video duration')
    validate_regions([region], metadata['width'], metadata['height'])
    with tempfile.TemporaryDirectory(prefix='plo_ocr_') as folder:
        cropped = Path(folder) / 'roi.png'
        crop = f'crop={region.width}:{region.height}:{region.x}:{region.y}'
        _run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
              '-ss', str(timestamp), '-i', str(video_path), '-frames:v', '1',
              '-vf', crop, str(cropped)])
        if not cropped.is_file():
            raise RuntimeError('FFmpeg did not produce a frame')
        result = subprocess.run(['tesseract', str(cropped), 'stdout', '--psm', '6', 'tsv'],
                                check=True, capture_output=True, text=True)
    text, count, confidence = parse_tesseract_tsv(result.stdout)
    return asdict(OCRProbe(float(timestamp), region.table_id, asdict(region), text,
                           count, confidence))
