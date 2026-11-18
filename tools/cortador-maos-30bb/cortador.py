# -*- coding: utf-8 -*-
"""Cortador de Mãos PLO - interface local; não auxilia decisões durante o jogo."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_TITLE = "Cortador de Mãos PLO • Revisão de Sessões"
TIME_FMT = "%Y-%m-%d %H:%M:%S"
DEFAULT_HERO = "~Pulgar~"


def resource(binary: str) -> str:
    here = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    exe = binary + (".exe" if os.name == "nt" else "")
    local = here / exe
    return str(local) if local.exists() else (shutil.which(exe) or shutil.which(binary) or "")


def run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    kwargs = {"capture_output": True, "text": True, "errors": "replace", "timeout": timeout}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(args, **kwargs)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Erro desconhecido")[-1400:])
    return result


def fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600:02}:{(sec // 60) % 60:02}:{sec % 60:02}"


def parse_time(value: str) -> float:
    s = str(value).strip().replace(",", ".")
    if not s:
        raise ValueError("Tempo vazio.")
    if ":" not in s:
        return float(s)
    parts = [float(p) for p in s.split(":")]
    if len(parts) not in (2, 3):
        raise ValueError(f"Tempo inválido: {s}")
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def parse_money(s: str) -> float:
    value = re.sub(r"[^0-9,.\-]", "", str(s))
    if not value:
        raise ValueError("Valor monetário ausente")
    if "," in value and "." in value:
        value = value.replace(",", "") if value.rfind(".") > value.rfind(",") else value.replace(".", "").replace(",", ".")
    elif "," in value:
        value = value.replace(",", ".")
    return float(value)


AMOUNT = re.compile(r"(?:R\$|\$|€)?\s*(-?\d[\d.,]*)", re.I)


def amounts(action: str) -> list[float]:
    return [parse_money(m.group(1)) for m in AMOUNT.finditer(action)]


@dataclass
class Video:
    path: str
    duration: float
    width: int
    height: int
    has_audio: bool
    start: float = 0.0


@dataclass
class Clip:
    start: float
    end: float
    table: int = 0
    loss_bb: float = 0.0
    label: str = ""
    origin: str = "manual"
    hand_id: str = ""
    confirmed: bool = False


@dataclass
class HistoryHand:
    hand_id: str
    table_name: str
    timestamp: str
    bb: float
    net: float
    loss_bb: float


def probe(path: str) -> Video:
    ffprobe = resource("ffprobe")
    if not ffprobe:
        raise RuntimeError("FFprobe não encontrado. Instale FFmpeg ou copie ffprobe.exe ao lado do programa.")
    obj = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", path], timeout=40).stdout)
    streams = obj.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError(f"Não há vídeo em {Path(path).name}")
    duration = float(obj.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise RuntimeError("Duração inválida em " + path)
    return Video(path, duration, int(video["width"]), int(video["height"]),
                 any(s.get("codec_type") == "audio" for s in streams))


def split_history(text: str) -> list[str]:
    # Formatos comuns de histórico PokerStars/convertidos.
    markers = re.compile(r"^(?:PokerStars Hand #|Hand #\d+|Game Hand #|Game #\d+|Winamax Poker - HandId:|#Game No\s*:)", re.M | re.I)
    starts = [m.start() for m in markers.finditer(text)]
    if not starts:
        raise ValueError("Histórico não reconhecido. Exporte as mãos como TXT (formato PokerStars/convertido) no DriveHUD.")
    return [text[starts[i]:(starts[i + 1] if i + 1 < len(starts) else len(text))]
            for i in range(len(starts))]


def extract_stakes(header: str) -> float:
    # Padrão "(0.05/0.10)" ou "($0.05/$0.10 USD)".
    match = re.search(r"\(\s*(?:R\$|\$|€)?\s*(\d[\d.,]*)\s*/\s*(?:R\$|\$|€)?\s*(\d[\d.,]*)", header)
    if not match:
        match = re.search(r"(?:Blinds|Stakes)\s*[:=]?\s*(\d[\d.,]*)\s*/\s*(\d[\d.,]*)", header, re.I)
    return parse_money(match.group(2)) if match else 0.0


def parse_hand(chunk: str, hero: str) -> HistoryHand | None:
    lines = chunk.splitlines()
    if not lines or not hero:
        return None
    header = lines[0]
    id_match = re.search(r"(?:Hand|Game|HandId)\s*#?\s*:?\s*([0-9]+)", header, re.I)
    hand_id = id_match.group(1) if id_match else ""
    date = re.search(r"\b(20\d\d[-/]\d\d[-/]\d\d)[ T](\d\d:\d\d:\d\d)", header)
    timestamp = (date.group(1).replace("/", "-") + " " + date.group(2)) if date else ""
    bb = extract_stakes(header)
    if bb <= 0:
        return None
    table_m = re.search(r"^Table\s+['\"]?(.+?)['\"]?\s+(?:\d+-max|Seat #|is the button)", chunk, re.M | re.I)
    table_name = table_m.group(1).strip("'\" ") if table_m else "Mesa não identificada"

    spent, returned, collected = 0.0, 0.0, 0.0
    street_paid = 0.0
    hero_re = re.compile(r"^" + re.escape(hero) + r":\s*(.*)$", re.I)
    found_action = False
    summary_win = 0.0
    for line in lines:
        line = line.strip()
        if re.match(r"^\*\*\*\s*(FLOP|TURN|RIVER|SHOW DOWN)", line, re.I):
            street_paid = 0.0
        # Recebimento devolvido após aposta não paga.
        refund = re.search(r"Uncalled bet\s*\(?\s*(?:R\$|\$)?([\d.,]+)\)?\s+returned to\s+(.+)$", line, re.I)
        if refund and refund.group(2).strip().lower() == hero.lower():
            returned += parse_money(refund.group(1))
        m = hero_re.match(line)
        if m:
            act = m.group(1)
            low = act.lower()
            nums = amounts(act)
            if low.startswith(("posts ", "calls ", "bets ", "completes ")) and nums:
                spent += nums[0]
                street_paid += nums[0]
                found_action = True
            elif low.startswith("raises ") and nums:
                target = nums[-1]  # 'raises X to Y': Y é a contribuição total da rua.
                increment = max(0.0, target - street_paid)
                spent += increment
                street_paid += increment
                found_action = True
            if ("collected " in low or "wins " in low) and nums:
                collected += nums[0]
                found_action = True
        # Alguns formatos creditam ganhos só no SUMÁRIO.
        if re.search(r"^Seat \d+:\s*" + re.escape(hero) + r"\b", line, re.I):
            win = re.search(r"(?:collected|won)\s*\(?\s*(?:R\$|\$)?\s*([\d.,]+)", line, re.I)
            if win:
                summary_win += parse_money(win.group(1))

    if not found_action:
        return None
    if collected <= 0 and summary_win > 0:
        collected = summary_win
    net = collected + returned - spent
    return HistoryHand(hand_id, table_name, timestamp, bb, net, max(0, -net / bb))


def read_history(path: str, hero: str) -> list[HistoryHand]:
    raw = Path(path).read_bytes()
    decoded = ""
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin1"):
        try:
            decoded = raw.decode(encoding)
            break
        except UnicodeError:
            pass
    if not decoded:
        raise RuntimeError("Não foi possível ler o histórico em texto")
    hands = [parse_hand(part, hero) for part in split_history(decoded)]
    return [h for h in hands if h is not None]


def file_at(videos: list[Video], t: float) -> tuple[Video, float]:
    for v in videos:
        if v.start <= t < v.start + v.duration:
            return v, t - v.start
    if videos and abs(t - (videos[-1].start + videos[-1].duration)) < .01:
        return videos[-1], videos[-1].duration
    raise ValueError("Tempo fora da gravação")


def crop_filter(v: Video, table: int, layout: str = "grid2x2") -> str:
    if table not in (1, 2, 3, 4):
        raise ValueError("Selecione a mesa 1, 2, 3 ou 4.")
    if layout in ("horizontal1", "horizontal2", "horizontal3", "horizontal4"):
        # 1 a 4 mesas lado a lado, com largura igual em cada trecho do video.
        count = int(layout[-1])
        if table > count:
            raise ValueError(f"Mesa {table} nao existe no layout de {count} mesa(s).")
        x = round(v.width * (table - 1) / count)
        x_end = round(v.width * table / count)
        w, h = x_end - x, v.height
        y = 0
        scale = "960:540" if count == 1 else "720:1080"
    elif layout == "grid2x2":
        w, h = v.width // 2, v.height // 2
        x, y = (table - 1) % 2 * w, (table - 1) // 2 * h
        scale = "960:540"
    else:
        raise ValueError("Layout de mesas desconhecido.")
    # Escalamos sem deformar a mesa: faixas laterais quando necessario.
    return (f"crop={w}:{h}:{x}:{y},"
            f"scale={scale}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={scale.replace(':', ':')}:(ow-iw)/2:(oh-ih)/2,"
            f"fps=25,format=yuv420p")


def export_clip(videos: list[Video], clip: Clip, dest: Path, ffmpeg: str, layout: str = "grid2x2") -> None:
    if clip.table not in (1, 2, 3, 4):
        raise ValueError("Mesa inválida")
    total = sum(v.duration for v in videos)
    if clip.end <= clip.start or clip.start < 0 or clip.end > total + .01:
        raise ValueError("Intervalo inválido no vídeo")
    with tempfile.TemporaryDirectory(prefix="cortador_") as tmp:
        pieces = []
        for i, v in enumerate(videos):
            left = max(clip.start, v.start)
            right = min(clip.end, v.start + v.duration)
            if right - left <= .04:
                continue
            length = right - left
            part = Path(tmp) / f"p_{i:03}.mp4"
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                       "-ss", f"{left - v.start:.3f}", "-i", v.path]
            if not v.has_audio:
                command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            command += ["-t", f"{length:.3f}", "-map", "0:v:0"]
            command += ["-map", ("0:a:0" if v.has_audio else "1:a:0"),
                        "-vf", crop_filter(v, clip.table, layout),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-ar", "44100",
                        "-movflags", "+faststart", "-shortest", str(part)]
            run(command, timeout=max(180, int(length * 8)))
            pieces.append(part)
        if not pieces:
            raise RuntimeError("Nenhuma parte de vídeo corresponde ao intervalo.")
        if len(pieces) == 1:
            shutil.move(str(pieces[0]), str(dest))
            return
        manifest = Path(tmp) / "lista.txt"
        manifest.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
        run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(manifest),
             "-c", "copy", "-movflags", "+faststart", str(dest)], timeout=180)


class Editor(tk.Toplevel):
    def __init__(self, root: "App", clip: Clip | None = None):
        super().__init__(root)
        self.root = root
        self.original = clip
        self.title("Editar / adicionar mão")
        self.geometry("430x450")
        self.resizable(False, False)
        current = root.position.get()
        data = clip or Clip(max(0, current - 60), min(root.total, current + 15), getattr(root, "last_table", 1), 31, "Mão para revisão")
        self.vars = {
            "start": tk.StringVar(value=fmt(data.start)),
            "end": tk.StringVar(value=fmt(data.end)),
            "table": tk.StringVar(value=str(data.table or 1)),
            "loss": tk.StringVar(value=f"{data.loss_bb:g}"),
            "label": tk.StringVar(value=data.label),
        }
        labels = [("Início (linha do tempo total)", "start"),
                  ("Fim (linha do tempo total)", "end"),
                  ("Mesa (1-4, da esquerda para a direita)", "table"),
                  ("Perda líquida (BB)", "loss"),
                  ("Descrição da mão", "label")]
        for row, (label, field) in enumerate(labels):
            ttk.Label(self, text=label).grid(row=row * 2, column=0, sticky="w", padx=12, pady=(8, 0))
            ttk.Entry(self, textvariable=self.vars[field], width=40).grid(
                row=row * 2 + 1, column=0, sticky="ew", padx=12)
        self.confirmed = tk.BooleanVar(value=data.confirmed)
        ttk.Checkbutton(self, text="Perda e limites conferidos", variable=self.confirmed).grid(
            row=10, column=0, sticky="w", padx=12, pady=5)
        ttk.Button(self, text="Salvar mão", command=self.save).grid(row=11, column=0, pady=10)
        self.grab_set()

    def save(self):
        try:
            start = parse_time(self.vars["start"].get())
            end = parse_time(self.vars["end"].get())
            table = int(self.vars["table"].get())
            loss = float(self.vars["loss"].get().replace(",", "."))
            if table not in (1, 2, 3, 4) or start < 0 or end > self.root.total or end <= start:
                raise ValueError("Confira a mesa e os tempos (dentro da duração total).")
            if loss <= 0:
                raise ValueError("Informe a perda em BB (valor positivo).")
            clip = self.original or Clip(start, end)
            clip.start, clip.end, clip.table, clip.loss_bb = start, end, table, loss
            clip.label = self.vars["label"].get().strip() or "Mão para revisão"
            clip.confirmed = self.confirmed.get()
            if self.original is None:
                self.root.clips.append(clip)
            self.root.refresh()
            self.destroy()
        except (ValueError, TypeError) as e:
            messagebox.showerror("Dados inválidos", str(e), parent=self)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1160x820")
        self.minsize(990, 730)
        self.videos: list[Video] = []
        self.clips: list[Clip] = []
        self.total = 0.0
        self.position = tk.DoubleVar(value=0)
        self.hero = tk.StringVar(value=DEFAULT_HERO)
        self.min_bb = tk.StringVar(value="30")
        self.first_datetime = tk.StringVar()
        self.hh_offset = tk.StringVar(value="0")
        self.mapping: dict[str, int] = {}
        self.photo = None
        self.preview_after = None
        self.preview_path = Path(tempfile.gettempdir()) / f"cortador_preview_{os.getpid()}.png"
        self.preview_size = (0, 0)
        self.result_log: list[dict] = []
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Button(top, text="1. Adicionar vídeos MP4", command=self.add_videos).pack(side="left", padx=3)
        ttk.Button(top, text="Carregar projeto", command=self.load_project).pack(side="left", padx=3)
        ttk.Button(top, text="Salvar projeto", command=self.save_project).pack(side="left", padx=3)
        ttk.Button(top, text="Importar lista CSV", command=self.import_csv).pack(side="left", padx=3)
        ttk.Button(top, text="Importar DriveHUD TXT", command=self.import_hh).pack(side="left", padx=3)
        settings = ttk.Frame(self, padding=(12, 3))
        settings.pack(fill="x")
        for title, var, width in [("Seu nick:", self.hero, 16),
                                  ("Perda mínima BB:", self.min_bb, 5),
                                  ("Início do 1º vídeo (AAAA-MM-DD HH:MM:SS):", self.first_datetime, 21),
                                  ("Ajuste de horário HH (seg):", self.hh_offset, 6)]:
            ttk.Label(settings, text=title).pack(side="left", padx=(5, 2))
            ttk.Entry(settings, textvariable=var, width=width).pack(side="left", padx=(0, 7))
        ttk.Label(self, text="Os vídeos são considerados consecutivos; cortes entre arquivos também são possíveis.",
                  padding=(12, 3)).pack(anchor="w")
        self.files_label = ttk.Label(self, text="Nenhum vídeo carregado.", padding=(12, 2))
        self.files_label.pack(anchor="w")
        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=5)
        viewer = ttk.Frame(body)
        body.add(viewer, weight=3)
        self.canvas = tk.Canvas(viewer, bg="#161c23", width=840, height=430, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(420, 180, fill="white",
                                text="Adicione os vídeos para visualizar as quatro mesas.", tags="placeholder")
        self.canvas.bind("<Button-1>", self.click_preview)
        controls = ttk.Frame(viewer)
        controls.pack(fill="x")
        self.slider = ttk.Scale(controls, orient="horizontal", variable=self.position,
                                command=self.on_seek)
        self.slider.pack(side="left", fill="x", expand=True)
        self.time_label = ttk.Label(controls, text="00:00:00 / 00:00:00", width=26)
        self.time_label.pack(side="left", padx=10)
        ttk.Label(viewer, text="Clique num quadrante da imagem para selecionar a mesa (1-4). Use a barra para navegar.",
                  padding=4).pack(anchor="w")
        editor = ttk.Frame(body)
        body.add(editor, weight=2)
        columns = ("inicio", "fim", "mesa", "perda", "conferida", "origem", "descricao")
        self.tree = ttk.Treeview(editor, columns=columns, show="headings", height=9, selectmode="extended")
        widths = (98, 98, 75, 85, 90, 100, 390)
        for col, title, width in zip(columns, ("Início", "Fim", "Mesa", "Perda BB", "Conferida", "Origem", "Descrição"), widths):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=50, stretch=(col == "descricao"))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _: self.edit_clip())
        buttons = ttk.Frame(editor, padding=(0, 8))
        buttons.pack(fill="x")
        for txt, cmd in [("Nova mão", self.add_clip),
                         ("Editar mão", self.edit_clip),
                         ("Ir para a mão", self.jump_to_clip),
                         ("Excluir", self.delete_clip),
                         ("Mapear mesas do histórico", self.map_tables),
                         ("Exportar MP4", self.export)]:
            ttk.Button(buttons, text=txt, command=cmd).pack(side="left", padx=4)
        self.status = ttk.Label(self, text="Pronto. Para identificar perdas automaticamente, importe o histórico do DriveHUD.",
                                 padding=10)
        self.status.pack(fill="x")

    def alert(self, text: str):
        self.status.config(text=text)
        self.update_idletasks()

    def add_videos(self):
        paths = filedialog.askopenfilenames(title="Selecione Poker_Parte_01 até Poker_Parte_06 na ordem",
                                            filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.avi"), ("Todos", "*.*")])
        if not paths:
            return
        try:
            by_name = sorted(paths, key=lambda x: [int(t) if t.isdigit() else t.lower()
                                                     for t in re.split(r"(\d+)", Path(x).name)])
            existing = {v.path.lower() for v in self.videos}
            for p in by_name:
                if p.lower() not in existing:
                    v = probe(p)
                    v.start = self.total
                    self.videos.append(v)
                    self.total += v.duration
                    existing.add(p.lower())
            self.slider.configure(to=max(1, self.total))
            self.files_label.config(text=f"{len(self.videos)} vídeos | {fmt(self.total)} de gravação | "
                                         + ", ".join(Path(v.path).name for v in self.videos))
            self.position.set(0)
            self.schedule_preview()
            self.alert("Vídeos carregados. Clique em uma mesa ou importe histórico para localizar perdas.")
        except Exception as e:
            messagebox.showerror("Falha ao carregar vídeo", str(e))

    def on_seek(self, _=None):
        self.time_label.config(text=f"{fmt(self.position.get())} / {fmt(self.total)}")
        self.schedule_preview()

    def schedule_preview(self):
        if self.preview_after is not None:
            self.after_cancel(self.preview_after)
        self.preview_after = self.after(220, self.render_preview)

    def render_preview(self):
        self.preview_after = None
        if not self.videos or not resource("ffmpeg"):
            return
        try:
            when = min(self.position.get(), max(0.0, self.total - .1))
            video, local = file_at(self.videos, when)
            run([resource("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
                 "-ss", f"{local:.2f}", "-i", video.path,
                 "-frames:v", "1", "-vf",
                 "scale=840:460:force_original_aspect_ratio=decrease", str(self.preview_path)], timeout=40)
            self.photo = tk.PhotoImage(file=str(self.preview_path))
            self.canvas.delete("all")
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            x0 = max(0, (cw - self.photo.width()) // 2)
            y0 = max(0, (ch - self.photo.height()) // 2)
            self.preview_size = (x0, y0, self.photo.width(), self.photo.height())
            self.canvas.create_image(x0, y0, image=self.photo, anchor="nw")
            self.canvas.create_line(x0 + self.photo.width() // 2, y0,
                                    x0 + self.photo.width() // 2, y0 + self.photo.height(),
                                    fill="#f4c95d", width=2)
            self.canvas.create_line(x0, y0 + self.photo.height() // 2,
                                    x0 + self.photo.width(), y0 + self.photo.height() // 2,
                                    fill="#f4c95d", width=2)
            for table in range(1, 5):
                ix = (table - 1) % 2
                iy = (table - 1) // 2
                self.canvas.create_text(x0 + 28 + ix * self.photo.width() // 2,
                                        y0 + 20 + iy * self.photo.height() // 2,
                                        text=f"M{table}", fill="yellow", font=("Arial", 13, "bold"))
        except Exception as e:
            self.alert(f"Prévia indisponível: {e}")

    def click_preview(self, event):
        x0, y0, w, h = self.preview_size
        if not w or not (x0 <= event.x < x0 + w and y0 <= event.y < y0 + h):
            return
        table = 1 + int((event.x - x0) >= w / 2) + 2 * int((event.y - y0) >= h / 2)
        self.alert(f"Mesa {table} selecionada. Para adicionar recorte, clique em 'Nova mão'.")
        self.last_table = table

    def add_clip(self):
        if not self.videos:
            messagebox.showwarning("Vídeos ausentes", "Adicione vídeos primeiro.")
            return
        Editor(self)

    def selected_indices(self) -> list[int]:
        return sorted([int(iid) for iid in self.tree.selection() if iid.isdigit()])

    def edit_clip(self):
        idx = self.selected_indices()
        if not idx:
            messagebox.showinfo("Seleção", "Selecione uma mão da tabela para editar.")
            return
        Editor(self, self.clips[idx[0]])

    def jump_to_clip(self):
        idx = self.selected_indices()
        if idx:
            self.position.set(self.clips[idx[0]].start)
            self.on_seek()

    def delete_clip(self):
        idx = self.selected_indices()
        for i in reversed(idx):
            self.clips.pop(i)
        self.refresh()

    def refresh(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.clips.sort(key=lambda c: c.start)
        for i, c in enumerate(self.clips):
            self.tree.insert("", "end", iid=str(i), values=(
                fmt(c.start), fmt(c.end), c.table or "?", f"{c.loss_bb:.1f}",
                "SIM" if c.confirmed else "NÃO", c.origin, c.label))
        self.alert(f"{len(self.clips)} mãos na lista. Confira perdas e limites antes de exportar.")

    def import_csv(self):
        if not self.videos:
            messagebox.showwarning("Vídeos ausentes", "Carregue os vídeos antes da lista CSV.")
            return
        file = filedialog.askopenfilename(filetypes=[("Lista de mãos CSV", "*.csv")])
        if not file:
            return
        try:
            with open(file, encoding="utf-8-sig", newline="") as f:
                sniff = f.read(2048)
                f.seek(0)
                delim = ";" if sniff.count(";") > sniff.count(",") else ","
                reader = csv.DictReader(f, delimiter=delim)
                count = 0
                for row in reader:
                    def col(*names):
                        for name in names:
                            if row.get(name) not in (None, ""):
                                return row[name]
                        return ""
                    start = parse_time(col("inicio_global", "inicio", "start"))
                    end = parse_time(col("fim_global", "fim", "end"))
                    table = int(col("mesa", "table") or "0")
                    loss = float((col("perda_bb", "loss_bb", "bb") or "0").replace(",", "."))
                    label = col("descricao", "label", "id") or "Importado do CSV"
                    if start >= 0 and end <= self.total and start < end:
                        self.clips.append(Clip(start, end, table, loss, label, "CSV", "", False))
                        count += 1
            self.refresh()
            messagebox.showinfo("Importação", f"{count} mãos adicionadas. Revise antes de exportar.")
        except Exception as e:
            messagebox.showerror("Erro no CSV", str(e))

    def import_hh(self):
        if not self.videos:
            messagebox.showwarning("Vídeos ausentes", "Adicione os vídeos primeiro.")
            return
        file = filedialog.askopenfilename(title="Histórico DriveHUD exportado em texto",
                                           filetypes=[("Histórico TXT", "*.txt *.log"), ("Todos", "*.*")])
        if not file:
            return
        try:
            video_start = datetime.strptime(self.first_datetime.get().strip(), TIME_FMT)
            offset = float(self.hh_offset.get().replace(",", "."))
            min_bb = float(self.min_bb.get().replace(",", "."))
            hands = read_history(file, self.hero.get().strip())
            if not hands:
                raise ValueError("Nenhuma ação do jogador foi encontrada. Confira o nick e o formato do arquivo.")
            # O horário de cada mão identifica aproximadamente o início.
            table_groups: dict[str, list[HistoryHand]] = {}
            for h in hands:
                table_groups.setdefault(h.table_name, []).append(h)
            next_table_start: dict[str, float] = {}
            candidates = []
            for table_name, group in table_groups.items():
                ordered = sorted((h for h in group if h.timestamp), key=lambda h: h.timestamp)
                for i, hand in enumerate(ordered):
                    start = (datetime.strptime(hand.timestamp, TIME_FMT) - video_start).total_seconds() + offset
                    if hand.loss_bb <= min_bb or not (0 <= start < self.total):
                        continue
                    if i + 1 < len(ordered):
                        next_start = (datetime.strptime(ordered[i + 1].timestamp, TIME_FMT) - video_start).total_seconds() + offset
                    else:
                        next_start = start + 80
                    # A próxima mão na mesma mesa delimita a anterior, com duração máxima conservadora.
                    end = min(self.total, max(start + 10, min(next_start, start + 150)))
                    table = self.mapping.get(table_name, 0)
                    c = Clip(max(0, start - 3), end, table, hand.loss_bb,
                             f"{table_name} | {hand.hand_id} | {hand.timestamp}",
                             "DriveHUD", hand.hand_id, False)
                    candidates.append(c)
            self.clips.extend(candidates)
            self.refresh()
            unseen = sorted({h.table_name for h in hands if h.table_name not in self.mapping})
            messagebox.showinfo("Histórico lido",
                                f"{len(hands)} mãos interpretadas; {len(candidates)} perdas acima de {min_bb:g} BB "
                                f"localizadas na linha do tempo.\n\n"
                                "É necessário revisar início/fim e mapear a mesa de cada mão.\n"
                                "O horário do DriveHUD pode estar em outro fuso; use o campo 'Ajuste de horário'.\n\n"
                                + (f"Mesas sem mapeamento: {len(unseen)}" if unseen else "Mapeamento carregado."))
            if unseen and candidates:
                self.map_tables()
        except Exception as e:
            messagebox.showerror("Importação DriveHUD", str(e) +
                                 "\n\nPreencha a data/hora inicial do vídeo e confira o nick.")

    def map_tables(self):
        table_names = sorted({c.label.split(" | ")[0] for c in self.clips if c.origin == "DriveHUD"})
        if not table_names:
            messagebox.showinfo("Mapeamento", "Importe primeiro o histórico DriveHUD.")
            return
        win = tk.Toplevel(self)
        win.title("Posição das mesas nos 4 quadrantes")
        win.geometry("540x" + str(min(550, 130 + 37 * len(table_names))))
        ttk.Label(win, text="Associe o nome da mesa do histórico à posição no vídeo:").pack(pady=10)
        variables: dict[str, tk.StringVar] = {}
        for name in table_names:
            row = ttk.Frame(win)
            row.pack(fill="x", padx=15, pady=3)
            ttk.Label(row, text=name[:48], width=46).pack(side="left")
            v = tk.StringVar(value=str(self.mapping.get(name, 1)))
            ttk.Combobox(row, textvariable=v, values=["1", "2", "3", "4"], width=4,
                         state="readonly").pack(side="left")
            variables[name] = v
        def save():
            for name, var in variables.items():
                self.mapping[name] = int(var.get())
            for clip in self.clips:
                if clip.origin == "DriveHUD":
                    clip.table = self.mapping.get(clip.label.split(" | ")[0], clip.table)
            self.refresh()
            win.destroy()
        ttk.Button(win, text="Salvar mapa das mesas", command=save).pack(pady=10)

    def save_project(self):
        if not self.videos:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Projeto PLO", "*.json")])
        if not path:
            return
        content = {"version": 1, "videos": [asdict(v) for v in self.videos],
                   "clips": [asdict(c) for c in self.clips], "hero": self.hero.get(),
                   "minimum_bb": self.min_bb.get(), "first_datetime": self.first_datetime.get(),
                   "offset": self.hh_offset.get(), "mapping": self.mapping}
        Path(path).write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")
        self.alert(f"Projeto salvo em {path}")

    def load_project(self):
        path = filedialog.askopenfilename(filetypes=[("Projeto PLO", "*.json")])
        if not path:
            return
        try:
            content = json.loads(Path(path).read_text(encoding="utf-8"))
            videos = [Video(**v) for v in content["videos"]]
            missing = [v.path for v in videos if not Path(v.path).exists()]
            if missing:
                raise FileNotFoundError("Vídeos ausentes:\n" + "\n".join(missing))
            self.videos = videos
            self.total = sum(v.duration for v in videos)
            self.clips = [Clip(**c) for c in content["clips"]]
            self.hero.set(content.get("hero", DEFAULT_HERO))
            self.min_bb.set(content.get("minimum_bb", "30"))
            self.first_datetime.set(content.get("first_datetime", ""))
            self.hh_offset.set(content.get("offset", "0"))
            self.mapping = content.get("mapping", {})
            self.slider.configure(to=max(1, self.total))
            self.files_label.config(text=f"{len(videos)} vídeos | {fmt(self.total)} de gravação")
            self.refresh()
            self.schedule_preview()
        except Exception as e:
            messagebox.showerror("Erro no projeto", str(e))

    def export(self):
        if not self.videos:
            return
        ffmpeg = resource("ffmpeg")
        if not ffmpeg:
            messagebox.showerror("FFmpeg", "FFmpeg não encontrado. Instale-o ou deixe ffmpeg.exe ao lado do programa.")
            return
        try:
            minimum = float(self.min_bb.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Filtro", "Valor de BB inválido.")
            return
        selected = self.selected_indices()
        pool = [(i, self.clips[i]) for i in (selected or range(len(self.clips)))]
        candidates = [(i, c) for i, c in pool if c.loss_bb > minimum and c.table in (1, 2, 3, 4)
                      and c.end > c.start and c.end <= self.total]
        if not candidates:
            messagebox.showinfo("Sem mãos elegíveis",
                                "Nenhuma mão com perda > limite, mesa mapeada e horários válidos.")
            return
        unconfirmed = sum(not c.confirmed for _, c in candidates)
        if unconfirmed and not messagebox.askyesno(
            "Recortes não conferidos",
            f"{unconfirmed} de {len(candidates)} mãos não foram conferidas visualmente.\n"
            "A identificação automática pelo histórico usa horários aproximados.\n\n"
            "Deseja exportar mesmo assim?"):
            return
        folder = filedialog.askdirectory(title="Escolha a pasta de saída dos recortes")
        if not folder:
            return
        self.alert(f"Exportando {len(candidates)} mãos... você pode continuar usando o Windows.")
        def job():
            records = []
            for n, (index, c) in enumerate(candidates, 1):
                suffix = re.sub(r"[^A-Za-z0-9_\-]+", "_", c.hand_id or c.label)[:45]
                dest = Path(folder) / f"mao_{n:03}_perda_{c.loss_bb:.1f}BB_mesa{c.table}_{suffix}.mp4"
                try:
                    export_clip(self.videos, c, dest, ffmpeg)
                    status = "OK"
                except Exception as error:
                    status = "ERRO: " + str(error)[-250:]
                records.append({"arquivo": dest.name, "inicio_global": fmt(c.start),
                                "fim_global": fmt(c.end), "mesa": c.table,
                                "perda_bb": c.loss_bb, "conferida": c.confirmed,
                                "hand_id": c.hand_id, "status": status})
                self.after(0, lambda n=n, status=status: self.alert(
                    f"Processando {n}/{len(candidates)}: {status[:90]}"))
            with open(Path(folder) / "indice_das_maos.csv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(records[0].keys()), delimiter=";")
                writer.writeheader()
                writer.writerows(records)
            ok = sum(r["status"] == "OK" for r in records)
            self.after(0, lambda: messagebox.showinfo(
                "Exportação concluída", f"{ok} de {len(records)} vídeos exportados.\n"
                f"Relatório: {folder}/indice_das_maos.csv"))
            self.after(0, lambda: self.alert(f"Finalizado: {ok}/{len(records)} cortes. Pasta: {folder}"))
        threading.Thread(target=job, daemon=True).start()

    def close(self):
        try:
            self.preview_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.destroy()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
