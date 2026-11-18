# -*- coding: utf-8 -*-
"""Pasta padrao para os MP4 do Cortador PLO.

O destino escolhido pelo usuario fica no Windows, fora do ZIP do programa,
e nao contem credenciais nem dados das maos.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PREFERENCES_FILE = "preferencias.json"


def default_export_folder():
    """Pasta inicial mesmo na primeira execucao do programa."""
    return Path.home() / "Videos" / "Cortador PLO" / "Maos analisadas"


def preferences_path():
    root = os.environ.get("LOCALAPPDATA")
    base = Path(root) if root else Path.home() / ".local" / "share"
    return base / "CortadorPLO" / PREFERENCES_FILE


def valid_export_folder(value):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError("Escolha uma pasta de saida valida.")
    folder = Path(value).expanduser()
    if not folder.is_absolute():
        raise ValueError("Escolha o caminho absoluto de uma pasta.")
    if folder.exists() and not folder.is_dir():
        raise ValueError("O caminho escolhido e um arquivo, nao uma pasta.")
    return folder


def load_export_folder():
    """Recupera a escolha anterior; corrupcao nao impede abrir o aplicativo."""
    try:
        data = json.loads(preferences_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return valid_export_folder(data.get("export_folder"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return default_export_folder()


def save_export_folder(folder):
    """Salvamento atomico em LOCALAPPDATA; persiste entre atualizacoes."""
    chosen = valid_export_folder(folder)
    path = preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"export_folder": str(chosen)}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return chosen
