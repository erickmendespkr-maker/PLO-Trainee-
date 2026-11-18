# -*- coding: utf-8 -*-
"""Analisador de sessoes de poker por video (offline), sem historicos de maos."""
from __future__ import annotations

import base64
import csv
import difflib
import io
import json
import os
import re
import statistics
import subprocess
import tempfile
import threading
import unicodedata
from collections import deque
from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageChops, ImageEnhance, ImageOps, ImageStat, ImageTk
except ImportError as exc:
    raise SystemExit("Pillow ausente. Execute INICIAR_ANALISE_VIDEO.bat para instalar.") from exc

from cortador import Clip, export_clip, file_at, fmt, parse_time, probe, resource

W, H = 960, 540
VIEW_W, VIEW_H = 720, 405
TABLES = (1, 2, 3, 4)
LAYOUT_LABELS = ("Auto (ate 4, slots fixos)", "1 mesa", "2 lado a lado",
                 "3 lado a lado", "4 lado a lado", "2 por 2")


def layout_key(label):
    """Converte selecao visual para layout tecnico."""
    lookups = {
        "Auto (ate 4, slots fixos)": "auto4", "1 mesa": "horizontal1",
        "2 lado a lado": "horizontal2", "3 lado a lado": "horizontal3",
        "4 lado a lado": "horizontal4", "2 por 2": "grid2x2"
    }
    if label in lookups:
        return lookups[label]
    if label in (*lookups.values(),):
        return label
    raise ValueError("Disposicao desconhecida: " + str(label))


def mode_at(t, initial, events):
    current = layout_key(initial)
    for event in sorted(events, key=lambda e: float(e["start"])):
        if t + 1e-7 < float(event["start"]):
            break
        current = layout_key(event["layout"])
    return current


def layout_count(mode):
    key = layout_key(mode)
    if key in ("auto4", "grid2x2"):
        return 4
    return int(key.removeprefix("horizontal"))


def layout_bounds(mode, table):
    count = layout_count(mode)
    if table not in TABLES or table > count:
        raise ValueError("Mesa inexistente na disposicao atual.")
    if layout_key(mode) == "grid2x2":
        col = (table - 1) % 2
        row = (table - 1) // 2
        return (col * W // 2, row * H // 2,
                (col + 1) * W // 2, (row + 1) * H // 2)
    return (round((table - 1) * W / count), 0,
            round(table * W / count), H)


def layout_rect(base_rect, table, mode):
    """Adapta uma ROI cadastrada no perfil de quatro colunas para 1, 2 ou 3."""
    rect = roi_tuple(base_rect)
    if layout_key(mode) == "grid2x2":
        return rect
    count = layout_count(mode)
    orig_x = (table - 1) * W // 4
    new_x = round((table - 1) * W / count)
    ratio = 4 / count
    return (round(new_x + (rect[0] - orig_x) * ratio), rect[1],
            round(new_x + (rect[2] - orig_x) * ratio), rect[3])


def unmap_layout_rect(rect, table, mode):
    """Transformacao inversa usada ao desenhar uma ROI na previa."""
    rect = roi_tuple(rect)
    if layout_key(mode) == "grid2x2":
        return list(rect)
    count = layout_count(mode)
    new_x = round((table - 1) * W / count)
    old_x = (table - 1) * W // 4
    return [round(old_x + (rect[0] - new_x) * count / 4), rect[1],
            round(old_x + (rect[2] - new_x) * count / 4), rect[3]]


def table_visible(frame, bounds, strict=True):
    """Detecta mesas presentes em slots fixos por assinatura visual do felt.

    Conservador: discrimina espacos vazios uniformes de uma mesa, mas uma
    tela desktop complexa ainda pode gerar falso positivo. Use eventos de
    disposicao para layouts que se reorganizam durante a sessao.
    """
    x1, y1, x2, y2 = bounds
    if x2 <= x1 or y2 <= y1:
        return False
    patch = frame.crop(bounds).convert("L").resize((40, 60))
    all_stats = ImageStat.Stat(patch)
    if all_stats.stddev[0] < 8:
        return False
    upper = ImageStat.Stat(patch.crop((5, 1, 35, 9))).mean[0]
    felt = ImageStat.Stat(patch.crop((10, 22, 30, 37))).mean[0]
    # Auto exige assinatura visual do felt para evitar considerar desktop uma mesa.
    # Um layout explicitamente selecionado aceita temas mais escuros ou diferentes.
    if not strict:
        return 8 <= felt <= 247
    return 16 <= felt <= 236 and abs(felt - upper) >= 10


def screenshot_profile():
    """Regioes estimadas do print enviado: quatro mesas verticais lado a lado.

    Coordenadas em imagem normalizada 960x540. Hero sempre embaixo,
    e somente as cartas do hero aparecem no pre-flop.
    A geometria e valida somente se as mesas nao mudarem de posicao.
    """
    out = {}
    for table in TABLES:
        dx = (table - 1) * 240
        out[str(table)] = {
            "hole": [dx + 128, 434, dx + 206, 484],
            "stack": [dx + 97, 488, dx + 153, 510],
            "nick": [dx + 91, 472, dx + 155, 496],
            "bb": "1", "detector": "bright",
            "bright_cutoff": 165, "min_bright": .18,
            "profile": "4_colunas_heroi_inferior_v1"
        }
    return out


def replicate_horizontal_rect(rect, source_table):
    """Repete um retangulo de uma mesa em quatro colunas de igual largura."""
    rect = roi_tuple(rect)
    if source_table not in TABLES:
        raise ValueError("Mesa invalida.")
    width = W // 4
    offset = (source_table - 1) * width
    relative = (rect[0] - offset, rect[1], rect[2] - offset, rect[3])
    if relative[0] < 0 or relative[2] > width:
        raise ValueError("Retangulo precisa ficar dentro de uma unica mesa.")
    return {
        t: [relative[0] + (t - 1) * width, relative[1],
            relative[2] + (t - 1) * width, relative[3]]
        for t in TABLES
    }


def bright_fraction(frame, rect, cutoff=165):
    """Proporcao de pixels brilhantes na area das cartas do jogador."""
    region = frame.crop(roi_tuple(rect)).convert("L")
    mask = region.point(lambda value: 255 if value >= cutoff else 0)
    return ImageStat.Stat(mask).mean[0] / 255.0


def roi_tuple(rect):
    if not rect or len(rect) != 4:
        raise ValueError("Regiao nao configurada.")
    x1, y1, x2, y2 = map(int, rect)
    if x1 >= x2 or y1 >= y2 or min(x1, y1) < 0 or x2 > W or y2 > H:
        raise ValueError("Regiao fora do quadro.")
    return x1, y1, x2, y2


def read_exact(stream, count):
    data = bytearray()
    while len(data) < count:
        part = stream.read(count - len(data))
        if not part:
            break
        data.extend(part)
    return bytes(data)


def image_png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def png_image(data):
    return Image.open(io.BytesIO(base64.b64decode(data))).convert("L")


def changed_fraction(frame, reference, rect, pixel_threshold=32):
    part = frame.crop(roi_tuple(rect))
    if part.size != reference.size:
        raise ValueError("A referencia do campo cartas tem tamanho diferente. Registre-a novamente.")
    diff = ImageChops.difference(part, reference)
    mask = diff.point(lambda value: 255 if value > pixel_threshold else 0)
    return ImageStat.Stat(mask).mean[0] / 255.0


def parse_stack(value):
    # A regiao do OCR deve conter SOMENTE o saldo em fichas do jogador.
    candidates = re.findall(r"\d[\d.,]*", value.replace(" ", ""))
    if not candidates:
        return None
    token = max(candidates, key=len).rstrip(".,")
    if not token:
        return None
    if "." in token and "," in token:
        token = token.replace(".", "") .replace(",", ".") if token.rfind(",") > token.rfind(".") else token.replace(",", "")
    elif token.count(".") > 1:
        token = token.replace(".", "")
    elif token.count(",") > 1:
        token = token.replace(",", "")
    elif "," in token:
        right = token.split(",")[-1]
        token = token.replace(",", "") if len(right) == 3 else token.replace(",", ".")
    elif "." in token and len(token.split(".")[-1]) == 3:
        token = token.replace(".", "")
    try:
        amount = float(token)
        return amount if 0 <= amount < 1e9 else None
    except ValueError:
        return None


def ocr_stack(img, tesseract, quick=False):
    # Binarizacao com 2 passes (interface clara/escura).
    sample = ImageOps.autocontrast(img.convert("L").resize((img.width * 4, img.height * 4)))
    sample = ImageEnhance.Contrast(sample).enhance(2.4)
    attempts = [sample.point(lambda x: 255 if x > 130 else 0),
                ImageOps.invert(sample).point(lambda x: 255 if x > 130 else 0)]
    values = []
    with tempfile.TemporaryDirectory(prefix="plo_ocr_") as temp:
        for i, prepared in enumerate(attempts):
            path = Path(temp) / f"stack_{i}.png"
            prepared.save(path)
            cmd = [tesseract, str(path), "stdout", "--psm", "7",
                   "-c", "tessedit_char_whitelist=0123456789,."]
            p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                               timeout=18, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if p.returncode == 0:
                val = parse_stack(p.stdout)
                if val is not None:
                    values.append(val)
                    if quick:  # no fast mode do not perform a redundant second OCR pass
                        break
    if not values:
        return None
    if len(values) == 2 and abs(values[0] - values[1]) > max(3, values[0] * .08):
        return None  # leituras contraditorias: pedir revisao
    return statistics.median(values)


def normalize_nick(value):
    """Ignora acentos, caixa, sinais e espacos para comparar nome de tela."""
    ascii_text = unicodedata.normalize("NFKD", str(value))
    ascii_text = "".join(c for c in ascii_text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", ascii_text.casefold())


def nickname_matches(recognized, expected):
    wanted = normalize_nick(expected)
    seen = normalize_nick(recognized)
    if len(wanted) < 3 or len(seen) < 3:
        return False
    if wanted in seen:
        return True
    # Pequenos erros do OCR sao comuns no nome sobreposto a um avatar.
    return difflib.SequenceMatcher(None, seen, wanted).ratio() >= .84


def read_nickname(image, tesseract):
    """Lê nome apenas na area definida do jogador; pode falhar em fonte pequena."""
    region = image.convert("L")
    if region.width < 6 or region.height < 6:
        return []
    region = ImageOps.autocontrast(region.resize(
        (max(180, region.width * 5), max(48, region.height * 5))))
    variants = [region, ImageOps.invert(region)]
    readings = []
    with tempfile.TemporaryDirectory(prefix="plo_nick_") as temp_dir:
        for index, candidate in enumerate(variants):
            filepath = Path(temp_dir) / f"nick_{index}.png"
            candidate.save(filepath)
            process = subprocess.run(
                [tesseract, str(filepath), "stdout", "--psm", "7"],
                capture_output=True, text=True, errors="replace", timeout=16,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if process.returncode == 0 and process.stdout.strip():
                readings.append(process.stdout.strip())
    return readings


def stack_median(images, tesseract, quick=False):
    """Analise rapida: ate duas imagens, um OCR por imagem se legivel."""
    values = []
    samples = images[-2:] if quick else images
    for sample in samples:
        try:
            v = ocr_stack(sample, tesseract, quick=quick)
            if v is not None:
                values.append(v)
        except (subprocess.SubprocessError, OSError):
            continue
    if quick and not values and len(images) > 2:
        # Salvaguarda para leitura ausente: terceira imagem em modo detalhado.
        try:
            retry = ocr_stack(images[0], tesseract, quick=False)
            if retry is not None:
                values.append(retry)
        except (subprocess.SubprocessError, OSError):
            pass
    if not values:
        return None, 0
    middle = statistics.median(values)
    consistent = [x for x in values if abs(x - middle) <= max(2, middle * .08)]
    if not consistent:
        return None, 0
    return statistics.median(consistent), len(consistent)


@dataclass
class Candidate:
    start: float
    end: float
    table: int
    loss_bb: float | None
    stack_before: float | None
    stack_after: float | None
    status: str
    confirmed: bool = False
    excluded: bool = False
    nick: str = ""
    nick_verified: bool = False
    layout: str = "horizontal4"


def net_loss_bb(stack_before, stack_after, bb_value):
    """Perda liquida em BB a partir dos saldos reais daquela mao, sem stack padrao."""
    if bb_value <= 0:
        raise ValueError("BB deve ser positivo.")
    return (stack_before - stack_after) / bb_value


def loss_reaches_threshold(loss_bb, threshold):
    """O valor de corte e INCLUSIVO (30 BB entra no filtro de 30 BB)."""
    return loss_bb is not None and (loss_bb >= threshold or
                                   abs(loss_bb - threshold) <= 1e-9)


class HandState:
    """Deteccao de cartas do heroi por diferenca com quadro vazio de referencia."""
    def __init__(self):
        self.layout = "horizontal4"
        self.active = False
        self.on_count = 0
        self.off_count = 0
        self.on_start = 0.
        self.off_start = 0.
        self.start_at = 0.
        self.before = []
        self.empty_frames = deque(maxlen=9)
        self.pending = None
        self.results = []

    def feed(self, t, occupied, stack_img, table, bb, threshold, tesseract, quick=False):
        if not self.active:
            if self.pending is not None:
                if not occupied and len(self.pending["after"]) < 3:
                    self.pending["after"].append(stack_img.copy())
                if len(self.pending["after"]) >= 3 or occupied:
                    self.finish(table, bb, threshold, tesseract, quick=quick)
            if occupied:
                if self.on_count == 0:
                    self.on_start = t
                self.on_count += 1
                if self.on_count >= 2:
                    self.active = True
                    self.start_at = self.on_start
                    # O saldo anterior a distribuicao e melhor que o saldo no flop.
                    samples = [x[1] for x in list(self.empty_frames)[-5:]]
                    self.before = [im.copy() for im in samples[-3:]]
                    self.on_count = 0
                    self.off_count = 0
            else:
                self.on_count = 0
                self.empty_frames.append((t, stack_img.copy()))
            return

        if occupied:
            self.off_count = 0
        else:
            if self.off_count == 0:
                self.off_start = t
            self.off_count += 1
            if self.off_count >= 2:
                self.active = False
                self.pending = {"start": self.start_at, "end": self.off_start,
                                "before": self.before[:], "after": [stack_img.copy()]}
                self.off_count = 0
                self.empty_frames.clear()

    def finish(self, table, bb, threshold, tesseract, quick=False):
        data = self.pending
        self.pending = None
        if not data:
            return
        pre, n_pre = stack_median(data["before"], tesseract, quick=quick)
        post, n_post = stack_median(data["after"], tesseract, quick=quick)
        loss = None if pre is None or post is None else net_loss_bb(pre, post, bb)
        if loss is None:
            status = "INCONCLUSIVO - OCR"
        elif loss_reaches_threshold(loss, threshold):
            status = "POSSIVEL PERDA >= LIMITE"
            if n_pre < 2 or n_post < 2:
                status += " (LEITURA FRACA)"
        else:
            return
        self.results.append(Candidate(
            max(0, data["start"] - 5), data["end"] + 5, table,
            round(loss, 2) if loss is not None else None, pre, post, status,
            layout=self.layout))


def scan_videos(videos, config, threshold, progress, hero_nick="~Pulgar~",
                quick=True, initial_layout="Auto (ate 4, slots fixos)", events=None):
    """Varre uma unica gravacao ou varios videos, com ate 4 mesas e eventos de layout."""
    tesseract = resource("tesseract")
    ffmpeg = resource("ffmpeg")
    if not tesseract:
        raise RuntimeError("Tesseract OCR nao encontrado.")
    if not ffmpeg:
        raise RuntimeError("FFmpeg nao encontrado.")

    events = sorted(events or [], key=lambda e: float(e["start"]))
    all_modes = {layout_key(initial_layout)}
    all_modes.update(layout_key(item["layout"]) for item in events)
    table_cfg = {}
    for mode in all_modes:
        for table in range(1, layout_count(mode) + 1):
            data = config[str(table)]
            detection = data.get("detector", "reference" if data.get("reference") else "bright")
            if detection not in ("bright", "reference"):
                raise ValueError(f"Detector invalido na mesa {table}.")
            if detection == "reference" and not data.get("reference"):
                raise ValueError(f"Mesa {table}: referencia manual ausente.")
            cfg = {
                "hole": layout_rect(data["hole"], table, mode),
                "stack": layout_rect(data["stack"], table, mode),
                "nick": layout_rect(data["nick"], table, mode) if data.get("nick") else None,
                "detector": detection,
                "empty": png_image(data["reference"]) if detection == "reference" else None,
                "bb": float(data["bb"]),
                "bright_cutoff": int(data.get("bright_cutoff", 165)),
                "min_bright": float(data.get("min_bright", .18)),
                "min_change": float(data.get("min_change", .08)),
            }
            if cfg["bb"] <= 0:
                raise ValueError(f"Valor de 1 BB deve ser positivo na mesa {table}.")
            table_cfg[(mode, table)] = cfg

    active_mode = None
    states = {}
    missing_counts = {table: 0 for table in TABLES}
    collected = []
    nick_verified = {}
    nick_attempts = {}
    sample_times = {0, 15, 45, 90, 180, 360}
    segment_start = 0.0
    detected_frames = 0

    def close_state(table, end_time, reason):
        state = states.pop(table, None)
        if state is None:
            return
        key = (state.scan_mode, table)
        cfg = table_cfg.get(key)
        if state.pending and cfg is not None:
            state.finish(table, cfg["bb"], threshold, tesseract, quick=quick)
        for candidate in state.results:
            candidate.start = max(candidate.start, segment_start)
            candidate.end = min(candidate.end, end_time)
            if candidate.end > candidate.start:
                collected.append(candidate)
        if state.active:
            # Nao considerar desaparecimento/rearranjo uma perda confirmada.
            start_time = max(segment_start, state.start_at - 5)
            if end_time > start_time:
                collected.append(Candidate(
                    start_time, end_time, table, None, None, None,
                    reason, layout=state.layout))

    for file_index, v in enumerate(videos):
        progress(f"Lendo {file_index + 1}/{len(videos)}: {Path(v.path).name}")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error",
                   "-i", v.path, "-an", "-vf", f"fps=1,scale={W}:{H},format=gray",
                   "-f", "rawvideo", "pipe:1"]
        proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            n = 0
            while True:
                packet = read_exact(proc.stdout, W * H)
                if len(packet) != W * H:
                    break
                frame = Image.frombytes("L", (W, H), packet)
                t = v.start + n
                mode = mode_at(t, initial_layout, events)
                if mode != active_mode:
                    if active_mode is not None:
                        for table in list(states):
                            close_state(table, t, "INCONCLUSIVO - MESA MUDOU DE LUGAR")
                        segment_start = t
                    else:
                        segment_start = t
                    active_mode = mode
                    states = {}
                    missing_counts = {table: 0 for table in TABLES}
                    progress(f"{fmt(t)}: disposicao {mode}; {layout_count(mode)} posicoes possiveis")

                seen = 0
                for table in range(1, layout_count(mode) + 1):
                    cfg = table_cfg[(mode, table)]
                    # Detecta janelas removidas mesmo quando o modo e "Auto".
                    # Tres quadros ausentes consecutivos evitam reset por animacao.
                    if not table_visible(
                            frame, layout_bounds(mode, table), strict=(mode == "auto4")):
                        missing_counts[table] += 1
                        if missing_counts[table] == 3:
                            close_state(table, t, "INCONCLUSIVO - MESA FECHADA OU OCULTA")
                        continue
                    seen += 1
                    if missing_counts[table] >= 3 or table not in states:
                        states[table] = HandState()
                        states[table].layout = (
                            "horizontal4" if mode == "auto4" else mode)
                        states[table].scan_mode = mode
                    missing_counts[table] = 0

                    key = (mode, table)
                    if (hero_nick.strip() and cfg["nick"] and
                            not nick_verified.get(key, False) and
                            nick_attempts.get(key, 0) < len(sample_times) and
                            (n in sample_times or
                             (segment_start > 0 and round(t - segment_start) in sample_times))):
                        nick_attempts[key] = nick_attempts.get(key, 0) + 1
                        try:
                            texts = read_nickname(frame.crop(cfg["nick"]), tesseract)
                            if any(nickname_matches(value, hero_nick) for value in texts):
                                nick_verified[key] = True
                                progress(f"Mesa {table}: nick {hero_nick} confirmado.")
                        except (OSError, subprocess.SubprocessError):
                            pass

                    if cfg["detector"] == "bright":
                        occupied = bright_fraction(frame, cfg["hole"],
                                                   cfg["bright_cutoff"]) >= cfg["min_bright"]
                    else:
                        occupied = changed_fraction(frame, cfg["empty"],
                                                    cfg["hole"]) >= cfg["min_change"]
                    states[table].feed(t, occupied, frame.crop(cfg["stack"]), table,
                                       cfg["bb"], threshold, tesseract, quick=quick)
                if seen:
                    detected_frames += 1
                n += 1
                if n == 30 and not detected_frames:
                    progress("AVISO: nenhum slot reconhecido nos primeiros 30s; "
                             "confira o layout e use Conferir mesas no frame.")
                if n % 60 == 0:
                    progress(f"{Path(v.path).name}: {fmt(n)} / {fmt(v.duration)} "
                             f"| mesas visiveis: {seen} | {mode}")
            if proc.wait(timeout=15) != 0:
                raise RuntimeError("FFmpeg falhou lendo " + v.path)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if proc.stdout:
                proc.stdout.close()

    if detected_frames == 0:
        raise ValueError("Nenhuma mesa foi reconhecida. Confira a disposicao inicial, "
                         "as mudancas do video e o botao Conferir mesas no frame.")
    total = sum(v.duration for v in videos)
    for table in list(states):
        close_state(table, total, "INCONCLUSIVO - MAO INTERROMPIDA NO FIM")
    for candidate in collected:
        candidate.end = min(total, candidate.end)
        candidate.nick = hero_nick.strip()
        key = ("auto4" if candidate.layout == "horizontal4" and
               "auto4" in all_modes else candidate.layout, candidate.table)
        candidate.nick_verified = nick_verified.get(key, False)
        if hero_nick.strip() and not candidate.nick_verified:
            candidate.status += " | NICK NAO CONFIRMADO"
    progress(f"Video completo: {len(collected)} candidatas/pendencias. "
             "Fechamentos e mudancas de layout exigem revisao.")
    return sorted(collected, key=lambda item: (item.start, item.table))


class GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PLO - Analise visual de videos (sem DriveHUD)")
        self.geometry("1120x800")
        self.minsize(990, 740)
        self.videos = []
        self.total = 0.
        self.frame = None
        self.photo = None
        self.selection_origin = None
        self.candidates = []
        self.busy = False
        self.layout = tk.StringVar(value=LAYOUT_LABELS[0])
        self.change_to = tk.StringVar(value="3 lado a lado")
        self.timeline = []
        self.nick = tk.StringVar(value="~Pulgar~")
        self.quick = tk.BooleanVar(value=True)
        self.cfg = screenshot_profile()
        self._ui()
        self.draw()
        self.tell("Aceita 1-4 mesas. Use eventos para quando janelas mudarem de posicao.")

    def _ui(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=5)
        ttk.Button(top, text="Adicionar 1 video completo ou varias partes", command=self.add_videos).pack(side="left")
        ttk.Button(top, text="Limpar videos", command=self.clear_videos).pack(side="left")
        self.info = ttk.Label(top, text="Nenhum video carregado")
        self.info.pack(side="left", padx=8)
        ttk.Label(top, text="Disposicao:").pack(side="left", padx=(12, 3))
        layout_box = ttk.Combobox(top, textvariable=self.layout,
                                  values=LAYOUT_LABELS,
                                  state="readonly", width=26)
        layout_box.pack(side="left")
        layout_box.bind("<<ComboboxSelected>>", lambda event: self.on_layout_change())

        row = ttk.Frame(self)
        row.pack(fill="x", padx=8)
        ttk.Label(row, text="Ir ao tempo global:").pack(side="left")
        self.seek = tk.StringVar(value="00:00:00")
        ttk.Entry(row, width=12, textvariable=self.seek).pack(side="left", padx=3)
        ttk.Button(row, text="Mostrar frame", command=self.show_frame).pack(side="left")
        ttk.Label(row, text="Mesa:").pack(side="left", padx=(14, 3))
        self.table = tk.StringVar(value="1")
        ttk.Combobox(row, textvariable=self.table, values=["1", "2", "3", "4"],
                     state="readonly", width=3).pack(side="left")
        ttk.Label(row, text="Marcar regiao:").pack(side="left", padx=4)
        self.field = tk.StringVar(value="cartas")
        ttk.Combobox(row, textvariable=self.field, values=["cartas", "saldo", "nick"],
                     state="readonly", width=8).pack(side="left")
        ttk.Button(row, text="Usar regioes do print", command=self.apply_profile).pack(side="left", padx=7)
        ttk.Button(row, text="Testar saldo", command=self.test_stack_frame).pack(side="left", padx=4)

        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=8, pady=5)
        ttk.Label(row2, text="Valor de 1 BB (em fichas):").pack(side="left")
        self.bb = tk.StringVar(value="1")
        ttk.Entry(row2, textvariable=self.bb, width=8).pack(side="left", padx=5)
        ttk.Button(row2, text="Salvar BB da mesa", command=self.set_bb).pack(side="left")
        ttk.Label(row2, text="Nick do jogador:").pack(side="left", padx=(14, 3))
        ttk.Entry(row2, textvariable=self.nick, width=18).pack(side="left")
        ttk.Button(row2, text="Verificar nick no frame", command=self.verify_nick_frame).pack(
            side="left", padx=7)
        ttk.Checkbutton(row2, text="OCR rapido", variable=self.quick).pack(side="left", padx=4)
        self.table.trace_add("write", lambda *_: self.on_table_change())

        changes = ttk.Frame(self)
        changes.pack(fill="x", padx=8, pady=(0, 3))
        ttk.Label(changes, text="Mudanca de mesas no tempo acima:").pack(side="left")
        ttk.Combobox(changes, textvariable=self.change_to, values=LAYOUT_LABELS[1:],
                     state="readonly", width=16).pack(side="left", padx=5)
        ttk.Button(changes, text="Registrar mudanca", command=self.add_layout_change).pack(side="left")
        ttk.Button(changes, text="Remover ultima", command=self.remove_layout_change).pack(
            side="left", padx=5)
        ttk.Button(changes, text="Conferir mesas no frame",
                   command=self.check_tables_frame).pack(side="left", padx=5)
        self.events_info = ttk.Label(changes, text="Sem mudancas registradas")
        self.events_info.pack(side="left", padx=8)

        self.canvas = tk.Canvas(self, width=VIEW_W, height=VIEW_H, background="#181818",
                                highlightthickness=0)
        self.canvas.pack(pady=2)
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        self.canvas.bind("<B1-Motion>", lambda event: self.draw(event))

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=5)
        ttk.Label(controls, text="Perda minima (BB):").pack(side="left")
        self.threshold = tk.StringVar(value="30")
        ttk.Entry(controls, textvariable=self.threshold, width=7).pack(side="left", padx=5)
        ttk.Button(controls, text="Salvar configuracao", command=self.save_cfg).pack(side="left")
        ttk.Button(controls, text="Abrir configuracao", command=self.load_cfg).pack(side="left", padx=5)
        ttk.Button(controls, text="ANALISAR VIDEO(S)", command=self.analyze).pack(side="left", padx=9)
        ttk.Button(controls, text="Salvar revisao", command=self.save_scan).pack(side="left")
        ttk.Button(controls, text="Abrir revisao", command=self.load_scan).pack(side="left", padx=4)
        ttk.Button(controls, text="Adicionar mao", command=self.add_manual).pack(side="left")
        self.status = ttk.Label(self, text="Aguardando videos e calibracao de cada mesa.")
        self.status.pack(fill="x", padx=8)

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=8, pady=4)
        columns = ("inicio", "fim", "mesa", "perda", "nick_status", "status", "conferido")
        self.grid = ttk.Treeview(table_frame, columns=columns, show="headings", height=4)
        for col, label, width in [
            ("inicio", "Inicio", 92), ("fim", "Fim", 92), ("mesa", "Mesa", 55),
            ("perda", "Perda BB estimada", 130), ("nick_status", "Nick OCR", 105),
            ("status", "Resultado OCR", 300), ("conferido", "Conferido", 90)]:
            self.grid.heading(col, text=label)
            self.grid.column(col, width=width)
        self.grid.pack(fill="both", expand=True)
        self.grid.bind("<<TreeviewSelect>>", self.select_candidate)

        edit = ttk.Frame(self)
        edit.pack(fill="x", padx=8, pady=5)
        ttk.Label(edit, text="Inicio:").pack(side="left")
        self.start_edit = tk.StringVar()
        ttk.Entry(edit, textvariable=self.start_edit, width=10).pack(side="left", padx=3)
        ttk.Label(edit, text="Fim:").pack(side="left")
        self.end_edit = tk.StringVar()
        ttk.Entry(edit, textvariable=self.end_edit, width=10).pack(side="left", padx=3)
        ttk.Label(edit, text="Perda (BB):").pack(side="left")
        self.loss_edit = tk.StringVar()
        ttk.Entry(edit, textvariable=self.loss_edit, width=9).pack(side="left", padx=3)
        ttk.Button(edit, text="Conferir/Salvar", command=self.confirm).pack(side="left", padx=6)
        ttk.Button(edit, text="Descartar", command=self.exclude).pack(side="left")
        ttk.Button(edit, text="Ver inicio", command=lambda: self.preview_edge("start")).pack(side="left", padx=5)
        ttk.Button(edit, text="Ver fim", command=lambda: self.preview_edge("end")).pack(side="left")
        ttk.Button(edit, text="EXPORTAR CONFERIDAS", command=self.export).pack(side="right")
        ttk.Label(self, text="Uso offline. Leituras de saldo por OCR sao estimativas; revise cada mao, rebuys e limites dos cortes.",
                  foreground="#9b571a").pack(padx=8, pady=2)

    def layout_id(self):
        try:
            when = parse_time(self.seek.get())
        except (ValueError, TypeError):
            when = 0
        return mode_at(when, self.layout.get(), self.timeline)

    def infer_table(self, x, y):
        mode = self.layout_id()
        for table in range(1, layout_count(mode) + 1):
            x1, y1, x2, y2 = layout_bounds(mode, table)
            if x1 <= x < x2 and y1 <= y < y2:
                return table
        return None

    def table_bounds(self, table):
        return layout_bounds(self.layout_id(), table)

    def refresh_changes(self):
        if not self.timeline:
            self.events_info.configure(text="Sem mudancas registradas")
        else:
            label = "; ".join(
                f"{fmt(entry['start'])} = {entry['layout']}"
                for entry in self.timeline[-2:])
            suffix = f" (+{len(self.timeline)-2})" if len(self.timeline) > 2 else ""
            self.events_info.configure(text=label + suffix)

    def add_layout_change(self):
        if not self.videos:
            messagebox.showwarning("Video", "Carregue o video antes de registrar mudancas.")
            return
        try:
            at = parse_time(self.seek.get())
            if not (0 < at < self.total):
                raise ValueError("O tempo precisa estar dentro do video e ser maior que zero.")
            target = self.change_to.get()
            layout_key(target)
            if target == "2 por 2":
                messagebox.showwarning(
                    "Mudanca para 2x2", "Uma reorganizacao 2x2 exige calibracao nova das caixas. "
                    "Use primeiro os modos de 1-4 mesas lado a lado ou confira as caixas manualmente.")
                return
            self.timeline = [x for x in self.timeline if abs(float(x["start"])-at) > .5]
            self.timeline.append({"start": at, "layout": target})
            self.timeline.sort(key=lambda x: float(x["start"]))
            self.refresh_changes()
            self.draw()
            self.tell(f"Mudanca registrada em {fmt(at)}: {target}.")
        except Exception as exc:
            messagebox.showerror("Mudanca de mesas", str(exc))

    def remove_layout_change(self):
        if self.timeline:
            item = self.timeline.pop()
            self.refresh_changes()
            self.draw()
            self.tell(f"Removida mudanca de {fmt(item['start'])}.")

    def check_tables_frame(self):
        if self.frame is None:
            messagebox.showwarning("Mesas", "Selecione o video e clique em Mostrar frame.")
            return
        mode = self.layout_id()
        found = [
            table for table in range(1, layout_count(mode) + 1)
            if table_visible(
                self.frame, layout_bounds(mode, table), strict=(mode == "auto4"))
        ]
        if found:
            summary = ", ".join(str(t) for t in found)
            messagebox.showinfo(
                "Mesas detectadas no frame",
                f"Disposicao: {mode}\nMesas com imagem detectada: {summary}\n\n"
                "Se as janelas mudaram de tamanho/posicao, registre a nova "
                "disposicao no instante indicado acima.")
        else:
            messagebox.showwarning(
                "Mesas nao detectadas",
                "Nenhuma janela foi reconhecida neste frame. "
                "Confira outro instante e use a disposicao correspondente.")

    def on_layout_change(self):
        # Perfis de 1-4 janelas lado a lado compartilham a mesma calibracao.
        mode = layout_key(self.layout.get())
        if mode == "grid2x2":
            if not messagebox.askyesno(
                    "Disposicao", "O layout 2x2 precisa recalibrar as caixas. Continuar?"):
                self.layout.set(LAYOUT_LABELS[0])
                return
            self.cfg = {str(t): {"bb": "1", "detector": "bright",
                                "bright_cutoff": 165, "min_bright": .18} for t in TABLES}
        elif not all(self.cfg[str(t)].get("hole") for t in TABLES):
            self.cfg = screenshot_profile()
        self.on_table_change()
        self.draw()
        self.tell("Layout inicial atualizado. Confira as regioes das mesas ativas.")

    def apply_profile(self):
        if self.layout_id() == "grid2x2":
            messagebox.showwarning("Disposicao", "Use um layout lado a lado para o perfil do print.")
            return
        self.cfg = screenshot_profile()
        self.on_table_change()
        self.draw()
        self.tell("Regioes do print restauradas. Confira o saldo e o nick.")

    def tell(self, msg):
        self.status.configure(text=msg)

    def add_videos(self):
        paths = filedialog.askopenfilenames(filetypes=[("MP4", "*.mp4"), ("Videos", "*.mp4 *.mkv *.mov")])
        if not paths:
            return
        try:
            found = [probe(path) for path in paths if path not in [v.path for v in self.videos]]
            self.videos.extend(found)
            self.videos.sort(key=lambda v: Path(v.path).name.lower())
            position = 0.
            for v in self.videos:
                v.start = position
                position += v.duration
            self.total = position
            self.info.configure(text=f"{len(self.videos)} arquivo(s) | {fmt(self.total)}")
            self.show_frame()
        except Exception as exc:
            messagebox.showerror("Video", str(exc))

    def clear_videos(self):
        self.videos = []
        self.total = 0
        self.frame = None
        self.candidates = []
        self.info.configure(text="Nenhum video carregado")
        self.timeline = []
        self.refresh_changes()
        self.refresh()
        self.draw()

    def show_frame(self):
        if not self.videos:
            return
        try:
            when = min(parse_time(self.seek.get()), max(0, self.total - .1))
            video, local = file_at(self.videos, when)
            cmd = [resource("ffmpeg"), "-hide_banner", "-loglevel", "error",
                   "-ss", str(local), "-i", video.path, "-frames:v", "1",
                   "-vf", f"scale={W}:{H}", "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
            kwargs = {"capture_output": True, "timeout": 35}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(cmd, **kwargs)
            if result.returncode:
                raise RuntimeError(result.stderr.decode("utf-8", "replace")[-500:])
            self.frame = Image.open(io.BytesIO(result.stdout)).convert("RGB")
            self.draw()
        except Exception as exc:
            messagebox.showerror("Previa", str(exc))

    def draw(self, event=None):
        self.canvas.delete("all")
        if self.frame is None:
            self.canvas.create_text(VIEW_W // 2, VIEW_H // 2, text="Adicione o video completo ou partes consecutivas",
                                    fill="white")
            return
        shown = self.frame.convert("RGB").resize((VIEW_W, VIEW_H))
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        mode = self.layout_id()
        if mode == "grid2x2":
            self.canvas.create_line(VIEW_W // 2, 0, VIEW_W // 2, VIEW_H,
                                    fill="#f7cd46", width=2)
            self.canvas.create_line(0, VIEW_H // 2, VIEW_W, VIEW_H // 2,
                                    fill="#f7cd46", width=2)
        else:
            for idx in range(1, layout_count(mode)):
                x = round(VIEW_W * idx / layout_count(mode))
                self.canvas.create_line(x, 0, x, VIEW_H, fill="#f7cd46", width=2)
        colors = {"hole": "#00ff91", "stack": "#00cfff", "nick": "#ec8fff"}
        for table in range(1, layout_count(mode) + 1):
            data = self.cfg[str(table)]
            for key in ("hole", "stack", "nick"):
                rect = data.get(key)
                if rect:
                    x1, y1, x2, y2 = layout_rect(rect, table, mode)
                    sx, sy = VIEW_W / W, VIEW_H / H
                    self.canvas.create_rectangle(x1*sx, y1*sy, x2*sx, y2*sy, outline=colors[key], width=2)
                    self.canvas.create_text(x1*sx, y1*sy, anchor="sw", text=f"M{table}: {key}", fill=colors[key])
        if self.selection_origin and event is not None:
            x1, y1 = self.selection_origin
            self.canvas.create_rectangle(x1, y1, event.x, event.y, outline="#ff6b4b", width=2)

    def mouse_down(self, event):
        if self.frame:
            self.selection_origin = (min(max(event.x, 0), VIEW_W),
                                     min(max(event.y, 0), VIEW_H))

    def mouse_up(self, event):
        if self.frame is None or not self.selection_origin:
            return
        x1, y1 = self.selection_origin
        x2, y2 = min(max(event.x, 0), VIEW_W), min(max(event.y, 0), VIEW_H)
        self.selection_origin = None
        x1, x2 = sorted((x1, x2))
        y1, y2 = sorted((y1, y2))
        if (x2-x1)*(y2-y1) < 60:
            self.draw()
            return
        rect = [round(x1 * W/VIEW_W), round(y1 * H/VIEW_H),
                round(x2 * W/VIEW_W), round(y2 * H/VIEW_H)]
        table = int(self.table.get())
        xmid, ymid = (rect[0]+rect[2])/2, (rect[1]+rect[3])/2
        inferred = self.infer_table(xmid, ymid)
        bounds = self.table_bounds(table)
        if inferred != table or not (bounds[0] <= rect[0] < rect[2] <= bounds[2] and
                                      bounds[1] <= rect[1] < rect[3] <= bounds[3]):
            messagebox.showwarning("Mesa", f"Esse retangulo parece estar na mesa {inferred}; voce selecionou a mesa {table}.")
            self.draw()
            return
        key = {"cartas": "hole", "saldo": "stack", "nick": "nick"}[self.field.get()]
        stored_rect = unmap_layout_rect(rect, table, self.layout_id())
        self.cfg[str(table)][key] = stored_rect
        if key == "hole":
            self.cfg[str(table)].pop("reference", None)
        self.cfg[str(table)]["detector"] = "bright"
        if key == "stack" and self.layout_id() != "grid2x2":
            # Mesmo posicionamento relativo em janelas 1-4, sem presumir 4 ativas.
            for destination, area in replicate_horizontal_rect(stored_rect, table).items():
                self.cfg[str(destination)]["stack"] = area
            self.tell("Saldo corrigido nas quatro mesas. Clique Testar saldo e salve a configuracao.")
        else:
            self.tell(f"Mesa {table}: regiao {key} ajustada.")
        self.draw()

    def test_stack_frame(self):
        """Verificacao manual da caixa de saldo para evitar OCR sobre nome/cartas."""
        if self.frame is None:
            messagebox.showwarning("Saldo", "Carregue um frame em que seu saldo esteja legivel.")
            return
        table = int(self.table.get())
        rect = self.cfg[str(table)].get("stack")
        tesseract = resource("tesseract")
        if not rect or not tesseract:
            messagebox.showwarning("Saldo", "Marque a regiao do saldo e confira o Tesseract.")
            return
        try:
            reading = ocr_stack(
                self.frame.crop(layout_rect(rect, table, self.layout_id())), tesseract)
            if reading is None:
                messagebox.showwarning(
                    "Saldo nao reconhecido",
                    "O programa nao leu um numero nesta caixa azul.\n"
                    "Escolha Marcar regiao -> saldo e desenhe exatamente sobre o valor do stack em BB.")
            else:
                messagebox.showinfo(
                    "Conferir saldo da mesa",
                    f"OCR da mesa {table}: {reading:g} BB\n\n"
                    "Compare com o numero mostrado no video. "
                    "Se diferente, redesenhe o retangulo azul.")
        except Exception as exc:
            messagebox.showerror("OCR saldo", str(exc))

    def verify_nick_frame(self):
        if self.frame is None:
            messagebox.showwarning("Nick", "Carregue um video e clique em Mostrar frame.")
            return
        nick = self.nick.get().strip()
        if not nick:
            messagebox.showwarning("Nick", "Preencha o nick do jogador.")
            return
        table = int(self.table.get())
        name_rect = self.cfg[str(table)].get("nick")
        if not name_rect:
            messagebox.showwarning("Nick", "Marque a regiao do nick da mesa selecionada.")
            return
        tesseract = resource("tesseract")
        if not tesseract:
            messagebox.showwarning("OCR", "Tesseract nao encontrado.")
            return
        try:
            values = read_nickname(
                self.frame.crop(layout_rect(name_rect, table, self.layout_id())), tesseract)
            verified = any(nickname_matches(value, nick) for value in values)
            displayed = " / ".join(values) or "(nao legivel)"
            if verified:
                self.tell(f"Mesa {table}: nick {nick} confirmado neste frame.")
                messagebox.showinfo("Nick reconhecido", f"Mesa {table}: {nick} confirmado.\nOCR: {displayed}")
            else:
                self.tell(f"Mesa {table}: OCR do nick inconclusivo. Ajuste a area roxa se necessario.")
                messagebox.showwarning(
                    "Nick nao confirmado",
                    f"Mesa {table}: o OCR nao confirmou {nick}.\nLeitura: {displayed}\n\n"
                    "Tente outro frame com o nome legivel ou ajuste a regiao roxa. "
                    "A analise por cartas continua disponivel.")
        except Exception as exc:
            messagebox.showerror("OCR de nick", str(exc))

    def set_empty(self):
        table = int(self.table.get())
        data = self.cfg[str(table)]
        if self.frame is None or not data.get("hole"):
            messagebox.showwarning("Referencia", "Marque antes a regiao das cartas do heroi.")
            return
        if not messagebox.askyesno("Confirmar referencia",
                                   f"Na mesa {table}, a regiao marcada das cartas do jogador esta VAZIA neste frame?"):
            return
        data["reference"] = image_png(
            self.frame.crop(layout_rect(data["hole"], table, self.layout_id())).convert("L"))
        data["detector"] = "reference"
        self.tell(f"Mesa {table}: referencia SEM cartas registrada.")
        self.draw()

    def set_bb(self):
        try:
            value = float(self.bb.get().replace(",", "."))
            if value <= 0:
                raise ValueError()
            self.cfg[self.table.get()]["bb"] = str(value)
            self.tell(f"Mesa {self.table.get()}: 1 BB = {value:g} fichas.")
        except ValueError:
            messagebox.showerror("BB", "Informe quanto vale 1 BB em fichas na tela.")

    def on_table_change(self):
        self.bb.set(str(self.cfg[self.table.get()].get("bb", 1)))

    def save_cfg(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Configuracao", "*.json")])
        if path:
            Path(path).write_text(json.dumps(
                {"layout": self.layout.get(), "nick": self.nick.get().strip(),
                 "quick": self.quick.get(), "timeline": self.timeline, "tables": self.cfg},
                indent=2), encoding="utf-8")
            self.tell("Configuracao salva.")

    def load_cfg(self):
        path = filedialog.askopenfilename(filetypes=[("Configuracao", "*.json")])
        if path:
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                settings = data.get("tables", data)
                self.cfg = {str(i): settings[str(i)] for i in TABLES}
                self.nick.set(data.get("nick", "~Pulgar~"))
                self.quick.set(bool(data.get("quick", True)))
                self.layout.set(data.get("layout", "2 por 2" if "tables" not in data else "4 lado a lado"))
                self.timeline = sorted(data.get("timeline", []), key=lambda x: float(x["start"]))
                self.refresh_changes()
                self.on_table_change()
                self.draw()
                self.tell("Configuracao carregada.")
            except Exception as exc:
                messagebox.showerror("Configuracao", str(exc))

    def add_manual(self):
        if not self.videos:
            messagebox.showwarning("Videos", "Adicione o video antes.")
            return
        try:
            start = parse_time(self.seek.get())
        except ValueError:
            start = 0
        mode = mode_at(start, self.layout.get(), self.timeline)
        table = int(self.table.get())
        if table > layout_count(mode):
            messagebox.showwarning("Mesa", "A mesa selecionada nao existe nesse instante.")
            return
        next_change = min(
            [float(e["start"]) for e in self.timeline if float(e["start"]) > start]
            or [self.total])
        end = min(start + 60, self.total, next_change)
        if end <= start:
            messagebox.showwarning("Tempo", "Escolha outro instante.")
            return
        self.candidates.append(Candidate(start, end, table, None, None, None,
                                         "ADICIONADA MANUALMENTE - REVISAR",
                                         nick=self.nick.get().strip(),
                                         layout=("horizontal4" if mode == "auto4" else mode)))
        self.refresh()
        self.grid.selection_set(str(len(self.candidates)-1))
        self.grid.see(str(len(self.candidates)-1))
        self.select_candidate()

    def save_scan(self):
        if not self.videos:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Revisao visual", "*.json")])
        if not path:
            return
        payload = {"version": 3, "videos": [asdict(v) for v in self.videos],
                   "layout": self.layout.get(), "config": self.cfg, "threshold": self.threshold.get(),
                   "nick": self.nick.get().strip(), "quick": self.quick.get(),
                   "timeline": self.timeline,
                   "candidates": [asdict(c) for c in self.candidates]}
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.tell("Revisao e recortes salvos em " + path)
        except Exception as exc:
            messagebox.showerror("Salvar", str(exc))

    def load_scan(self):
        path = filedialog.askopenfilename(filetypes=[("Revisao visual", "*.json")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            from cortador import Video
            videos = [Video(**entry) for entry in data["videos"]]
            missing = [v.path for v in videos if not Path(v.path).is_file()]
            if missing:
                raise FileNotFoundError("Videos nao encontrados:\n" + "\n".join(missing))
            self.videos = videos
            self.total = sum(v.duration for v in videos)
            old_layout = layout_key(data.get("layout", "4 lado a lado"))
            candidates = []
            for entry in data["candidates"]:
                entry = dict(entry)
                if "layout" not in entry:
                    entry["layout"] = "horizontal4" if old_layout == "auto4" else old_layout
                candidates.append(Candidate(**entry))
            self.candidates = candidates
            self.cfg = data.get("config", self.cfg)
            self.layout.set(data.get("layout", "2 por 2"))
            self.timeline = sorted(data.get("timeline", []), key=lambda x: float(x["start"]))
            self.refresh_changes()
            self.nick.set(data.get("nick", "~Pulgar~"))
            self.quick.set(bool(data.get("quick", True)))
            self.threshold.set(str(data.get("threshold", 30)))
            self.info.configure(text=f"{len(videos)} arquivo(s) | {fmt(self.total)}")
            self.on_table_change()
            self.refresh()
            self.show_frame()
            self.tell(f"Revisao aberta: {len(self.candidates)} candidatas. Confira e exporte.")
        except Exception as exc:
            messagebox.showerror("Abrir revisao", str(exc))

    def analyze(self):
        if self.busy:
            return
        if not self.videos:
            messagebox.showwarning("Videos", "Adicione o video original ou as partes MP4.")
            return
        try:
            threshold = float(self.threshold.get().replace(",", "."))
            if threshold <= 0:
                raise ValueError("Limite BB precisa ser positivo.")
            if not self.nick.get().strip():
                raise ValueError("Preencha o nick do jogador principal.")
            modes = {layout_key(self.layout.get())}
            modes.update(layout_key(e["layout"]) for e in self.timeline)
            required = set()
            for mode in modes:
                required.update(range(1, layout_count(mode) + 1))
            for table in sorted(required):
                data = self.cfg[str(table)]
                for key in ("hole", "stack"):
                    if not data.get(key):
                        raise ValueError(f"Falta regiao de {key} na mesa {table}.")
                if data.get("detector") == "reference" and not data.get("reference"):
                    raise ValueError(f"Mesa {table}: falta referencia manual.")
                roi_tuple(data["hole"])
                roi_tuple(data["stack"])
                if not data.get("bb"):
                    raise ValueError(f"Informe BB da mesa {table}.")
            if not resource("tesseract"):
                raise ValueError("Instale Tesseract OCR e coloque tesseract.exe no PATH.")
        except Exception as exc:
            messagebox.showerror("Configuracao", str(exc))
            return
        self.busy = True
        self.tell("Iniciando analise visual offline...")
        cfg = json.loads(json.dumps(self.cfg))
        videos = self.videos[:]
        hero_nick = self.nick.get().strip()
        quick = self.quick.get()
        initial_layout = self.layout.get()
        events = [entry.copy() for entry in self.timeline]
        def worker():
            try:
                results = scan_videos(videos, cfg, threshold,
                                      lambda msg: self.after(0, lambda m=msg: self.tell(m)),
                                      hero_nick=hero_nick, quick=quick,
                                      initial_layout=initial_layout, events=events)
                self.after(0, lambda: self.finished(results))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self.failed(e))
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, results):
        self.candidates = results
        self.busy = False
        self.refresh()
        self.tell(f"Analise concluida: {len(results)} candidatas / inconclusivas. Salve revisao e confira.")
        messagebox.showinfo("Concluido",
                            f"{len(results)} ocorrencias encontradas. "
                            "As perdas sao ESTIMADAS por OCR; confirme as fichas e os limites.")

    def failed(self, error):
        self.busy = False
        messagebox.showerror("Analise interrompida", error)
        self.tell("Erro na analise: " + error[:120])

    def refresh(self):
        for item in self.grid.get_children():
            self.grid.delete(item)
        for i, c in enumerate(self.candidates):
            if c.excluded:
                continue
            self.grid.insert("", "end", iid=str(i), values=(
                fmt(c.start), fmt(c.end), c.table,
                f"{c.loss_bb:.2f}" if c.loss_bb is not None else "?",
                "OK" if c.nick_verified else "Revisar",
                c.status, "SIM" if c.confirmed else "NAO"))

    def selected(self):
        item = self.grid.selection()
        return int(item[0]) if item else None

    def select_candidate(self, *_):
        idx = self.selected()
        if idx is None:
            return
        c = self.candidates[idx]
        self.start_edit.set(fmt(c.start))
        self.end_edit.set(fmt(c.end))
        self.loss_edit.set("" if c.loss_bb is None else str(c.loss_bb))

    def preview_edge(self, field):
        idx = self.selected()
        if idx is None:
            return
        c = self.candidates[idx]
        self.seek.set(fmt(c.start if field == "start" else c.end))
        self.table.set(str(c.table))
        self.show_frame()

    def confirm(self):
        idx = self.selected()
        if idx is None:
            return
        try:
            c = self.candidates[idx]
            st, en = parse_time(self.start_edit.get()), parse_time(self.end_edit.get())
            loss = float(self.loss_edit.get().replace(",", "."))
            if not (0 <= st < en <= self.total) or loss <= 0:
                raise ValueError("Confira inicio, fim e perda.")
            mode_start = mode_at(st + 0.01, self.layout.get(), self.timeline)
            mode_end = mode_at(max(st + 0.01, en - 0.01), self.layout.get(), self.timeline)
            if mode_start != mode_end:
                raise ValueError(
                    "A mao atravessa uma mudanca de disposicao. "
                    "Ajuste inicio/fim ou divida manualmente o trecho.")
            if c.table > layout_count(mode_start):
                raise ValueError("A mesa selecionada nao existe nesse instante.")
            c.layout = "horizontal4" if mode_start == "auto4" else mode_start
            c.start, c.end, c.loss_bb = st, en, loss
            c.status = "VALOR E LIMITES CONFERIDOS"
            c.confirmed = True
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Conferencia", str(exc))

    def exclude(self):
        idx = self.selected()
        if idx is not None:
            self.candidates[idx].excluded = True
            self.refresh()

    def export(self):
        if self.busy:
            return
        try:
            threshold = float(self.threshold.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("BB", "Limite BB invalido.")
            return
        eligible = [c for c in self.candidates if c.confirmed and not c.excluded and
                    loss_reaches_threshold(c.loss_bb, threshold)]
        if not eligible:
            messagebox.showinfo("Exportacao",
                                "Nenhuma mao com perda >= limite e dados confirmados.")
            return
        folder = filedialog.askdirectory(title="Pasta dos MP4 para o instrutor")
        if not folder:
            return
        self.busy = True
        self.tell(f"Exportando {len(eligible)} maos conferidas...")
        hero_nick = self.nick.get().strip()
        def worker():
            logs = []
            for i, c in enumerate(eligible, 1):
                filename = f"mao_{i:03}_mesa{c.table}_perda_{c.loss_bb:.1f}BB.mp4"
                status = "OK"
                try:
                    clip = Clip(c.start, c.end, c.table, c.loss_bb, "Video OCR",
                                "Video", "", True)
                    export_clip(self.videos, clip, Path(folder) / filename,
                                resource("ffmpeg"), layout=c.layout)
                except Exception as exc:
                    status = "ERRO: " + str(exc)[-180:]
                logs.append({"arquivo": filename, "nick": c.nick or hero_nick,
                             "nick_ocr_confirmado": c.nick_verified, "mesa": c.table,
                             "disposicao": c.layout,
                             "inicio": fmt(c.start), "fim": fmt(c.end),
                             "perda_bb_conferida": c.loss_bb, "status": status})
                self.after(0, lambda j=i, s=status: self.tell(f"Exportado {j}/{len(eligible)}: {s}"))
            with open(Path(folder)/"indice_das_maos.csv", "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(logs[0]), delimiter=";")
                writer.writeheader()
                writer.writerows(logs)
            def done():
                self.busy = False
                good = sum(x["status"] == "OK" for x in logs)
                self.tell(f"Finalizado {good}/{len(logs)}. Pasta: {folder}")
                messagebox.showinfo("Exportacao", f"{good}/{len(logs)} MP4 gerados.\nIndice CSV em {folder}")
            self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    GUI().mainloop()
