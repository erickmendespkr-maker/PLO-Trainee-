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
from dataclasses import dataclass, asdict, field
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from PIL import Image, ImageChops, ImageEnhance, ImageOps, ImageStat, ImageTk
except ImportError as exc:
    raise SystemExit("Pillow ausente. Execute INICIAR_ANALISE_VIDEO.bat para instalar.") from exc

from cortador import Clip, export_clip, file_at, fmt, parse_time, probe, resource
from hud_recognition import is_full_hud, read_hud_stack, read_hud_nick
from analise_local import times_for_hand, assess_stacks, offline_review_decision
from desfecho_local import read_table_ocr, evaluate_pot_transfer
from pasta_saida import load_export_folder, save_export_folder, valid_export_folder

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


def default_hero_hud(mode, table):
    """Uma caixa grande inferior por mesa, como no print de 3 mesas."""
    mode = layout_key(mode)
    left, top, right, bottom = layout_bounds(mode, table)
    if mode == "grid2x2":
        # O perfil 2x2 possui geometria diferente, exigir ajuste manual.
        return None
    width = right - left
    return (round(left + width * .31), 405,
            round(left + width * .90), 528)


def hero_hud_parts(hud):
    """Subareas internas. Usuario desenha UM HUD; OCR/cartas recebem recortes."""
    x1, y1, x2, y2 = roi_tuple(hud)
    width, height = x2 - x1, y2 - y1
    if width < 65 or height < 50:
        raise ValueError("HUD unico pequeno demais: inclua cartas, nick e saldo.")
    parts = {
        "hole": (round(x1 + width * .40), round(y1 + height * .20),
                 round(x1 + width * .94), round(y1 + height * .64)),
        "nick": (round(x1 + width * .11), round(y1 + height * .47),
                 round(x1 + width * .43), round(y1 + height * .65)),
        "stack": (round(x1 + width * .11), round(y1 + height * .67),
                  round(x1 + width * .43), round(y1 + height * .80)),
    }
    return {name: roi_tuple(rect) for name, rect in parts.items()}


def layout_roi(data, table, mode, key):
    """Uma unica marcacao HUD prevalece para cartas, nick e saldo."""
    mode = layout_key(mode)
    selections = data.get("layout_rois", {}).get(mode, {})
    hud = selections.get("hero_hud")
    if hud is None and mode != "grid2x2":
        hud = default_hero_hud(mode, table)
    if key == "hero_hud":
        return roi_tuple(hud) if hud is not None else None
    # Saldo e nick sao pesquisados DENTRO do HUD completo; nao usar mais
    # percentuais estreitos que cortavam "125,7 BB" e "~Pulgar~".
    if hud is not None and key in ("nick", "stack"):
        return roi_tuple(hud)
    if hud is not None and key == "hole":
        return hero_hud_parts(hud)["hole"]
    # Compatibilidade com antigos layouts 2x2 e JSON anteriores.
    specific = selections.get(key)
    if specific is not None:
        return roi_tuple(specific)
    return layout_rect(data[key], table, mode) if data.get(key) else None


def store_layout_roi(config, table, mode, key, absolute_rect, source="manual"):
    """Preserva calibracoes de outros layouts ao redesenhar uma regiao."""
    mode = layout_key(mode)
    if mode == "auto4":
        raise ValueError("Confirme a disposicao antes de marcar.")
    rect = list(roi_tuple(absolute_rect))
    tables = [table] if mode == "grid2x2" else list(range(1, layout_count(mode) + 1))
    x1, y1, x2, y2 = layout_bounds(mode, table)
    for destination in tables:
        dx1, dy1, dx2, dy2 = layout_bounds(mode, destination)
        new_rect = [rect[0]-x1+dx1, rect[1]-y1+dy1,
                    rect[2]-x1+dx1, rect[3]-y1+dy1]
        if not (dx1 <= new_rect[0] < new_rect[2] <= dx2 and
                dy1 <= new_rect[1] < new_rect[3] <= dy2):
            raise ValueError("Retangulo nao cabe em todas as janelas deste layout.")
        config[str(destination)].setdefault("layout_rois", {}).setdefault(
            mode, {})[key] = new_rect
        config[str(destination)].setdefault("layout_roi_sources", {}).setdefault(
            mode, {})[key] = source
        if mode == "horizontal4":
            config[str(destination)][key] = new_rect[:]


def detect_hero_cards_anchor(frame, mode, table):
    """Localiza o grupo de cartas claras do heroi na faixa inferior da mesa.

    Opera somente no frame RGB original 960x540, nao depende de OCR/API.
    Se a evidência visual for fraca, devolve None em vez de mover marcas.
    """
    mode = layout_key(mode)
    if mode in ("auto4", "grid2x2"):
        return None
    box = layout_bounds(mode, table)
    x1, y1, x2, y2 = box
    width = x2 - x1
    if width < 175:
        return None
    image = frame.convert("RGB")
    pixels = image.load()
    left = x1 + round(width * .36)
    right = min(x2 - 4, x1 + round(width * .90))
    top = max(y1, round(H * .775))
    bottom = min(y2 - 4, round(H * .924))
    if bottom - top < 35:
        return None
    density = []
    for y in range(top, bottom):
        hits = 0
        for x in range(left, right):
            red, green, blue = pixels[x, y]
            if (red + green + blue >= 480 and
                    max(red, green, blue) >= 175 and
                    min(red, green, blue) >= 65):
                hits += 1
        density.append(hits)
    min_density = max(11, round((right-left) * .16))
    bands = []
    first = None
    for index, amount in enumerate([*density, 0]):
        if amount >= min_density and first is None:
            first = index
        elif amount < min_density and first is not None:
            last = index
            if last - first >= 12:
                bands.append((sum(density[first:last]), first, last))
            first = None
    if not bands:
        return None
    _, start, finish = max(bands)
    card_top, card_bottom = top + start, top + finish
    if not (420 <= card_top <= 474 and 430 <= card_bottom <= 498):
        return None
    columns = []
    for x in range(left, right):
        hits = 0
        for y in range(card_top, card_bottom):
            red, green, blue = pixels[x, y]
            if (red + green + blue >= 480 and
                    max(red, green, blue) >= 175 and
                    min(red, green, blue) >= 65):
                hits += 1
        if hits >= max(4, round((card_bottom-card_top) * .18)):
            columns.append(x)
    if len(columns) < round(width * .18):
        return None
    # Evitar unir um avatar claro isolado ao conjunto de cartas.
    runs = []
    run_start = run_end = columns[0]
    for x in columns[1:]:
        if x - run_end <= 5:
            run_end = x
        else:
            runs.append((run_end - run_start, run_start, run_end))
            run_start = run_end = x
    runs.append((run_end - run_start, run_start, run_end))
    run_width, card_left, card_right = max(runs)
    if not (width * .19 <= run_width <= width * .49):
        return None
    return (max(x1, card_left - 3), max(y1, card_top - 3),
            min(x2, card_right + 4), min(y2, card_bottom + 3))


def auto_hero_profile(frame, mode):
    """Estima somente uma caixa HUD a partir de cartas visiveis do heroi."""
    mode = layout_key(mode)
    if mode in ("auto4", "grid2x2"):
        return None
    anchors = []
    width = layout_bounds(mode, 1)[2] - layout_bounds(mode, 1)[0]
    for table in range(1, layout_count(mode) + 1):
        rect = detect_hero_cards_anchor(frame, mode, table)
        if rect is not None:
            x1, _, _, _ = layout_bounds(mode, table)
            anchors.append((rect[0] - x1, rect[1],
                            rect[2] - x1, rect[3]))
    if not anchors:
        return None
    columns = list(zip(*anchors))
    hole = [round(statistics.median(col)) for col in columns]
    hud = [
        max(0, hole[0] - round(width * .24)),
        max(0, hole[1] - 27),
        min(width, hole[2] + round(width * .06)),
        min(H, hole[3] + 49)
    ]
    if hud[2] - hud[0] < 65 or hud[3] - hud[1] < 50:
        return None
    return {"hero_hud": hud}


def apply_auto_hero_profile(config, frame, mode, force=False):
    """Atualiza apenas HUDs automaticos, preservando os manuais."""
    mode = layout_key(mode)
    profile = auto_hero_profile(frame, mode)
    if profile is None:
        return 0
    adjusted = 0
    for table in range(1, layout_count(mode) + 1):
        left, top, right, bottom = layout_bounds(mode, table)
        data = config[str(table)]
        key = "hero_hud"
        source = data.get("layout_roi_sources", {}).get(
            mode, {}).get(key, "legacy")
        if source == "manual" and not force:
            continue
        r = profile[key]
        rect = [r[0]+left, r[1]+top, r[2]+left, r[3]+top]
        if not (left <= rect[0] < rect[2] <= right and
                top <= rect[1] < rect[3] <= bottom):
            continue
        data.setdefault("layout_rois", {}).setdefault(mode, {})[key] = rect
        data.setdefault("layout_roi_sources", {}).setdefault(
            mode, {})[key] = "auto"
        adjusted += 1
    return adjusted


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
    # Detectar primeiro as bordas verticais que atravessam quase a
    # altura das janelas. Mesas diferentes podem ter cartas e saldos
    # bastante distintos, apesar de manter a mesma geometria. O metodo
    # anterior priorizava similaridade de conteudo e podia reconhecer
    # quatro mesas como uma unica.
    structural = []
    for count in (4, 3, 2):
        positions = [round(W * i / count) for i in range(1, count)]
        boundary_evidence = [vertical_seam_strength(gray, x)
                             for x in positions]
        if not boundary_evidence or min(boundary_evidence) < .36:
            continue
        textured = sum(
            table_visible(gray, layout_bounds(f"horizontal{count}", table),
                          strict=False)
            for table in range(1, count + 1))
        if textured < count:
            continue
        structural.append((min(boundary_evidence), count))
    if structural:
        best_seam, detected_count = max(
            structural, key=lambda item: (item[0], item[1] / 10))
        if previous and layout_key(previous) == f"horizontal{detected_count}":
            return previous, .96, {previous: round(best_seam, 3)}
        if best_seam >= .48:
            mode = f"horizontal{detected_count}"
            return mode, .87, {mode: round(best_seam, 3)}

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
            "stack": [dx + 97, 487, dx + 153, 500],
            "nick": [dx + 91, 470, dx + 155, 486],
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
    """Le o HUD inteiro; so usa OCR legado em recortes antigos pequenos."""
    if is_full_hud(img):
        return read_hud_stack(img, tesseract, parse_stack, quick=quick)
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
    # Tesseract frequentemente devolve '114, 0' para '114,0'.
    # Juntar somente quando existe pontuacao decimal explicita.
    cleaned = re.sub(r"(?<=\d)([.,])\s+(?=\d)", r"\1", value)
    candidates = re.findall(r"\d+(?:[.,]\d+)*", cleaned)
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
    """Pesquisa o nick no HUD inteiro, nao em uma faixa antiga estreita."""
    if is_full_hud(image):
        return read_hud_nick(image, tesseract)
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
    source: str = "OCR"
    before_times: list[float] = field(default_factory=list)
    after_times: list[float] = field(default_factory=list)
    hand_start: float | None = None
    hand_end: float | None = None
    pot_verified: bool = False
    hero_invested_bb: float | None = None
    winner_nick: str = ""
    auto_rebuy_seen: bool | None = None


def eligible_losses(candidates, threshold, automatic_only=False,
                    require_pot_evidence=False):
    """Com rebuy automatico, OCR de stacks sozinho NAO permite MP4 automatico."""
    chosen = []
    for c in candidates:
        if c.excluded or not loss_reaches_threshold(c.loss_bb, threshold):
            continue
        trusted_auto = c.auto_verified and (
            not require_pot_evidence or c.pot_verified)
        if automatic_only:
            if trusted_auto:
                chosen.append(c)
        elif trusted_auto or c.confirmed:
            chosen.append(c)
    return chosen


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
             quick=False, native_reader=None, auto_rebuy=False):
        if not self.active:
            if self.pending is not None:
                if not occupied and len(self.pending["after"]) < 6:
                    self.pending["after"].append(stack_img.copy())
                    self.pending["after_times"].append(t)
                # Esperar saldo estabilizar apos animacao/pagamento do pote,
                # sem atravesar o inicio da mao seguinte.
                if len(self.pending["after"]) >= 6 or occupied:
                    self.finish(table, bb, threshold, tesseract, quick=quick,
                                native_reader=native_reader,
                                auto_rebuy=auto_rebuy)
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
               native_reader=None, auto_rebuy=False):
        data = self.pending
        self.pending = None
        if not data:
            return
        if auto_rebuy:
            # A mesa pode recompor para 100 BB imediatamente apos uma perda.
            # Saldo pre/pos identico nao prova ganho e nao permite descartar
            # nenhuma mao. Registrar todas para interpretacao do POTE.
            self.results.append(Candidate(
                max(0, data["start"] - 5), data["end"] + 5, table,
                None, None, None, "INCONCLUSIVO - AGUARDANDO POTE/REBUY",
                layout=self.layout,
                reliability="Verificar aporte do heroi e premiacao do pote",
                source="Contexto pendente",
                before_times=data.get("before_times", [])[:],
                after_times=data.get("after_times", [])[:],
                hand_start=data["start"], hand_end=data["end"]))
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
                layout=self.layout, reliability="OCR ausente",
                before_times=data.get("before_times", [])[:],
                after_times=data.get("after_times", [])[:]))
            return

        if not loss_reaches_threshold(loss, threshold):
            if n_pre < 2 or n_post < 2:
                # Uma unica leitura insuficiente nao prova que o jogador
                # ganhou ou perdeu menos de 30 BB. Guardar para revisao,
                # em vez de descartar silenciosamente uma perda real.
                self.results.append(Candidate(
                    max(0, data["start"] - 5), data["end"] + 5, table,
                    None, pre, post, "INCONCLUSIVO - SALDO FRACO",
                    layout=self.layout,
                    reliability="Menos de dois saldos confirmados por lado",
                    before_times=data.get("before_times", [])[:],
                    after_times=data.get("after_times", [])[:]))
            # Somente ganhos ou perdas pequenas com leitura consistente saem.
            return

        # Leitura coerente de 2 amostras antes e 2 depois e exigida para
        # exportacao automatica. Valores absurdos ja foram filtrados.
        strong = (n_pre >= 2 and n_post >= 2 and
                  0 <= post / bb <= MAX_STACK_BB and
                  0 <= pre / bb <= MAX_STACK_BB)
        status = ("POSSIVEL PERDA - COMPARACAO OCR" if strong else
                  "INCONCLUSIVO - OCR DO SALDO FRACO")
        self.results.append(Candidate(
            max(0, data["start"] - 5), data["end"] + 5, table,
            round(loss, 2), pre, post, status,
            layout=self.layout, auto_verified=strong,
            reliability=f"OCR: antes {n_pre} / depois {n_post} leituras",
            source="OCR",
            before_times=data.get("before_times", [])[:],
            after_times=data.get("after_times", [])[:]))


def scan_videos(videos, config, threshold, progress, hero_nick="~Pulgar~",
                quick=True, initial_layout="Automatico (1 a 4 mesas)", events=None,
                detected_events=None, auto_rebuy=True):
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
                "hole": layout_roi(data, table, mode, "hole"),
                "stack": layout_roi(data, table, mode, "stack"),
                "nick": layout_roi(data, table, mode, "nick"),
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
                         native_reader=read_native_at,
                         auto_rebuy=auto_rebuy)
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
                                       native_reader=read_native_at,
                                       auto_rebuy=auto_rebuy)
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


def estimate_candidates_offline(videos, config, candidates, threshold,
                                progress=lambda msg: None, sample_count=7):
    """Triagem de possivel investimento >=30 BB pelo stack DURANTE cada mao.

    Nunca classifica automaticamente perda apenas pela queda do stack, porque
    o vencedor/side pots e o rebuy exigem confirmacao por evidencia de video.
    A leitura usa o HUD verde completo, em frames NATIVOS do video.
    """
    if not videos:
        return [], 0, 0
    ffmpeg, tesseract = resource("ffmpeg"), resource("tesseract")
    if not ffmpeg or not tesseract:
        raise RuntimeError("FFmpeg e Tesseract sao necessarios para triagem local.")
    duration = sum(v.duration for v in videos)
    copies = [Candidate(**asdict(c)) for c in candidates]
    analyzed = 0
    priority = 0
    for candidate in copies:
        if candidate.excluded or candidate.confirmed or candidate.pot_verified:
            continue
        # Arquivos gerados por versoes antigas nao podem continuar marcados
        # como auto confirmados pela IA removida.
        candidate.auto_verified = False
        candidate.loss_bb = None
        candidate.pot_verified = False
        mode = layout_key(candidate.layout)
        if mode == "auto4" or not 1 <= candidate.table <= layout_count(mode):
            candidate.status = "REVISAR - DISPOSICAO DA MESA INSEGURA"
            continue
        times = times_for_hand(candidate, duration, sample_count)
        if times is None:
            candidate.status = "REVISAR - LIMITES DA MAO INSEGUROS"
            continue
        rect = layout_roi(
            config[str(candidate.table)], candidate.table, mode, "hero_hud")
        if rect is None:
            candidate.status = "REVISAR - HUD NAO LOCALIZADO"
            continue
        bb = float(config[str(candidate.table)].get("bb", 1))
        if not bb > 0:
            candidate.status = "REVISAR - BB INVALIDO"
            continue
        samples = {"before": [], "during": [], "after": []}
        for kind in ("before", "during", "after"):
            for at in times[kind]:
                try:
                    original = native_stack_crop(videos, at, rect, ffmpeg)
                    value = ocr_stack(original, tesseract, quick=True)
                    if value is not None and 0 <= value / bb <= MAX_STACK_BB:
                        samples[kind].append(value)
                    else:
                        samples[kind].append(None)
                except (OSError, RuntimeError, ValueError,
                        subprocess.SubprocessError):
                    samples[kind].append(None)
        estimate = assess_stacks(
            samples["before"], samples["during"], samples["after"],
            bb, threshold)
        candidate.hero_invested_bb = estimate["invested_estimate_bb"]
        candidate.auto_rebuy_seen = (
            True if estimate["rebuy_possible"] else None)
        candidate.source = "Triagem local - OCR"
        candidate.reliability = (
            estimate["reason"] + " | "
            + f"BB inicio={estimate['baseline_bb']}, "
            + f"minimo={estimate['minimum_bb']} | "
            + f"quadros OCR validos={sum(v is not None for v in samples['during'])}"
            + f"/{len(samples['during'])}")
        if estimate["prioritize"]:
            priority += 1
            candidate.status = "PRIORIDADE - APORTE >= LIMITE; CONFERIR POTE"
        else:
            candidate.status = "PENDENTE - " + estimate["reason"][:75]
        analyzed += 1
        if analyzed % 3 == 0 or analyzed == len(copies):
            progress(f"Triagem local: {analyzed}/{len(copies)} maos, "
                     f"{priority} com aporte provavel >= {threshold:g} BB.")
    return copies, analyzed, priority


def confirm_candidates_by_pot_offline(videos, config, candidates,
                                      threshold, progress=lambda msg: None):
    """Passo 3/3: seguir pote e stacks da MESA inteira apos a mao.

    Nao basta stack do heroi cair; so MP4 automaticamente se uma
    transferencia de fichas a outro assento for confirmada.
    """
    result = [Candidate(**asdict(c)) for c in candidates]
    ffmpeg = resource("ffmpeg")
    tesseract = resource("tesseract")
    if not ffmpeg or not tesseract:
        raise RuntimeError("FFmpeg/Tesseract nao encontrados para o pote.")
    duration = sum(v.duration for v in videos)
    approved = 0
    evaluated = 0
    for index, c in enumerate(result):
        if c.excluded or c.confirmed:
            continue
        if c.hero_invested_bb is None or not loss_reaches_threshold(
                c.hero_invested_bb, threshold):
            continue
        mode = layout_key(c.layout)
        if mode == "auto4" or c.table > layout_count(mode):
            c.status = "PENDENTE - MESA NAO IDENTIFICADA"
            continue
        start = (c.hand_start if c.hand_start is not None
                 else c.start + 5.0)
        finish = (c.hand_end if c.hand_end is not None
                  else c.end - 5.0)
        if not (1.0 <= start < finish < duration - 1):
            c.status = "PENDENTE - MAO SEM INICIO OU FIM CONFIAVEL"
            continue
        # Nao misturar o resultado de outra mao da mesma mesa.
        next_starts = [
            other.hand_start for other in result[index + 1:]
            if other.table == c.table and other.layout == c.layout
            and other.hand_start is not None
            and other.hand_start > finish]
        hard_end = min(duration - .15,
                       min(next_starts) - .2 if next_starts else finish + 14)
        after_candidates = [finish + offset for offset in (.75, 2.0, 4.0,
                                                            7.0, 11.0)]
        after_candidates = [t for t in after_candidates if t < hard_end]
        if len(after_candidates) < 2:
            c.status = "PENDENTE - PREMIACAO NAO OBSERVAVEL"
            continue
        table_box = layout_bounds(mode, c.table)
        def snap(moment):
            return read_table_ocr(
                native_stack_crop(videos, moment, table_box, ffmpeg),
                tesseract)
        try:
            before = snap(max(.02, start - 1.0))
            pot_before = snap(max(start + .1, finish - 1.5))
            last = None
            outcome = None
            # 2 quadros sequenciais apos a transferencia, para confirmar
            # que o ganho do adversario nao e uma animacao transitoria.
            for moment in after_candidates:
                current = snap(moment)
                if last is not None:
                    outcome = evaluate_pot_transfer(
                        before, pot_before, last, current,
                        c.hero_invested_bb, threshold)
                    if outcome["confirmed"]:
                        break
                last = current
        except (OSError, RuntimeError, ValueError,
                subprocess.SubprocessError) as exc:
            c.status = "PENDENTE - OCR DA MESA INTEIRA FALHOU"
            c.reliability = type(exc).__name__ + " durante leitura do pote"
            continue
        evaluated += 1
        if outcome is not None and outcome["confirmed"]:
            c.loss_bb = outcome["loss_bb"]
            c.pot_verified = True
            c.auto_verified = True
            c.status = "PERDA CONFIRMADA - POTE PARA ADVERSARIO (OFFLINE)"
            c.source = "OCR local da mesa inteira"
            c.winner_nick = outcome["winner"]
            c.reliability = outcome["reason"]
            approved += 1
        else:
            c.pot_verified = False
            c.auto_verified = False
            c.loss_bb = None
            c.status = "PENDENTE - DESTINO DO POTE NAO CONFIRMADO"
            c.reliability = (
                outcome["reason"] if outcome is not None
                else "Nao ha quadros de premiacao suficientes")
        if evaluated % 3 == 0:
            progress(f"Vencedor do pote: {evaluated} maos examinadas; "
                     f"{approved} perdas >= {threshold:g} BB confirmadas.")
    progress(f"Resultado offline: {approved} perdas confirmadas por "
             f"transferencia do pote; {evaluated} suspeitas verificadas.")
    return result, evaluated, approved


DEFAULT_MARKINGS_FILE = "marcacoes_padrao.json"


def latest_review_path():
    """Ultima revisao fora do ZIP para reusar sem repetir a varredura."""
    return default_markings_path().parent / "ultima_revisao.json"


def default_markings_path():
    """Persiste fora da pasta ZIP, para nao perder calibracao ao atualizar."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "CortadorPLO" / DEFAULT_MARKINGS_FILE


def validated_markings(data):
    """Valida o arquivo salvo antes de usar coordenadas no OCR."""
    if not isinstance(data, dict):
        raise ValueError("Marcacoes invalidas.")
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("Configuracao sem tabelas.")
    prepared = {}
    for table in TABLES:
        source = tables.get(str(table))
        if not isinstance(source, dict):
            raise ValueError(f"Mesa {table} ausente nas marcacoes.")
        clone = dict(source)
        for key in ("hole", "stack", "nick"):
            if clone.get(key):
                clone[key] = list(roi_tuple(clone[key]))
            elif key in ("hole", "stack"):
                raise ValueError(f"Regiao {key} ausente na mesa {table}.")
        # Migrar automaticamente a marcacao VERDE GRANDE desenhada na versao
        # anterior como "cartas": se cobre o HUD inteiro (altura >= 80px),
        # ja e a unica marcacao que o usuario quer guardar.
        layouts = json.loads(json.dumps(source.get("layout_rois", {})))
        sources = json.loads(json.dumps(source.get("layout_roi_sources", {})))
        for mode, entries in layouts.items():
            if not isinstance(entries, dict):
                raise ValueError("Perfil de layout invalido.")
            hud = entries.get("hero_hud")
            legacy_large = entries.get("hole")
            if hud is None and legacy_large:
                rect = roi_tuple(legacy_large)
                if rect[3] - rect[1] >= 80 and rect[2] - rect[0] >= 90:
                    hud = list(rect)
                    entries["hero_hud"] = hud
                    sources.setdefault(mode, {})["hero_hud"] = "manual"
            if hud is not None:
                entries["hero_hud"] = list(roi_tuple(hud))
        clone["layout_rois"] = layouts
        clone["layout_roi_sources"] = sources
        # Uma referencia visual antiga de cartas tem dimensoes diferentes
        # das subareas calculadas a partir do novo HUD; nao reutiliza-la.
        if any(isinstance(entry, dict) and entry.get("hero_hud")
               for entry in layouts.values()):
            clone.pop("reference", None)
            clone["detector"] = "bright"
        bb = float(str(clone.get("bb", "1")).replace(",", "."))
        if not (0 < bb < 1000000):
            raise ValueError(f"BB invalido na mesa {table}.")
        clone["bb"] = str(bb)
        prepared[str(table)] = clone
    layout = data.get("layout", LAYOUT_LABELS[0])
    layout_key(layout)
    return {"version": 1, "layout": layout,
            "nick": str(data.get("nick", "~Pulgar~")),
            "tables": prepared}


def save_markings_file(path, tables, nick, layout):
    """Gravacao atomica evita perder o ultimo padrao se o PC desligar."""
    payload = validated_markings({
        "tables": tables, "nick": nick, "layout": layout})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        os.replace(temp, target)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def load_markings_file(path):
    return validated_markings(
        json.loads(Path(path).read_text(encoding="utf-8")))



class GUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PLO - Analise visual de videos (sem DriveHUD)")
        self.geometry("1120x845")
        self.minsize(990, 760)
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
        self.auto_rebuy = tk.BooleanVar(value=True)
        self.show_inconclusive = tk.BooleanVar(value=True)
        self.pot_choice = tk.StringVar(value="Nao sei")
        self.auto_export_folder = None
        self.output_dir = tk.StringVar(value=str(load_export_folder()))
        self.cfg = screenshot_profile()
        self.markings_source = "Pre-calibracao do print"
        preset = default_markings_path()
        if preset.is_file():
            try:
                saved = load_markings_file(preset)
                self.cfg = saved["tables"]
                self.nick.set(saved["nick"])
                self.layout.set(saved["layout"])
                self.markings_source = "Marcacoes salvas no computador"
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                self.markings_source = "Pre-calibracao do print (padrao salvo invalido)"
        self._ui()
        self.on_table_change()
        self.draw()
        self.tell(self.markings_source + " — use Salvar como padrao apos ajustes.")

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
        ttk.Label(row, text="Marcar: HUD unico (cartas + nick + saldo)").pack(
            side="left", padx=5)
        self.field = tk.StringVar(value="HUD unico")
        ttk.Button(row, text="Usar regioes do print", command=self.apply_profile).pack(side="left", padx=5)
        ttk.Button(row, text="Salvar como padrao",
                   command=self.save_default_markings).pack(side="left", padx=4)
        ttk.Button(row, text="Usar padrao salvo",
                   command=self.load_default_markings).pack(side="left", padx=4)
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
        ttk.Checkbutton(row2, text="Salvar MP4 de perdas confirmadas",
                        variable=self.auto_export).pack(side="left", padx=6)
        self.table.trace_add("write", lambda *_: self.on_table_change())

        rebuy_row = ttk.Frame(self)
        rebuy_row.pack(fill="x", padx=8, pady=(0, 3))
        ttk.Label(
            rebuy_row, text="Rebuy automatico considerado | 3 etapas: "
                            "mao, aporte e pote",
            foreground="#696969").pack(side="left", padx=4)
        ttk.Label(rebuy_row, text="Saldo voltar a 100 BB nao significa ganho.",
                  foreground="#696969").pack(side="left", padx=8)

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
        ttk.Checkbutton(controls, text="Mostrar maos inconclusivas",
                        variable=self.show_inconclusive,
                        command=self.refresh).pack(side="left", padx=8)
        review_ai = ttk.Frame(self)
        review_ai.pack(fill="x", padx=8)
        ttk.Button(review_ai, text="ESTIMAR APORTES (OFFLINE)",
                   command=self.recheck_inconclusive).pack(side="left", pady=3)
        ttk.Button(review_ai, text="Abrir ultima revisao",
                   command=self.load_latest_review).pack(side="left", padx=8)
        ttk.Button(review_ai, text="AUTOAJUSTAR MARCACOES NESTE VIDEO",
                   command=self.force_auto_align).pack(side="left", padx=4)
        ttk.Label(review_ai, text="Reutiliza horarios da revisao; sem IA, sem rede.",
                  foreground="#696969").pack(side="left", padx=8)
        output_row = ttk.Frame(self)
        output_row.pack(fill="x", padx=8, pady=(2, 4))
        ttk.Label(output_row, text="Pasta padrao dos MP4:").pack(side="left", padx=(0, 5))
        ttk.Entry(output_row, textvariable=self.output_dir,
                  state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(output_row, text="Alterar pasta",
                   command=self.choose_output_folder).pack(side="left", padx=3)
        ttk.Button(output_row, text="Abrir pasta",
                   command=self.open_output_folder).pack(side="left", padx=3)
        self.status = ttk.Label(self, text="Aguardando videos e calibracao de cada mesa.")
        self.status.pack(fill="x", padx=8)

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=8, pady=4)
        columns = ("inicio", "fim", "mesa", "perda", "nick_status", "status", "conferido")
        self.grid = ttk.Treeview(table_frame, columns=columns, show="headings", height=4)
        for col, label, width in [
            ("inicio", "Inicio", 92), ("fim", "Fim", 92), ("mesa", "Mesa", 55),
            ("perda", "Aporte possivel / Perda BB", 160), ("nick_status", "Nick OCR", 105),
            ("status", "Resultado OCR / IA", 300), ("conferido", "Conferido", 90)]:
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
        ttk.Label(edit, text="Perda liquida (BB):").pack(side="left")
        self.loss_edit = tk.StringVar()
        ttk.Entry(edit, textvariable=self.loss_edit, width=9).pack(side="left", padx=3)
        ttk.Label(edit, text="Pote:").pack(side="left", padx=4)
        ttk.Combobox(edit, textvariable=self.pot_choice,
                     values=["Nao sei", "Adversario levou tudo",
                             "Heroi ganhou parte", "Heroi ganhou"],
                     state="readonly", width=22).pack(side="left")
        ttk.Button(edit, text="Conferir/Salvar", command=self.confirm).pack(side="left", padx=6)
        ttk.Button(edit, text="Descartar", command=self.exclude).pack(side="left")
        ttk.Button(edit, text="Ver inicio", command=lambda: self.preview_edge("start")).pack(side="left", padx=5)
        ttk.Button(edit, text="Ver fim", command=lambda: self.preview_edge("end")).pack(side="left")
        ttk.Button(edit, text="EXPORTAR PERDAS", command=self.export).pack(side="right")
        ttk.Button(edit, text="EXPORTAR PARA REVISAO",
                   command=self.export_review_candidates).pack(side="right", padx=5)
        ttk.Label(self, text="100% offline. Aporte estimado nao prova derrota: confirme destino do pote para classificar perdas.",
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
            # Nao apagar os perfis de 1-4 mesas ao visualizar um layout 2x2.
            self.tell("Layout 2x2 selecionado. Ajuste manualmente as regioes "
                      "se necessario; os perfis lado a lado ficam intactos.")
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
        self.tell("Perfil de HUD unico restaurado. "
                  "A caixa verde ja inclui cartas, nick e saldo.")

    def save_default_markings(self):
        """Captura TODAS as marcas atuais, incluindo ajustes manuais do nick."""
        try:
            target = save_markings_file(
                default_markings_path(), self.cfg, self.nick.get(),
                self.layout.get())
            self.markings_source = "Marcacoes salvas no computador"
            self.tell("HUD unico por mesa e BB salvos como padrao.")
            messagebox.showinfo(
                "Padrao salvo",
                "Os HUDs unicos foram salvos para as disposicoes configuradas.\n\n"
                "Elas serao carregadas automaticamente toda vez que abrir "
                "o programa, inclusive apos atualizar o ZIP.\n\n"
                f"Arquivo: {target}")
        except (OSError, ValueError, TypeError) as exc:
            messagebox.showerror("Salvar padrao", str(exc))

    def load_default_markings(self):
        path = default_markings_path()
        if not path.is_file():
            messagebox.showwarning(
                "Sem padrao salvo",
                "Ainda nao existe padrao salvo. Posicione as regioes "
                "e clique Salvar como padrao.")
            return
        try:
            saved = load_markings_file(path)
            self.cfg = saved["tables"]
            self.nick.set(saved["nick"])
            self.layout.set(saved["layout"])
            self.markings_source = "Marcacoes salvas no computador"
            self.on_table_change()
            self.draw()
            self.tell("Padrao salvo carregado: cartas, saldo, nick e BB.")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            messagebox.showerror("Abrir padrao", str(exc))

    def tell(self, msg):
        self.status.configure(text=msg)

    def auto_align_current_frame(self, force=False):
        """Calibra a partir das cartas do heroi, mantendo marcas manuais."""
        if self.frame is None:
            return 0
        mode = self.layout_id()
        if mode not in ("horizontal1", "horizontal2",
                        "horizontal3", "horizontal4"):
            return 0
        adjusted = apply_auto_hero_profile(self.cfg, self.frame, mode, force)
        if adjusted:
            try:
                save_markings_file(
                    default_markings_path(), self.cfg,
                    self.nick.get(), self.layout.get())
            except (OSError, ValueError, TypeError):
                self.tell("AVISO: autoajuste aplicado, mas nao foi salvo.")
            self.tell(f"Autoajuste no layout de {layout_count(mode)} mesa(s): "
                      f"{adjusted} HUDs posicionados pelo video.")
            self.draw()
        return adjusted

    def force_auto_align(self):
        if self.frame is None:
            messagebox.showwarning("Autoajuste", "Carregue um video e clique Mostrar frame.")
            return
        if not messagebox.askyesno(
                "Autoajustar marcacoes",
                "Localizar suas cartas na parte inferior e ajustar o HUD "
                "unico que tambem contem nick e saldo?\n\n"
                "Isto substitui as marcacoes DESTE layout, mas preserva "
                "as marcacoes dos outros layouts."):
            return
        changed = self.auto_align_current_frame(force=True)
        if not changed:
            messagebox.showwarning(
                "Autoajuste inconclusivo",
                "Nao foram encontradas cartas do jogador com evidencia "
                "suficiente neste quadro. Va a um instante em que suas "
                "cartas estejam visiveis, clique Mostrar frame e tente novamente.")
        else:
            messagebox.showinfo(
                "Autoajuste aplicado",
                "O retangulo HUD foi ajustado usando cartas visiveis. "
                "Confira Testar saldo antes de analisar a gravacao.")

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
            # Nao carregar a inferencia visual do arquivo anterior ao trocar video.
            self.detected_timeline = []
            self.preview_auto_mode = None
            self.preview_when = None
            self.show_frame()
        except Exception as exc:
            messagebox.showerror("Video", str(exc))

    def clear_videos(self):
        self.videos = []
        self.total = 0
        self.seek.set("00:00:00")
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
            if parse_time(self.seek.get()) > when + .01:
                self.seek.set(fmt(when))
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
            # Tenta alinhar automaticamente para o novo frame, mas jamais
            # sobrescreve regioes que o usuario marcou manualmente.
            self.auto_align_current_frame(force=False)
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
        for table in range(1, layout_count(mode) + 1):
            data = self.cfg[str(table)]
            rect = layout_roi(data, table, mode, "hero_hud")
            if rect:
                x1, y1, x2, y2 = rect
                sx, sy = VIEW_W / W, VIEW_H / H
                self.canvas.create_rectangle(
                    x1*sx, y1*sy, x2*sx, y2*sy,
                    outline="#00ff91", width=3)
                self.canvas.create_text(x1*sx, y1*sy, anchor="sw",
                                        text=f"M{table}: HUD", fill="#00ff91")
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
        try:
            hero_hud_parts(rect)
            store_layout_roi(self.cfg, table, self.layout_id(),
                             "hero_hud", rect, source="manual")
        except ValueError as exc:
            messagebox.showwarning("Marcar HUD unico", str(exc))
            self.draw()
            return
        # Modos de cartas, nick e saldo passam a ser derivados do mesmo HUD.
        for destination in range(1, layout_count(self.layout_id()) + 1):
            self.cfg[str(destination)].pop("reference", None)
            self.cfg[str(destination)]["detector"] = "bright"
        try:
            save_markings_file(default_markings_path(), self.cfg,
                               self.nick.get(), self.layout.get())
            self.markings_source = "HUDs salvos automaticamente"
            self.tell(f"HUD unico salvo nas {layout_count(self.layout_id())} mesas. "
                      "Cartas, nick e saldo identificados dentro da caixa verde.")
        except (OSError, ValueError, TypeError):
            self.tell("HUD ajustado, mas nao foi salvo no Windows. "
                      "Use Salvar configuracao.")
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
            area = layout_roi(self.cfg[str(table)], table, mode, "stack")
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
        window.geometry("900x670")
        window.minsize(650, 500)

        ttk.Label(window, text=(
            f"HUD VERDE COMPLETO do MP4: {original.width} x {original.height} pixels. "
            "Busca de nick e saldo dentro dessa area."
        )).pack(pady=(10, 5))
        # Nao cortar o HUD inteiro na janela de diagnostico: limitar ambas
        # as dimensoes, inclusive em videos 1080p/1440p/4K.
        scale = max(1, min(5, 830 // max(original.width, 1),
                           260 // max(original.height, 1)))
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
        ttk.Label(window, text="A imagem acima deve mostrar cartas, nick E saldo "
                  "do jogador. Se algum faltar, redesenhe o HUD verde.",
                  wraplength=720).pack(pady=3)

        details = tk.Text(window, height=9, width=80, wrap="word")
        details.pack(fill="both", expand=True, padx=12, pady=5)
        details.insert("end", "Leituras de regioes INTERNAS do HUD e modos OCR:\n\n")
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
        if self.frame is None or not self.videos:
            messagebox.showwarning("Nick", "Carregue o video e clique Mostrar frame.")
            return
        nick = self.nick.get().strip()
        if not nick:
            messagebox.showwarning("Nick", "Preencha o nick do jogador.")
            return
        try:
            table = int(self.table.get())
            mode = self.layout_id()
            if table > layout_count(mode):
                raise ValueError("Mesa nao aparece neste layout.")
            hud = layout_roi(self.cfg[str(table)], table, mode, "hero_hud")
            if hud is None:
                raise ValueError("Marque um HUD unico antes de verificar o nick.")
            when = parse_time(self.seek.get())
            tesseract = resource("tesseract")
            ffmpeg = resource("ffmpeg")
            if not tesseract or not ffmpeg:
                raise ValueError("Tesseract ou FFmpeg nao encontrado.")
            full_hud = native_stack_crop(self.videos, when, hud, ffmpeg)
            readings = read_nickname(full_hud, tesseract)
            matched = any(nickname_matches(line, nick) for line in readings)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            messagebox.showerror("Verificar nick", str(exc))
            return

        shown = " / ".join(readings[:8]) or "(sem leitura)"
        if matched:
            self.tell(f"Nick {nick} confirmado no HUD completo da mesa {table}.")
            messagebox.showinfo(
                "Nick reconhecido", f"Mesa {table}: {nick} confirmado.\nOCR: {shown}")
            return

        self.tell("Nick nao identificado no HUD pelo OCR local.")
        messagebox.showwarning(
            "Nick inconclusivo",
            f"O OCR buscou {nick} no HUD completo e nao confirmou.\n"
            f"Leituras: {shown}\n\n"
            "Selecione outro frame em que seu nick esteja visivel. "
            "A deteccao das suas cartas continua funcionando offline.")


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
            self.frame.crop(layout_roi(data, table, self.layout_id(), "hole")).convert("L"))
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
                 "auto_rebuy": self.auto_rebuy.get(),
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
                self.auto_rebuy.set(True)
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

    def review_payload(self):
        return {"version": 5, "videos": [asdict(v) for v in self.videos],
                "layout": self.layout.get(), "config": self.cfg,
                "threshold": self.threshold.get(),
                "nick": self.nick.get().strip(), "quick": self.quick.get(),
                "auto_export": self.auto_export.get(),
                "auto_rebuy": self.auto_rebuy.get(),
                "timeline": self.timeline,
                "detected_timeline": self.detected_timeline,
                "candidates": [asdict(c) for c in self.candidates]}

    def autosave_review(self):
        if not self.videos:
            return False
        target = latest_review_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".tmp")
            try:
                temp.write_text(json.dumps(
                    self.review_payload(), ensure_ascii=False, indent=2),
                    encoding="utf-8")
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.tell("AVISO: nao foi possivel salvar a ultima revisao no Windows.")
            return False

    def save_scan(self):
        if not self.videos:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Revisao visual", "*.json")])
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(
                self.review_payload(), ensure_ascii=False, indent=2),
                encoding="utf-8")
            self.tell("Revisao e recortes salvos em " + path)
        except Exception as exc:
            messagebox.showerror("Salvar", str(exc))

    def load_latest_review(self):
        path = latest_review_path()
        if not path.is_file():
            messagebox.showwarning(
                "Sem revisao automatica",
                "Nenhuma analise finalizada nesta versao foi salva no Windows. "
                "Use Abrir revisao se salvou um JSON em outra pasta.")
            return
        self.load_scan(str(path))

    def load_scan(self, path=None):
        if path is None:
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
                # Revisoes de versoes com API continuam acessiveis, mas
                # nao sao aceitas como perdas confirmadas automaticamente.
                entry.pop("gemini_checked", None)
                if not entry.get("confirmed", False):
                    entry["auto_verified"] = False
                    entry["pot_verified"] = False
                    entry["loss_bb"] = None
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
            self.auto_rebuy.set(True)
            self.threshold.set(str(data.get("threshold", 30)))
            self.info.configure(text=f"{len(videos)} arquivo(s) | {fmt(self.total)}")
            self.on_table_change()
            self.refresh()
            self.show_frame()
            self.tell(f"Revisao aberta: {len(self.candidates)} candidatas. Confira e exporte.")
        except Exception as exc:
            messagebox.showerror("Abrir revisao", str(exc))

    def current_output_folder(self, create=False):
        """Pasta selecionada pelo usuario, reutilizada em todas as exportacoes."""
        path = valid_export_folder(self.output_dir.get())
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    def choose_output_folder(self):
        """Alterar uma vez e lembrar no Windows entre as execucoes."""
        if self.busy:
            return
        current = self.current_output_folder()
        initial = current if current.is_dir() else current.parent
        while not initial.is_dir() and initial != initial.parent:
            initial = initial.parent
        chosen = filedialog.askdirectory(
            title="Escolha a pasta padrao para salvar as maos analisadas",
            initialdir=str(initial))
        if not chosen:
            return
        try:
            folder = save_export_folder(chosen)
            self.output_dir.set(str(folder))
            self.tell(f"Pasta padrao dos MP4 salva: {folder}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Pasta de saida", str(exc))

    def open_output_folder(self):
        try:
            folder = self.current_output_folder(create=True)
            if os.name == "nt":
                os.startfile(str(folder))
            else:
                messagebox.showinfo("Pasta de saida", str(folder))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Pasta de saida", str(exc))

    def recheck_inconclusive(self):
        """Reutiliza a ultima revisao para estimar aportes sem varrer video inteiro."""
        if self.busy:
            return
        if not self.videos or not self.candidates:
            messagebox.showwarning(
                "Triagem offline",
                "Primeiro execute ANALISAR VIDEO(S) ou abra a ultima revisao.")
            return
        try:
            threshold = float(self.threshold.get().replace(",", "."))
            if threshold <= 0:
                raise ValueError("Perda minima precisa ser positiva.")
        except ValueError as exc:
            messagebox.showerror("Triagem", str(exc))
            return
        candidates = [Candidate(**asdict(c)) for c in self.candidates]
        videos = self.videos[:]
        config = json.loads(json.dumps(self.cfg))
        self.busy = True
        self.tell("Estimando aportes por OCR nos quadros DURANTE cada mao...")
        def worker():
            try:
                revised, analyzed, priority = estimate_candidates_offline(
                    videos, config, candidates, threshold,
                    lambda msg: self.after(0, lambda m=msg: self.tell(m)))
                self.after(0, lambda: self.finished(
                    revised, self.detected_timeline[:],
                    f"Triagem offline: {analyzed} maos, {priority} prioritarias",
                    export_review=False))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self.failed(e))
        threading.Thread(target=worker, daemon=True).start()


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
                    layout_roi(self.cfg[str(table)], table, mode, "stack"),
                    resource("ffmpeg"))
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
                "Nenhuma faixa de saldo do HUD unico foi reconhecida no frame original.\n"
                "A triagem das maos pode continuar mesmo com OCR parcial.\n\n"
                "Clique 'Testar saldo' para ver o recorte ORIGINAL ampliado "
                "e as leituras brutas antes de iniciar horas de analise.\n\n"
                "Deseja analisar mesmo assim?")
        if failures:
            self.tell("OCR do frame: " + "; ".join(successes) +
                      " | falharam: " + ", ".join(failures))
        return True

    def analyze(self):
        """Duas fases offline: localizar maos e estimar aportes durante a mao."""
        if self.busy:
            return
        if not self.videos:
            messagebox.showwarning("Videos", "Adicione o video original ou partes MP4.")
            return
        try:
            threshold = float(self.threshold.get().replace(",", "."))
            if threshold <= 0:
                raise ValueError("Perda minima deve ser positiva.")
            if not self.nick.get().strip():
                raise ValueError("Preencha o nick do jogador.")
            modes = {layout_key(self.layout.get())}
            modes.update(layout_key(e["layout"]) for e in self.timeline)
            required = set()
            for mode in modes:
                required.update(range(1, layout_count(mode) + 1))
            for table in sorted(required):
                data = self.cfg[str(table)]
                if not data.get("bb"):
                    raise ValueError(f"Informe o BB da mesa {table}.")
                if data.get("detector") == "reference" and not data.get("reference"):
                    raise ValueError(f"Mesa {table}: referencia vazia.")
                if data.get("hole"):
                    roi_tuple(data["hole"])
            if not resource("tesseract") or not resource("ffmpeg"):
                raise ValueError("Instale Tesseract e FFmpeg antes da analise offline.")
            if self.auto_export.get():
                self.current_output_folder(create=True)
        except (ValueError, OSError, KeyError) as exc:
            messagebox.showerror("Configuracao", str(exc))
            return

        self.busy = True
        self.tell("Fase 1/3: localizando maos do heroi (offline)...")
        cfg = json.loads(json.dumps(self.cfg))
        videos = self.videos[:]
        hero_nick = self.nick.get().strip()
        quick = self.quick.get()
        rebuy_mode = self.auto_rebuy.get()
        layout = self.layout.get()
        events = [e.copy() for e in self.timeline]
        detections = []
        def worker():
            try:
                results = scan_videos(
                    videos, cfg, threshold,
                    lambda msg: self.after(0, lambda m=msg: self.tell(m)),
                    hero_nick=hero_nick, quick=quick,
                    initial_layout=layout, events=events,
                    detected_events=detections, auto_rebuy=rebuy_mode)
                self.after(0, lambda: self.tell(
                    f"Fase 2/3: {len(results)} maos candidatas; "
                    "OCR do stack durante cada mao..."))
                estimates, analyzed, priority = estimate_candidates_offline(
                    videos, cfg, results, threshold,
                    lambda msg: self.after(0, lambda m=msg: self.tell(m)))
                self.after(0, lambda: self.tell(
                    f"Fase 3/3: verificando quem recebeu o pote "
                    f"em {priority} maos com aporte >= {threshold:g} BB..."))
                decisions, verified, losses = confirm_candidates_by_pot_offline(
                    videos, cfg, estimates, threshold,
                    lambda msg: self.after(0, lambda m=msg: self.tell(m)))
                summary = (f"{analyzed} maos, {priority} com aporte potencial; "
                           f"{verified} destinos de pote analisados, "
                           f"{losses} perdas confirmadas")
                self.after(0, lambda: self.finished(
                    decisions, detections, summary, export_review=False,
                    auto_export_losses=True))
            except Exception as exc:
                self.after(0, lambda e=str(exc): self.failed(e))
        threading.Thread(target=worker, daemon=True).start()

    def finished(self, results, detections=None, summary="",
                 export_review=False, auto_export_losses=False):
        self.candidates = results
        self.detected_timeline = sorted(detections or [],
                                        key=lambda e: e["start"])
        self.busy = False
        self.refresh()
        saved = self.autosave_review()
        threshold = float(self.threshold.get().replace(",", "."))
        priorities = sum(
            c.hero_invested_bb is not None and
            c.hero_invested_bb >= threshold for c in results)
        confirmed = sum(c.pot_verified and c.auto_verified and
                        loss_reaches_threshold(c.loss_bb, threshold)
                        for c in results)
        self.tell(f"Analise offline: {len(results)} maos; {priorities} com "
                  f"aporte potencial, {confirmed} perdas confirmadas. "
                  + ("Revisao salva." if saved else
                     "AVISO: nao foi possivel salvar revisao.") + " " + summary)
        if auto_export_losses and self.auto_export.get() and confirmed:
            self.export(automatic_only=True)
        elif export_review and self.auto_export.get() and results:
            self.export_review_candidates(confirm=False)
        else:
            messagebox.showinfo(
                "Analise offline concluida",
                f"{len(results)} maos encontradas.\n"
                f"{priorities} com aporte potencial >= limite.\n"
                f"{confirmed} perdas com destino de pote confirmado.\n\n"
                "Somente perdas confirmadas geram MP4 automaticamente. "
                "Para casos duvidosos, use EXPORTAR PARA REVISAO.")

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
                (f"PERDA {c.loss_bb:.1f}" if c.confirmed else
                 (f"APORTE ~{c.hero_invested_bb:.1f}" if
                  c.hero_invested_bb is not None else "Sem leitura")),
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
        self.pot_choice.set(
            "Adversario levou tudo" if c.confirmed else "Nao sei")

    def preview_edge(self, field):
        idx = self.selected()
        if idx is None:
            return
        c = self.candidates[idx]
        self.seek.set(fmt(c.start if field == "start" else c.end))
        self.table.set(str(c.table))
        self.show_frame()

    def confirm(self):
        """So o usuario pode comprovar a perda sem um historico de maos."""
        idx = self.selected()
        if idx is None:
            return
        try:
            c = self.candidates[idx]
            st, en = parse_time(self.start_edit.get()), parse_time(self.end_edit.get())
            threshold = float(self.threshold.get().replace(",", "."))
            loss = float(self.loss_edit.get().replace(",", "."))
            choice = self.pot_choice.get()
            if not offline_review_decision(loss, threshold,
                                           "oponente_tudo" if choice == "Adversario levou tudo"
                                           else "hero_parte_liquido_conferido"
                                           if choice == "Heroi ganhou parte" else "incerto"):
                raise ValueError(
                    f"Para exportar, confirme que perdeu pelo menos {threshold:g} BB "
                    "LIQUIDOS e selecione um destino do pote compativel. "
                    "A estimativa de aporte nao e perda confirmada.")
            if not (0 <= st < en <= self.total):
                raise ValueError("Confira inicio e fim da mao.")
            mode_start = self.effective_layout_at(st + .01)
            mode_end = self.effective_layout_at(max(st + .01, en - .01))
            if mode_start != mode_end:
                raise ValueError("Mao cruza mudanca de mesas. Ajuste os tempos.")
            if c.table > layout_count(mode_start):
                raise ValueError("Mesa nao existe no trecho selecionado.")
            c.layout = "horizontal4" if mode_start == "auto4" else mode_start
            c.start, c.end, c.loss_bb = st, en, loss
            c.status = "PERDA LIQUIDA CONFERIDA MANUALMENTE"
            c.confirmed = True
            c.auto_verified = False
            c.pot_verified = True
            c.source = "Revisao manual offline"
            c.reliability = "Usuario conferiu o desfecho no video; resultado e BB fornecidos manualmente."
            self.refresh()
            self.autosave_review()
            self.tell(f"Perda confirmada manualmente: {loss:g} BB, mesa {c.table}. "
                      "Use EXPORTAR PERDAS.")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Conferencia da mao", str(exc))


    def exclude(self):
        idx = self.selected()
        if idx is not None:
            self.candidates[idx].excluded = True
            self.refresh()

    def export_review_candidates(self, confirm=True):
        """Entrega cortes reais de todas as maos detectadas, sem depender de API.

        Estes clips NAO sao classificados como perdas confirmadas. Sao uma
        maneira pratica de conferir o pote e o aporte do heroi offline.
        """
        if self.busy:
            return
        if not self.videos or not self.candidates:
            messagebox.showwarning(
                "Revisao offline",
                "Adicione um video e execute ANALISAR VIDEO(S) offline, "
                "ou clique Abrir ultima revisao para aproveitar os horarios.")
            return
        candidates = [c for c in self.candidates
                      if not c.excluded and c.end > c.start
                      and 1 <= c.table <= 4]
        if not candidates:
            messagebox.showwarning("Revisao offline",
                                   "Nao ha maos candidatas para exportar.")
            return
        candidates.sort(key=lambda c: (
            c.hero_invested_bb is None,
            -(c.hero_invested_bb or 0),
            c.start))
        if confirm and not messagebox.askyesno(
                "Exportar cortes para revisao",
                f"Gerar {len(candidates)} MP4 separados para revisao?\n\n"
                "Todos serao marcados como PENDENTES. "
                "Eles NAO representam perdas comprovadas de 30 BB.\n\n"
                "A triagem e 100% local, sem API e sem rede.\n\n"
                "Deseja continuar?"):
            return
        try:
            dest = self.current_output_folder(create=True) / "Maos para revisar"
            dest.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Pasta dos MP4", str(exc))
            return
        videos = self.videos[:]
        ffmpeg = resource("ffmpeg")
        if not ffmpeg:
            messagebox.showerror("FFmpeg", "FFmpeg nao encontrado no Windows.")
            return
        self.busy = True
        self.tell(f"Exportando {len(candidates)} maos em MP4 para revisao offline...")
        def worker():
            index = []
            for i, c in enumerate(candidates, 1):
                name = (f"REVISAO_{i:03}_mesa{c.table}_"
                        f"{fmt(c.start).replace(':', '-')}_PENDENTE.mp4")
                destination = dest / name
                status = "OK"
                try:
                    clip = Clip(
                        c.start, c.end, c.table,
                        0.0, "Candidato pendente de revisao",
                        "Offline", "", False)
                    export_clip(videos, clip, destination, ffmpeg, layout=c.layout)
                except Exception as exc:
                    status = "ERRO: " + str(exc)[-180:]
                    destination.unlink(missing_ok=True)
                index.append({
                    "arquivo": name, "mesa": c.table, "layout": c.layout,
                    "inicio": fmt(c.start), "fim": fmt(c.end),
                    "nick": c.nick, "perda_bb": "",
                    "aporte_estimado_bb": c.hero_invested_bb,
                    "classificacao": "PENDENTE - NAO E PERDA CONFIRMADA",
                    "origem": c.source, "estado_analise": c.status,
                    "resultado_exportacao": status
                })
                self.after(0, lambda k=i, st=status:
                           self.tell(f"Revisao offline: MP4 {k}/{len(candidates)} - {st}"))
            try:
                with (dest / "indice_revisao_offline.csv").open(
                        "w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.DictWriter(
                        fh, fieldnames=list(index[0]), delimiter=";")
                    writer.writeheader()
                    writer.writerows(index)
            except OSError:
                self.after(0, lambda:
                           self.tell("AVISO: os MP4 foram processados, "
                                     "mas o CSV de revisao nao foi salvo."))
            def done():
                self.busy = False
                succeeded = sum(item["resultado_exportacao"] == "OK"
                                for item in index)
                self.tell(f"Revisao offline: {succeeded}/{len(candidates)} "
                          f"MP4 gerados em {dest}")
                messagebox.showinfo(
                    "Cortes de revisao",
                    f"{succeeded} de {len(candidates)} MP4 gerados.\n\n"
                    f"Pasta: {dest}\n\n"
                    "IMPORTANTE: sao jogadas candidatas, nao perdas confirmadas. "
                    "Confira os potes e descarte as que nao perderam 30 BB.")
            self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    def export(self, folder=None, automatic_only=False):
        if self.busy:
            return
        try:
            threshold = float(self.threshold.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("BB", "Perda minima invalida.")
            return
        eligible = eligible_losses(
            self.candidates, threshold, automatic_only=automatic_only,
            require_pot_evidence=True)
        if folder is None:
            try:
                folder = str(self.current_output_folder(create=True))
            except (OSError, ValueError) as exc:
                messagebox.showerror("Pasta dos MP4", str(exc))
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
                                 "leitura_consistente", "origem", "status",
                                 "confiabilidade", "aporte_heroi_bb",
                                 "vencedor_pote", "pote_confirmado", "rebuy_visto"])
                for c in self.candidates:
                    writer.writerow([fmt(c.start), fmt(c.end), c.table, c.layout,
                                     c.nick, c.stack_before, c.stack_after,
                                     c.loss_bb, "SIM" if c.auto_verified else "NAO",
                                     c.source, c.status, c.reliability,
                                     c.hero_invested_bb, c.winner_nick,
                                     "SIM" if c.pot_verified else "NAO",
                                     c.auto_rebuy_seen])
        except OSError as exc:
            messagebox.showerror("Relatorio", str(exc))
            return

        if not eligible:
            self.auto_export_folder = None
            if self.auto_rebuy.get():
                pending = sum(not c.excluded and not c.confirmed
                              for c in self.candidates)
                self.tell(f"Nenhum pote perdido >= {threshold:g} BB confirmado. "
                          f"{pending} maos ainda pendentes de verificacao.")
                messagebox.showwarning(
                    "Nenhum pote confirmado para exportar",
                    "Nenhuma mao foi confirmada como perda de pelo menos "
                    f"{threshold:g} BB com aporte do heroi e pote ao adversario.\n\n"
                    "O saldo voltar para 100 BB com rebuy nao prova perda.\n"
                    "Nao foram exportados cortes incertos.\n\n"
                    f"Relatorio: {report}\n"
                    "Para revisar as jogadas, use EXPORTAR PARA REVISAO "
                    "ou selecione uma mao e confirme o pote e a perda liquida. "
                    "A ultima revisao permanece salva.")
            else:
                self.tell("0 perdas com leitura de saldo suficiente. "
                          "Confira as marcacoes e o OCR.")
                messagebox.showwarning(
                    "Nenhuma perda exportavel",
                    "Nenhuma perda foi confirmada pelo OCR do saldo.\n\n"
                    f"Relatorio: {report}\n"
                    "Confira a regiao do HUD verde e use Testar saldo.")
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
                    clip = Clip(c.start, c.end, c.table, c.loss_bb, "Pote confirmado",
                                "Offline", "", True)
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
                             "classificacao": (
                                 "Perda liquida confirmada manualmente" if c.confirmed
                                 else "Revisar"),
                             "origem": c.source,
                             "mesa": c.table, "disposicao": c.layout,
                             "inicio": fmt(c.start), "fim": fmt(c.end),
                             "saldo_antes": c.stack_before,
                             "saldo_depois": c.stack_after,
                             "aporte_heroi_bb": c.hero_invested_bb,
                             "vencedor_pote": c.winner_nick,
                             "pote_confirmado": c.pot_verified,
                             "rebuy_visto": c.auto_rebuy_seen,
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
                    "A confirmacao automatica usa OCR da mesa e pode falhar. "
                    "Confira os cortes antes de enviar ao instrutor.")
            self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    GUI().mainloop()
