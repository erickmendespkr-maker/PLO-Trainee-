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
LAYOUT_LABELS = ("Automatico (1 a 4 mesas)", "1 mesa", "2 lado a lado",
                 "3 lado a lado", "4 lado a lado", "2 por 2")


def layout_key(label):
    """Converte selecao visual para layout tecnico."""
    lookups = {
        "Auto (ate 4, slots fixos)": "auto4",
        "Automatico (1 a 4 mesas)": "auto4", "1 mesa": "horizontal1",
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


def vertical_seam_strength(frame, x):
    """Fração de alturas com borda vertical perto de um separador entre mesas."""
    if not (10 <= x <= W - 10):
        return 0.
    img = frame if frame.mode == "L" else frame.convert("L")
    px = img.load()
    evidence = 0
    sampled = 0
    for y in range(32, H - 25, 14):
        sampled += 1
        values = [px[x + dx, y] for dx in (-8, -6, -4, -2, 0, 2, 4, 6, 8)]
        maximum = max(abs(values[i] - values[i+1]) for i in range(len(values)-1))
        if maximum >= 18:
            evidence += 1
    return evidence / max(sampled, 1)


def infer_horizontal_layout(frame, previous=None):
    """Inferencia conservadora de 1 a 4 colunas pela repeticao visual das mesas.

    Compara a estrutura em partes equivalentes de cada janela; nao usa OCR
    em cada frame. Se o resultado for ambiguo, devolve None e nao inventa
    uma quantidade. "auto4" significa 4 slots fixos (mesmo com vazios).
    """
    gray = frame.convert("L")
    scores = {}
    seams_by_mode = {}
    seam_cache = {}

    # Mesas que fecham sem rearranjo deixam um slot inteiro vazio. Se esse
    # vazio for confundido com "1 mesa ampliada", o crop fica errado.
    slot4 = []
    for table in TABLES:
        bounds = layout_bounds("horizontal4", table)
        patch = gray.crop(bounds).resize((24, 36))
        textured = ImageStat.Stat(patch).stddev[0] >= 9
        slot4.append(textured)
    # Prioriza a grade original quando restam 1-3 janelas e os demais
    # quadrantes sao uniformes. Uma mesa ampliada costuma ocupar >1 slot.
    if 1 <= sum(slot4) <= 3:
        uniform_blanks = all(
            ImageStat.Stat(gray.crop(layout_bounds("horizontal4", i+1))
                          .resize((24, 36))).stddev[0] < 5
            for i, present in enumerate(slot4) if not present)
        # Delimitador alto ao lado da janela ativa impede classificar
        # erroneamente uma faixa homogenea de uma mesa ampliada.
        seams = [vertical_seam_strength(gray, x) for x in (240, 480, 720)]
        if uniform_blanks and max(seams) >= .35:
            return "horizontal4", .85, {"horizontal4": .85}
    for count in (2, 3, 4):
        mode = f"horizontal{count}"
        slots = []
        for table in range(1, count + 1):
            bounds = layout_bounds(mode, table)
            if not table_visible(gray, bounds, strict=False):
                continue
            part = gray.crop(bounds).resize((32, 48))
            if ImageStat.Stat(part).stddev[0] < 7:
                continue
            slots.append((table, part))
        boundary_scores = []
        for index in range(1, count):
            separator = round(W * index / count)
            if separator not in seam_cache:
                seam_cache[separator] = vertical_seam_strength(gray, separator)
            boundary_scores.append(seam_cache[separator])
        seam = statistics.mean(boundary_scores)
        seams_by_mode[mode] = seam
        if len(slots) < 2:
            continue
        similarities = []
        for i, (_, img1) in enumerate(slots):
            for _, img2 in slots[i+1:]:
                difference = ImageStat.Stat(ImageChops.difference(img1, img2)).mean[0]
                similarities.append(max(0., 1. - difference / 75.))
        consistency = statistics.median(similarities)
        # Penalizar discordancia grande entre as varias janelas.
        inconsistency = (max(similarities) - min(similarities)) if len(similarities) > 2 else 0.
        coverage = len(slots) / count
        scores[mode] = (consistency - .18 * inconsistency +
                        .08 * coverage + .025 * (count - 2) +
                        .12 * seam)
    # Sem divisorias verticais, a semelhanca entre duas metades da mesma
    # mesa unica pode parecer falsamente duas mesas repetidas.
    if scores and max(seams_by_mode.get(mode, 0.) for mode in scores) < .14:
        if table_visible(gray, layout_bounds("horizontal1", 1), strict=False):
            return "horizontal1", .70, scores
    if scores:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        mode, score = ordered[0]
        runner = ordered[1][1] if len(ordered) > 1 else 0.
        if previous in scores and scores[previous] >= score - .035:
            mode = previous
            score = scores[mode]
        if score >= .68 and (mode == previous or score - runner >= .045):
            return mode, round(score, 3), scores

    # Uma unica mesa ampliada e o fallback somente quando nao ha evidencia
    # de duas ou mais janelas repetidas. Caso contrario, manter inconclusivo.
    if not scores or max(scores.values()) < .58:
        if table_visible(gray, layout_bounds("horizontal1", 1), strict=False):
            return "horizontal1", .70, scores
    return None, 0., scores


class AutoLayoutTracker:
    """Confirmacao temporal: evita mudar layout por animacoes de uma jogada."""
    def __init__(self):
        self.stable = None
        self.suspected = None
        self.streak = 0

    def observe(self, frame, observation=None):
        # Aceita resultado ja calculado para que o diagnostico nao duplique
        # o custo da inferencia. O scanner normal segue inalterado.
        if observation is None:
            observation = infer_horizontal_layout(frame, self.stable)
        guess, confidence, _scores = observation
        if guess is None:
            self.suspected = None
            self.streak = 0
            # Ambiguidade nao produz perda valida.
            return self.stable, False, "indefinido"
        if guess == self.stable:
            self.suspected = None
            self.streak = 0
            return self.stable, True, "estavel"
        if self.suspected != guess:
            self.suspected = guess
            self.streak = 1
        else:
            self.streak += 1
        if self.streak >= 3:
            self.stable = guess
            self.suspected = None
            self.streak = 0
            return self.stable, True, "alterado"
        return self.stable, False, "confirmando"


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


def native_stack_crop(videos, second, rect, ffmpeg):
    """Extrai a regiao do saldo do MP4 original, sem reduzir para 960x540.

    'rect' usa coordenadas normalizadas 960x540 e deve corresponder ao
    layout da mesa naquele instante.
    """
    video, local = file_at(videos, max(0.0, second))
    x1, y1, x2, y2 = roi_tuple(rect)
    x = max(0, round(x1 * video.width / W))
    y = max(0, round(y1 * video.height / H))
    right = min(video.width, round(x2 * video.width / W))
    bottom = min(video.height, round(y2 * video.height / H))
    width, height = right - x, bottom - y
    if width < 4 or height < 4:
        raise ValueError("Area do saldo muito pequena para OCR nativo.")
    command = [ffmpeg, "-hide_banner", "-loglevel", "error",
               "-ss", f"{local:.3f}", "-i", video.path, "-frames:v", "1",
               "-vf", f"crop={width}:{height}:{x}:{y}",
               "-f", "image2pipe", "-vcodec", "png", "pipe:1"]
    proc = subprocess.run(
        command, capture_output=True, timeout=40,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if proc.returncode != 0 or not proc.stdout:
        details = proc.stderr.decode("utf-8", "replace")[-350:]
        raise RuntimeError("Nao foi possivel extrair saldo nativo: " + details)
    with Image.open(io.BytesIO(proc.stdout)) as img:
        return img.convert("RGB").copy()


def stack_ocr_variants(img):
    """Preserva os detalhes de fontes pequenas e gera polaridades diferentes."""
    if img.width < 4 or img.height < 4:
        return []
    factor = max(4, min(10, round(520 / max(img.width, 1))))
    enlarged = img.convert("L").resize(
        (img.width * factor, img.height * factor), Image.Resampling.LANCZOS)
    base = ImageOps.autocontrast(enlarged, cutoff=1)
    base = ImageOps.expand(base, border=26, fill=255)
    # Evite destruir a antialiasing fina dos digitos antes de OCR.
    high = ImageEnhance.Contrast(base).enhance(2.2)
    return [
        ("cinza", base),
        ("inverso", ImageOps.invert(base)),
        ("alto_contraste", high),
        ("binario_claro", high.point(lambda p: 255 if p >= 140 else 0)),
        ("binario_escuro", ImageOps.invert(high).point(
            lambda p: 255 if p >= 140 else 0)),
    ]


def read_stack_diagnostics(img, tesseract, quick=False):
    """Retorna numero conservador e leituras brutas para explicar falhas."""
    variants = stack_ocr_variants(img)
    if not variants:
        return None, []
    # No modo rapido, a escala de cinza com bordas vem antes da binarizacao.
    jobs = [(variants[0], 7), (variants[1], 7)]
    if not quick:
        jobs.extend([((name, image), psm)
                     for (name, image) in variants[2:] for psm in (7, 13)])
    results = []
    parsed = []
    with tempfile.TemporaryDirectory(prefix="plo_stack_") as folder:
        for index, ((name, prepared), psm) in enumerate(jobs):
            filepath = Path(folder) / f"ocr_{index}.png"
            prepared.save(filepath)
            cmd = [tesseract, str(filepath), "stdout", "--psm", str(psm),
                   "-c", "tessedit_char_whitelist=0123456789,."]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      errors="replace", timeout=20,
                                      creationflags=getattr(
                                          subprocess, "CREATE_NO_WINDOW", 0))
                raw = proc.stdout.strip() if proc.returncode == 0 else ""
            except (OSError, subprocess.SubprocessError) as exc:
                raw = f"ERRO: {exc}"
            amount = parse_stack(raw)
            results.append((name, psm, raw, amount))
            if amount is not None:
                parsed.append(amount)
                if quick:
                    return amount, results
    if not parsed:
        return None, results
    # Diferentes algoritmos na MESMA imagem so confirmam formato, nao
    # confirmam a perda: essa confirmacao exige frames diferentes.
    choices = []
    for value in parsed:
        matches = sum(abs(value - other) <= max(1., value * .01)
                      for other in parsed)
        choices.append((matches, value))
    choices.sort(key=lambda item: item[0], reverse=True)
    votes, best = choices[0]
    if votes >= 2:
        return statistics.median(
            [value for value in parsed if abs(value - best) <= max(1., best * .01)]
        ), results
    # Nao aceitar um unico numero isolado entre multiplos filtros.
    return (parsed[0] if len(parsed) == 1 else None), results


def parse_stack(value):
    # A regiao do OCR deve conter SOMENTE o saldo em fichas do jogador.
    # Nunca junte numeros separados por espacos: isso produzia leituras
    # falsas como "154020" a partir de varios textos sobrepostos.
    candidates = re.findall(r"\d+(?:[.,]\d+)*", value)
    # A caixa do saldo deve conter um unico numero. Dois tokens indicam
    # captura de outro campo da mesa e nao servem para exportacao automatica.
    if len(candidates) != 1:
        return None
    token = candidates[0].rstrip(".,")
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
    value, _ = read_stack_diagnostics(img, tesseract, quick=quick)
    return value



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


MAX_STACK_BB = 5000.0  # Teto amplo de seguranca contra OCR absurdo, nao um buy-in fixo.


def stack_median(images, tesseract, quick=False, bb=1):
    """Le saldos consistentes; modo rapido usa ate duas imagens por lado."""
    values = []
    samples = images[-2:] if quick else images
    for sample in samples:
        try:
            v = ocr_stack(sample, tesseract, quick=quick)
            if v is not None and 0 <= v / bb <= MAX_STACK_BB:
                values.append(v)
        except (subprocess.SubprocessError, OSError):
            continue
    if quick and not values and len(images) > 2:
        # Salvaguarda para leitura ausente: terceira imagem em modo detalhado.
        try:
            retry = ocr_stack(images[0], tesseract, quick=False)
            if retry is not None and 0 <= retry / bb <= MAX_STACK_BB:
                values.append(retry)
        except (subprocess.SubprocessError, OSError):
            pass
    if not values:
        return None, 0
    middle = statistics.median(values)
    # Variacoes acima de 1% entre leituras sao suspeitas. Em BB pequenos,
    # permitir ate 1 BB de variacao por arredondamento na tela.
    consistent = [x for x in values if abs(x - middle) <= max(bb, middle * .01)]
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
    auto_verified: bool = False
    reliability: str = ""


def eligible_losses(candidates, threshold, automatic_only=False):
    """So encaminha a exportacao perdas confirmadas ou OCR consistente."""
    return [c for c in candidates if not c.excluded and
            (c.auto_verified if automatic_only else
             (c.confirmed or c.auto_verified)) and
            loss_reaches_threshold(c.loss_bb, threshold)]


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
        self.scan_mode = "horizontal4"
        self.active = False
        self.on_count = 0
        self.off_count = 0
        self.on_start = 0.
        self.off_start = 0.
        self.start_at = 0.
        self.before = []
        self.before_times = []
        self.empty_frames = deque(maxlen=9)
        self.pending = None
        self.results = []

    def feed(self, t, occupied, stack_img, table, bb, threshold, tesseract,
             quick=False, native_reader=None):
        if not self.active:
            if self.pending is not None:
                if not occupied and len(self.pending["after"]) < 3:
                    self.pending["after"].append(stack_img.copy())
                    self.pending["after_times"].append(t)
                if len(self.pending["after"]) >= 3 or occupied:
                    self.finish(table, bb, threshold, tesseract, quick=quick,
                                native_reader=native_reader)
            if occupied:
                if self.on_count == 0:
                    self.on_start = t
                self.on_count += 1
                if self.on_count >= 2:
                    self.active = True
                    self.start_at = self.on_start
                    # O saldo anterior a distribuicao e melhor que o saldo no flop.
                    samples = list(self.empty_frames)[-3:]
                    self.before = [im.copy() for _at, im in samples]
                    self.before_times = [at for at, _im in samples]
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
                                "before": self.before[:], "before_times": self.before_times[:],
                                "after": [stack_img.copy()], "after_times": [t]}
                self.off_count = 0
                self.empty_frames.clear()

    def finish(self, table, bb, threshold, tesseract, quick=False,
               native_reader=None):
        data = self.pending
        self.pending = None
        if not data:
            return
        pre, n_pre = stack_median(data["before"], tesseract, quick=quick, bb=bb)
        post, n_post = stack_median(data["after"], tesseract, quick=quick, bb=bb)

        loss = None if pre is None or post is None else net_loss_bb(pre, post, bb)
        if quick and (loss_reaches_threshold(loss, threshold) or
                      (loss is None and (pre is not None or post is not None))):
            # Rechecar apenas possiveis perdas ou leitura parcialmente legivel.
            # Se ambos os lados sao ilegíveis, evitar ate 12 chamadas extras
            # por mao: a ROI provavelmente precisa ser corrigida.
            detail_pre, n_dp = stack_median(data["before"], tesseract, quick=False, bb=bb)
            detail_post, n_da = stack_median(data["after"], tesseract, quick=False, bb=bb)
            if detail_pre is not None and detail_post is not None:
                pre, post = detail_pre, detail_post
                n_pre, n_post = n_dp, n_da
                loss = net_loss_bb(pre, post, bb)
            else:
                # Resultado do passe rapido sozinho nunca e auto verificado.
                n_pre, n_post = 0, 0

        if native_reader is not None and (
                loss is None or n_pre < 2 or n_post < 2):
            # Segundo caminho: os frames originais preservam os digitos
            # que somem quando o video inteiro e reduzido para 960x540.
            # So ler 2-3 amostras por lado se o OCR leve falhar.
            original_samples = {}
            for name in ("before", "after"):
                images = []
                for sample_at in data.get(name + "_times", [])[-3:]:
                    try:
                        images.append(native_reader(
                            sample_at, table, self.scan_mode))
                    except (OSError, ValueError, RuntimeError,
                            subprocess.SubprocessError):
                        pass
                original_samples[name] = images
            # O fallback usa ate duas amostras e evita dezenas de OCR
            # detalhados por mao. O usuario pode diagnosticar a ROI
            # com todos os filtros no botao Testar saldo.
            n_before, c_before = stack_median(
                original_samples["before"], tesseract, quick=True, bb=bb)
            n_after, c_after = stack_median(
                original_samples["after"], tesseract, quick=True, bb=bb)
            if n_before is not None and n_after is not None:
                pre, post = n_before, n_after
                n_pre, n_post = c_before, c_after
                loss = net_loss_bb(pre, post, bb)
            elif loss is None:
                pre, post = n_before, n_after
                n_pre, n_post = c_before, c_after

        if loss is None:
            self.results.append(Candidate(
                max(0, data["start"] - 5), data["end"] + 5, table,
                None, pre, post, "INCONCLUSIVO - SALDO NAO LIDO",
                layout=self.layout, reliability="OCR ausente"))
            return

        if not loss_reaches_threshold(loss, threshold):
            # Mãos ganhas, sem perda ou com perda < limite nao entram.
            return

        # Leitura coerente de 2 amostras antes e 2 depois e exigida para
        # exportacao automatica. Valores absurdos ja foram filtrados.
        strong = (n_pre >= 2 and n_post >= 2 and
                  0 <= post / bb <= MAX_STACK_BB and
                  0 <= pre / bb <= MAX_STACK_BB)
        status = ("PERDA >= LIMITE - OCR CONSISTENTE" if strong else
                  "POSSIVEL PERDA >= LIMITE - OCR FRACO")
        self.results.append(Candidate(
            max(0, data["start"] - 5), data["end"] + 5, table,
            round(loss, 2), pre, post, status,
            layout=self.layout, auto_verified=strong,
            reliability=f"antes {n_pre} leituras / depois {n_post} leituras"))


def scan_videos(videos, config, threshold, progress, hero_nick="~Pulgar~",
                quick=True, initial_layout="Automatico (1 a 4 mesas)", events=None,
                detected_events=None):
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
    # O modo Auto pode assumir qualquer uma das 4 quantidades em qualquer trecho.
    if "auto4" in all_modes:
        all_modes.update(f"horizontal{i}" for i in TABLES)
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
    auto_detector = AutoLayoutTracker()
    no_detection_reported = False
    unsafe_since = None
    unsafe_frames = 0
    # Um frame ambiguo isolado nao deve encerrar a mao. O trecho
    # interrompido so e consolidado apos alguns frames ou troca confirmada.
    unsafe_grace_frames = 6

    def read_native_at(global_second, table, scan_mode):
        roi = table_cfg[(scan_mode, table)]["stack"]
        return native_stack_crop(videos, global_second, roi, ffmpeg)

    def close_state(table, end_time, reason):
        state = states.pop(table, None)
        if state is None:
            return
        key = (state.scan_mode, table)
        cfg = table_cfg.get(key)
        if state.pending and cfg is not None:
            state.finish(table, cfg["bb"], threshold, tesseract, quick=quick,
                         native_reader=read_native_at)
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
                requested_mode = mode_at(t, initial_layout, events)
                if requested_mode == "auto4":
                    mode, safe_to_scan, situation = auto_detector.observe(frame)
                    if not safe_to_scan:
                        # Nao ler saldo nesta imagem: houve possivel reorganizacao.
                        # Preserva as maos durante pequenas animacoes e alertas,
                        # ao contrario da versao anterior que perdia o estado
                        # imediatamente apos um unico frame ambiguo.
                        if unsafe_since is None:
                            unsafe_since = t
                        unsafe_frames += 1
                        if states and unsafe_frames >= unsafe_grace_frames:
                            for table in list(states):
                                close_state(table, unsafe_since,
                                            "INCONCLUSIVO - LAYOUT INDEFINIDO")
                            states = {}
                            segment_start = t
                        if situation == "indefinido" and not no_detection_reported and n >= 10:
                            progress(f"{fmt(t)}: layout indefinido; "
                                     "aguardando frames estaveis.")
                            no_detection_reported = True
                        n += 1
                        continue
                else:
                    mode = requested_mode
                    auto_detector = AutoLayoutTracker()
                if mode != active_mode:
                    if active_mode is not None:
                        boundary = unsafe_since if unsafe_since is not None else t
                        for table in list(states):
                            close_state(table, boundary,
                                        "INCONCLUSIVO - MESA MUDOU DE LUGAR")
                        segment_start = t
                    else:
                        segment_start = t
                    active_mode = mode
                    states = {}
                    missing_counts = {table: 0 for table in TABLES}
                    if detected_events is not None:
                        detected_events.append({"start": round(t, 2), "layout": mode})
                    progress(f"{fmt(t)}: disposicao detectada {mode}; "
                             f"{layout_count(mode)} posicoes possiveis")

                # Periodos curtos inconclusivos nao encerram uma mao; se a
                # disposicao mudou, ela ja foi fechada no primeiro frame suspeito.
                unsafe_since = None
                unsafe_frames = 0
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
                                       cfg["bb"], threshold, tesseract, quick=quick,
                                       native_reader=read_native_at)
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
        candidate.nick_verified = nick_verified.get(
            (candidate.layout, candidate.table), False)
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
        self.detected_timeline = []
        self.preview_when = None
        self.preview_auto_mode = None
        self.preview_confidence = 0.
        self.nick = tk.StringVar(value="~Pulgar~")
        self.quick = tk.BooleanVar(value=True)
        self.auto_export = tk.BooleanVar(value=True)
        self.show_inconclusive = tk.BooleanVar(value=False)
        self.auto_export_folder = None
        self.cfg = screenshot_profile()
        self._ui()
        self.draw()
        self.tell("Modo Automatico: detecta 1-4 mesas e mudanças durante o video.")

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
        ttk.Checkbutton(row2, text="Gerar MP4 automaticos",
                        variable=self.auto_export).pack(side="left", padx=6)
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
        ttk.Checkbutton(controls, text="Mostrar OCR inconclusivo",
                        variable=self.show_inconclusive,
                        command=self.refresh).pack(side="left", padx=8)
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
        ttk.Button(edit, text="EXPORTAR PERDAS", command=self.export).pack(side="right")
        ttk.Label(self, text="Uso offline. Leituras de saldo por OCR sao estimativas; revise cada mao, rebuys e limites dos cortes.",
                  foreground="#9b571a").pack(padx=8, pady=2)

    def effective_layout_at(self, when):
        """Layout manual tem prioridade, senao usa historico detectado ou previa."""
        current = mode_at(when, self.layout.get(), self.timeline)
        if current != "auto4":
            return current
        if (self.preview_when is not None and
                abs(self.preview_when - when) < 1.2 and self.preview_auto_mode):
            return self.preview_auto_mode
        known = [e for e in self.detected_timeline if e["start"] <= when]
        if known:
            return known[-1]["layout"]
        return "horizontal4"  # Apenas grade da previa; scanner nao assume 4.

    def layout_id(self):
        try:
            when = parse_time(self.seek.get())
        except (ValueError, TypeError):
            when = 0
        return self.effective_layout_at(when)

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
        try:
            when = parse_time(self.seek.get())
        except (ValueError, TypeError):
            when = 0
        is_auto = mode_at(when, self.layout.get(), self.timeline) == "auto4"
        if is_auto:
            mode, confidence, scores = infer_horizontal_layout(self.frame)
            if mode is None:
                ranking = ", ".join(
                    f"{name}: {value:.2f}"
                    for name, value in sorted(scores.items(),
                                              key=lambda item: -item[1]))
                messagebox.showwarning(
                    "Deteccao inconclusiva",
                    "Nao foi possivel identificar a quantidade com seguranca "
                    "neste frame. Tente outro instante.\n\n"
                    f"Pontuacoes: {ranking or 'sem mesas repetidas reconhecidas'}")
                return
        else:
            mode, confidence = self.layout_id(), None
        found = [
            table for table in range(1, layout_count(mode) + 1)
            if table_visible(self.frame, layout_bounds(mode, table), strict=False)
        ]
        summary = ", ".join(str(t) for t in found) if found else "nenhuma"
        certainty = (f" | confianca estimada: {confidence:.2f}"
                     if confidence is not None else "")
        messagebox.showinfo(
            "Mesas detectadas no frame",
            f"Disposicao: {mode}{certainty}\n"
            f"Mesas com imagem detectada: {summary}\n\n"
            "A deteccao automatica e experimental; confirme visualmente "
            "se as linhas amarelas correspondem as janelas.")

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
            self.detected_timeline = []
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
        self.detected_timeline = []
        self.preview_when = None
        self.preview_auto_mode = None
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
            self.preview_when = when
            if mode_at(when, self.layout.get(), self.timeline) == "auto4":
                auto, confidence, _ = infer_horizontal_layout(
                    self.frame, self.preview_auto_mode)
                self.preview_auto_mode = auto
                self.preview_confidence = confidence
            else:
                self.preview_auto_mode = None
                self.preview_confidence = 0.
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
        """Usa o MP4 na resolucao original e mostra o que o Tesseract enxergou."""
        if self.frame is None or not self.videos:
            messagebox.showwarning("Saldo", "Carregue um video e clique Mostrar frame.")
            return
        table = int(self.table.get())
        rect = self.cfg[str(table)].get("stack")
        tesseract = resource("tesseract")
        ffmpeg = resource("ffmpeg")
        if not rect or not tesseract or not ffmpeg:
            messagebox.showwarning("Saldo", "Confira a area do saldo, FFmpeg e Tesseract.")
            return
        try:
            when = parse_time(self.seek.get())
            mode = self.layout_id()
            if table > layout_count(mode):
                messagebox.showwarning("Mesa", "A mesa escolhida nao aparece neste layout.")
                return
            area = layout_rect(rect, table, mode)
            original = native_stack_crop(self.videos, when, area, ffmpeg)
            value, diagnostics = read_stack_diagnostics(original, tesseract, quick=False)
            bb = float(self.cfg[str(table)].get("bb", 1))
            if value is not None and not (0 <= value / bb <= MAX_STACK_BB):
                value = None
            self.show_stack_diagnostics(table, original, value, diagnostics, bb)
        except Exception as exc:
            messagebox.showerror("Diagnostico OCR", str(exc))

    def show_stack_diagnostics(self, table, original, value, results, bb):
        """Mostra a imagem nativa: posicionamento e texto ficam visiveis."""
        window = tk.Toplevel(self)
        window.title(f"Diagnostico do saldo — mesa {table}")
        window.geometry("760x560")
        window.minsize(610, 470)

        ttk.Label(window, text=(
            f"Recorte ORIGINAL do MP4: {original.width} x {original.height} pixels. "
            "Ampliação apenas para visualização."
        )).pack(pady=(10, 5))
        scale = max(2, min(9, 640 // max(original.width, 1)))
        scaled = original.resize((original.width * scale, original.height * scale),
                                 Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(scaled)
        preview = ttk.Label(window, image=photo)
        preview.image = photo
        preview.pack(pady=8)
        if value is None:
            outcome = "OCR NAO RECONHECEU O SALDO. Veja o recorte e as leituras abaixo."
        else:
            outcome = f"SALDO LIDO: {value:g} fichas ({value / bb:g} BB). Confira no video."
        ttk.Label(window, text=outcome, wraplength=720).pack(pady=6)

        details = tk.Text(window, height=9, width=80, wrap="word")
        details.pack(fill="both", expand=True, padx=12, pady=5)
        details.insert("end", "Leituras brutas por contraste e modo do Tesseract:\n\n")
        for variant, psm, raw, amount in results:
            label = raw.replace("\n", " ").strip() or "(vazio)"
            parsed = f"{amount:g}" if amount is not None else "invalido"
            details.insert("end", f"{variant} / psm {psm}: {label} => {parsed}\n")
        details.configure(state="disabled")

        def save_crop():
            target = filedialog.asksaveasfilename(
                parent=window, title="Salvar o recorte para enviar ao suporte",
                defaultextension=".png", initialfile=f"saldo_mesa_{table}.png",
                filetypes=[("Imagem PNG", "*.png")])
            if target:
                original.save(target)
                messagebox.showinfo("Imagem salva", f"Recorte salvo em:\n{target}",
                                    parent=window)

        buttons = ttk.Frame(window)
        buttons.pack(pady=12)
        ttk.Button(buttons, text="Salvar recorte PNG",
                   command=save_crop).pack(side="left", padx=5)
        ttk.Button(buttons, text="Fechar", command=window.destroy).pack(
            side="left", padx=5)


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
                 "quick": self.quick.get(), "auto_export": self.auto_export.get(),
                 "timeline": self.timeline, "tables": self.cfg},
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
                self.auto_export.set(bool(data.get("auto_export", True)))
                self.layout.set(data.get("layout", "2 por 2" if "tables" not in data else "4 lado a lado"))
                self.timeline = sorted(data.get("timeline", []), key=lambda x: float(x["start"]))
                self.detected_timeline = []
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
        mode = self.effective_layout_at(start)
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
        payload = {"version": 4, "videos": [asdict(v) for v in self.videos],
                   "layout": self.layout.get(), "config": self.cfg, "threshold": self.threshold.get(),
                   "nick": self.nick.get().strip(), "quick": self.quick.get(),
                   "auto_export": self.auto_export.get(),
                   "timeline": self.timeline,
                   "detected_timeline": self.detected_timeline,
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
            self.detected_timeline = sorted(
                data.get("detected_timeline", []), key=lambda x: float(x["start"]))
            self.refresh_changes()
            self.nick.set(data.get("nick", "~Pulgar~"))
            self.quick.set(bool(data.get("quick", True)))
            self.auto_export.set(bool(data.get("auto_export", True)))
            self.threshold.set(str(data.get("threshold", 30)))
            self.info.configure(text=f"{len(videos)} arquivo(s) | {fmt(self.total)}")
            self.on_table_change()
            self.refresh()
            self.show_frame()
            self.tell(f"Revisao aberta: {len(self.candidates)} candidatas. Confira e exporte.")
        except Exception as exc:
            messagebox.showerror("Abrir revisao", str(exc))

    def check_stacks_before_analysis(self):
        """Alerta se o video nao produz nenhum saldo legivel nas ROIs atuais."""
        if self.frame is None or not resource("tesseract"):
            return True
        mode = self.layout_id()
        successes = []
        failures = []
        for table in range(1, layout_count(mode) + 1):
            if not table_visible(self.frame, layout_bounds(mode, table), strict=False):
                continue
            rect = self.cfg[str(table)].get("stack")
            if not rect:
                continue
            try:
                bb = float(self.cfg[str(table)].get("bb", 1))
                image = native_stack_crop(
                    self.videos, parse_time(self.seek.get()),
                    layout_rect(rect, table, mode), resource("ffmpeg"))
                value = ocr_stack(image, resource("tesseract"), quick=True)
                if value is not None and 0 <= value / bb <= MAX_STACK_BB:
                    successes.append(f"Mesa {table}: {value / bb:g} BB")
                else:
                    failures.append(f"Mesa {table}")
            except (OSError, ValueError, subprocess.SubprocessError):
                failures.append(f"Mesa {table}")
        if failures and not successes:
            return messagebox.askyesno(
                "OCR dos saldos nao funciona nesta previa",
                "Nenhuma caixa azul apresentou saldo valido no frame original.\n"
                "Isso pode gerar zero cortes.\n\n"
                "Clique 'Testar saldo' para ver o recorte ORIGINAL ampliado "
                "e as leituras brutas antes de iniciar horas de analise.\n\n"
                "Deseja analisar mesmo assim?")
        if failures:
            self.tell("OCR do frame: " + "; ".join(successes) +
                      " | falharam: " + ", ".join(failures))
        return True

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
        if not self.check_stacks_before_analysis():
            return
        destination = None
        if self.auto_export.get():
            destination = filedialog.askdirectory(
                title="Escolha a pasta para os MP4 das perdas detectadas")
            if not destination:
                return
        self.auto_export_folder = destination
        self.busy = True
        self.tell("Analisando saldos para selecionar perdas >= limite...")
        cfg = json.loads(json.dumps(self.cfg))
        videos = self.videos[:]
        hero_nick = self.nick.get().strip()
        quick = self.quick.get()
        initial_layout = self.layout.get()
        events = [entry.copy() for entry in self.timeline]
        detections = []
        def worker():
            try:
                results = scan_videos(videos, cfg, threshold,
                                      lambda msg: self.after(0, lambda m=msg: self.tell(m)),
                                      hero_nick=hero_nick, quick=quick,
                                      initial_layout=initial_layout, events=events,
                                      detected_events=detections)
                self.after(0, lambda: self.finished(results, detections))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self.failed(e))
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, results, detections=None):
        self.candidates = results
        self.detected_timeline = sorted(detections or [], key=lambda e: e["start"])
        self.busy = False
        self.refresh()
        verified = sum(c.auto_verified and not c.excluded for c in results)
        unresolved = sum(c.loss_bb is None for c in results)
        weak = len(results) - verified - unresolved
        self.tell(f"Analise: {verified} perdas OCR consistentes; "
                  f"{weak} perdas fracas; {unresolved} leituras inconclusivas.")
        if self.auto_export_folder:
            # Gera apenas os MP4 com leitura repetida confiavel, sem clique manual.
            self.export(folder=self.auto_export_folder, automatic_only=True)
        else:
            messagebox.showinfo(
                "Analise concluida",
                f"Perdas detectadas com OCR consistente: {verified}\n"
                f"Perdas incertas: {weak}\nLeituras inconclusivas: {unresolved}\n\n"
                "As leituras devem ser conferidas nos videos.")

    def failed(self, error):
        self.busy = False
        messagebox.showerror("Analise interrompida", error)
        self.tell("Erro na analise: " + error[:120])

    def refresh(self):
        for item in self.grid.get_children():
            self.grid.delete(item)
        for i, c in enumerate(self.candidates):
            if c.excluded or (c.loss_bb is None and not self.show_inconclusive.get()):
                continue
            self.grid.insert("", "end", iid=str(i), values=(
                fmt(c.start), fmt(c.end), c.table,
                f"{c.loss_bb:.2f}" if c.loss_bb is not None else "?",
                "OK" if c.nick_verified else "Revisar",
                c.status,
                "MANUAL" if c.confirmed else ("AUTO" if c.auto_verified else "Revisar")))

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
            mode_start = self.effective_layout_at(st + 0.01)
            mode_end = self.effective_layout_at(max(st + 0.01, en - 0.01))
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

    def export(self, folder=None, automatic_only=False):
        if self.busy:
            return
        try:
            threshold = float(self.threshold.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("BB", "Perda minima invalida.")
            return
        eligible = eligible_losses(self.candidates, threshold,
                                   automatic_only=automatic_only)
        if folder is None:
            folder = filedialog.askdirectory(title="Pasta dos MP4 das perdas")
            if not folder:
                return
        dest = Path(folder)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Pasta de exportacao", str(exc))
            return
        # Relatorio inclui tambem casos fracos, evitando a impressao de
        # que todos foram analisados corretamente.
        report = dest / "relatorio_analise.csv"
        try:
            with report.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh, delimiter=";")
                writer.writerow(["inicio", "fim", "mesa", "layout", "nick",
                                 "saldo_antes", "saldo_depois", "perda_bb",
                                 "ocr_consistente", "status", "confiabilidade"])
                for c in self.candidates:
                    writer.writerow([fmt(c.start), fmt(c.end), c.table, c.layout,
                                     c.nick, c.stack_before, c.stack_after,
                                     c.loss_bb, "SIM" if c.auto_verified else "NAO",
                                     c.status, c.reliability])
        except OSError as exc:
            messagebox.showerror("Relatorio", str(exc))
            return

        if not eligible:
            self.auto_export_folder = None
            self.tell("0 perdas com OCR consistente para exportar. "
                      "Verifique o retangulo azul e clique Testar saldo.")
            messagebox.showwarning(
                "Nenhuma perda exportavel",
                "O programa nao confirmou perdas de pelo menos "
                f"{threshold:g} BB com leituras suficientes.\n\n"
                "Nao foram gerados cortes possivelmente errados.\n"
                f"Relatorio: {report}\n\n"
                "Verifique o quadro azul sobre o numero do saldo e use "
                "'Testar saldo'.")
            return

        self.busy = True
        self.tell(f"Gerando {len(eligible)} MP4 de perdas identificadas...")
        hero_nick = self.nick.get().strip()
        videos = self.videos[:]
        def worker():
            logs = []
            for i, c in enumerate(eligible, 1):
                filename = f"mao_{i:03}_mesa{c.table}_perda_{c.loss_bb:.1f}BB.mp4"
                destination = dest / filename
                status = "OK"
                try:
                    clip = Clip(c.start, c.end, c.table, c.loss_bb, "Video OCR",
                                "Video", "", True)
                    export_clip(videos, clip, destination,
                                resource("ffmpeg"), layout=c.layout)
                except Exception as exc:
                    status = "ERRO: " + str(exc)[-180:]
                    try:
                        destination.unlink(missing_ok=True)
                    except OSError:
                        pass
                logs.append({"arquivo": filename, "nick": c.nick or hero_nick,
                             "nick_ocr_confirmado": c.nick_verified,
                             "classificacao": "OCR consistente" if c.auto_verified
                                             else "Confirmado manualmente",
                             "mesa": c.table, "disposicao": c.layout,
                             "inicio": fmt(c.start), "fim": fmt(c.end),
                             "saldo_antes": c.stack_before,
                             "saldo_depois": c.stack_after,
                             "perda_bb": c.loss_bb, "status": status})
                self.after(0, lambda j=i, st=status:
                           self.tell(f"MP4 {j}/{len(eligible)}: {st}"))
            try:
                with (dest / "indice_das_maos.csv").open(
                        "w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.DictWriter(fh, fieldnames=list(logs[0]),
                                            delimiter=";")
                    writer.writeheader()
                    writer.writerows(logs)
            except OSError as exc:
                logs.append({"status": "ERRO GRAVANDO INDICE: " + str(exc)})

            def done():
                self.busy = False
                self.auto_export_folder = None
                good = sum(entry["status"] == "OK" for entry in logs)
                self.tell(f"{good}/{len(eligible)} MP4 gerados em {dest}.")
                messagebox.showinfo(
                    "Exportacao concluida",
                    f"{good} de {len(eligible)} MP4 gerados.\n\n"
                    f"Pasta: {dest}\n"
                    "Indice: indice_das_maos.csv\n"
                    "Diagnostico: relatorio_analise.csv\n\n"
                    "As leituras por OCR sao estimativas; confira os cortes antes "
                    "de enviar ao instrutor.")
            self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    GUI().mainloop()
