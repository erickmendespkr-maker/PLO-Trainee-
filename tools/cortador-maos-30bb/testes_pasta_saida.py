# -*- coding: utf-8 -*-
"""Testes de persistencia da pasta de videos, sem alterar arquivos do usuario."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pasta_saida import (
    default_export_folder, load_export_folder, preferences_path,
    save_export_folder, valid_export_folder,
)


class OutputFolderTests(unittest.TestCase):
    def test_pasta_padrao_sem_configuracao(self):
        with tempfile.TemporaryDirectory() as temp:
            userhome = Path(temp) / "usuario"
            local = Path(temp) / "appdata"
            with patch("pasta_saida.Path.home", return_value=userhome), \
                 patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
                self.assertEqual(
                    load_export_folder(),
                    userhome / "Videos" / "Cortador PLO" / "Maos analisadas")
                self.assertFalse(preferences_path().is_file())

    def test_escolha_persiste_apos_reabrir_programa(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "AppData"
            dest = Path(temp) / "Minhas maos para treinador"
            dest.mkdir()
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
                self.assertEqual(save_export_folder(dest), dest)
                self.assertEqual(load_export_folder(), dest)
                self.assertEqual(
                    json.loads(preferences_path().read_text(encoding="utf-8")),
                    {"export_folder": str(dest)})
                self.assertEqual(preferences_path().parent.name, "CortadorPLO")
                self.assertFalse(preferences_path().with_suffix(".json.tmp").exists())

    def test_alterar_pasta_substitui_preferencia_anterior(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "primeira"
            next_folder = Path(temp) / "segunda"
            with patch.dict(os.environ, {"LOCALAPPDATA": str(Path(temp) / "Local")}):
                save_export_folder(first)
                self.assertEqual(load_export_folder(), first)
                save_export_folder(next_folder)
                self.assertEqual(load_export_folder(), next_folder)

    def test_arquivo_corrompido_retorna_pasta_padrao(self):
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "Local"
            with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
                file = preferences_path()
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("{invalid", encoding="utf-8")
                self.assertEqual(load_export_folder(), default_export_folder())

    def test_nao_aceitar_arquivo_como_pasta_ou_caminho_vazio(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "existe.txt"
            file.write_text("arquivo", encoding="utf-8")
            with self.assertRaises(ValueError):
                valid_export_folder(file)
            with self.assertRaises(ValueError):
                valid_export_folder(" ")


if __name__ == "__main__":
    unittest.main()
