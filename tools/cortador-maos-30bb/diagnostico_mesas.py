# -*- coding: utf-8 -*-
"""Diagnostico offline do layout de mesas em uma gravacao, sem OCR/Tesseract.

Amostra 1 quadro a cada 5 segundos para localizar transicoes entre 1-4 mesas.
Nao analisa fichas nem classifica perdas: use o CSV para revisar o detector.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image

from analise_video import (W, H, AutoLayoutTracker, infer_horizontal_layout,
                           layout_bounds, layout_count, read_exact, table_visible)
from cortador import fmt, probe, resource

SAMPLE_SECONDS = 5


def diagnosticar(video_path, csv_path, on_progress=print):
    ffmpeg = resource("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg nao encontrado. Execute o instalador do programa.")
    video = probe(str(video_path))
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video_path),
               "-an", "-vf", f"fps=1/{SAMPLE_SECONDS},scale={W}:{H},format=gray",
               "-f", "rawvideo", "pipe:1"]
    output = Path(csv_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    tracker = AutoLayoutTracker()
    transitions = []
    frames = 0
    confirmed_frames = 0
    previous_mode = None
    columns = ["tempo_video_aproximado", "segundo_aproximado", "candidato",
               "modo_confirmado", "mesas_visiveis", "qtde_visivel_estimada",
               "estado", "pontuacao_candidato", "score_2", "score_3", "score_4"]
    proc = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        with output.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, delimiter=";")
            writer.writeheader()
            while True:
                packet = read_exact(proc.stdout, W * H)
                if len(packet) != W * H:
                    break
                frame = Image.frombytes("L", (W, H), packet)
                t = min(frames * SAMPLE_SECONDS, video.duration)
                candidate, score, scores = infer_horizontal_layout(frame, tracker.stable)
                confirmed_mode, safe, status = tracker.observe(
                    frame, observation=(candidate, score, scores))
                visible = []
                # O modo de grade fixa (4 posicoes) pode conter slots vazios.
                if confirmed_mode:
                    visible = [i for i in range(1, layout_count(confirmed_mode) + 1)
                               if table_visible(frame, layout_bounds(confirmed_mode, i),
                                                strict=False)]
                if safe and confirmed_mode:
                    confirmed_frames += 1
                    if confirmed_mode != previous_mode:
                        transitions.append((t, confirmed_mode, len(visible)))
                        previous_mode = confirmed_mode
                writer.writerow({
                    "tempo_video_aproximado": fmt(t),
                    "segundo_aproximado": round(t, 1),
                    "candidato": candidate or "INDEFINIDO",
                    "modo_confirmado": confirmed_mode or "INDEFINIDO",
                    "mesas_visiveis": ",".join(map(str, visible)) or "?",
                    "qtde_visivel_estimada": len(visible) if confirmed_mode else "?",
                    "estado": status if safe else "PENDENTE/" + status,
                    "pontuacao_candidato": round(score, 3),
                    "score_2": round(scores.get("horizontal2", 0.), 3),
                    "score_3": round(scores.get("horizontal3", 0.), 3),
                    "score_4": round(scores.get("horizontal4", 0.), 3),
                })
                frames += 1
                if frames % 12 == 0:
                    on_progress(f"Video ate {fmt(t)} de {fmt(video.duration)} analisado...")
        if proc.wait(timeout=30) != 0:
            raise RuntimeError("FFmpeg falhou ao ler o arquivo de video.")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        if proc.stdout:
            proc.stdout.close()

    summary = output.with_name(output.stem + "_mudancas.csv")
    with summary.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["tempo_video_aproximado", "segundo_aproximado",
                         "novo_layout", "quantidade_visivel_estimada"])
        for t, mode, count in transitions:
            writer.writerow([fmt(t), round(t, 1), mode, count])

    on_progress(f"Quadros examinados: {frames}; com layout confirmado: {confirmed_frames}.")
    on_progress(f"Diagnostico: {output}")
    on_progress(f"Mudancas: {summary}")
    return frames, confirmed_frames, summary


def main():
    root = tk.Tk()
    root.withdraw()
    video_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not video_path:
        selected = filedialog.askopenfilename(
            title="Escolha a gravacao completa de poker",
            filetypes=[("Video MP4", "*.mp4"), ("Videos", "*.mp4 *.mkv *.mov")])
        if not selected:
            return
        video_path = Path(selected)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video nao encontrado: {video_path}")

    selected = filedialog.asksaveasfilename(
        title="Salvar diagnostico das mesas",
        defaultextension=".csv",
        initialfile="diagnostico_mesas_" + video_path.stem + ".csv",
        filetypes=[("Planilha CSV", "*.csv")])
    if not selected:
        return
    rows, stable, transitions = diagnosticar(video_path, selected)
    messagebox.showinfo(
        "Diagnostico concluido",
        f"Quadros examinados: {rows}\n"
        f"Com layout confirmado: {stable}\n\n"
        f"CSV detalhado:\n{selected}\n\nMudancas:\n{transitions}\n\n"
        "Importante: as pontuacoes sao heuristicas, nao probabilidades. "
        "Confirme os horarios e layouts visualmente.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERRO:", exc, file=sys.stderr)
        try:
            messagebox.showerror("Diagnostico de mesas", str(exc))
        except Exception:
            pass
        raise
