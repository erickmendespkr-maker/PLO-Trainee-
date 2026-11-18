# -*- coding: utf-8 -*-
"""Backend opcional de visao Gemini para recortes de saldo de sessoes encerradas.

Sem chave embutida no codigo. No Windows, a chave configurada na interface fica
criptografada com DPAPI no perfil do usuario. O video completo nunca e enviado.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import io
import json
import math
import os
from pathlib import Path
import re
import statistics
import urllib.error
import urllib.request

from PIL import Image, ImageOps

DEFAULT_MODEL = "gemini-3.5-flash-lite"
ALLOWED_MODELS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
)
MAX_REQUESTS_PER_ANALYSIS = 40
API_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/"
SECURE_FILE_NAME = "gemini_credencial.dpapi"


class GeminiError(Exception):
    """Erro sem vazar dados da credencial."""


class GeminiLimitError(GeminiError):
    """Cota local esgotada ou erro permanente no servico."""


class _Blob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _protect_bytes(raw: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise GeminiError("O armazenamento protegido requer Windows.")
    input_buffer = ctypes.create_string_buffer(raw, len(raw))
    input_blob = _Blob(len(raw), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte)))
    output_blob = _Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    operation.restype = wintypes.BOOL
    if decrypt:
        operation.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p,
                              ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                              wintypes.DWORD, ctypes.POINTER(_Blob)]
        args = (ctypes.byref(input_blob), None, None, None, None, 1,
                ctypes.byref(output_blob))
    else:
        operation.argtypes = [ctypes.POINTER(_Blob), ctypes.c_wchar_p,
                              ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                              wintypes.DWORD, ctypes.POINTER(_Blob)]
        args = (ctypes.byref(input_blob), "CortadorPLO Gemini", None, None, None, 1,
                ctypes.byref(output_blob))
    if not operation(*args):
        raise GeminiError("O Windows nao conseguiu proteger ou ler a credencial.")
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(output_blob.pbData, ctypes.c_void_p))


def key_file_path():
    base = os.getenv("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "CortadorPLO" / SECURE_FILE_NAME


def save_key(key: str) -> None:
    key = key.strip()
    if not key or len(key) < 15 or "\n" in key or "\r" in key:
        raise GeminiError("A chave informada parece incompleta.")
    encrypted = _protect_bytes(key.encode("utf-8"))
    dest = key_file_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        temp.write_bytes(encrypted)
        os.replace(temp, dest)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def read_key() -> str | None:
    env = os.getenv("GEMINI_API_KEY", "").strip()
    if env:
        return env
    file = key_file_path()
    if not file.is_file():
        return None
    try:
        return _protect_bytes(file.read_bytes(), decrypt=True).decode("utf-8").strip()
    except (UnicodeError, OSError, GeminiError):
        return None


def remove_key():
    key_file_path().unlink(missing_ok=True)


def normalize_amount(value, max_stack=5000.0):
    """Parse estrito de numero, nunca extrai digitos de uma frase."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        text = value.strip().replace(",", ".")
        if not re.fullmatch(r"\d+(?:\.\d{1,3})?", text):
            return None
        number = float(text)
    elif isinstance(value, (float, int)):
        number = float(value)
    else:
        return None
    return number if math.isfinite(number) and 0 <= number <= max_stack else None


def stable_pair(values, bb=1.0, max_stack_bb=5000.0):
    """Requer dois QUADROS independentes com valores proximos."""
    if not isinstance(values, list) or len(values) != 2 or bb <= 0:
        return None
    amounts = [normalize_amount(x, max_stack=max_stack_bb * bb) for x in values]
    if any(x is None for x in amounts):
        return None
    left, right = amounts
    if abs(left - right) > max(bb * 0.6, max(left, right) * .008):
        return None
    return statistics.median(amounts)


def interpret_stack_response(payload, bb=1.0, max_stack_bb=5000.0):
    """So devolve saldos quando 2 frames antes e 2 depois concordam."""
    if not isinstance(payload, dict):
        return None
    pre = stable_pair(payload.get("before"), bb, max_stack_bb)
    post = stable_pair(payload.get("after"), bb, max_stack_bb)
    if pre is None or post is None:
        return None
    # Usar valores em fichas; o cliente do poker pode exibir saldos em BB.
    return pre, post


def _image_png(image: Image.Image):
    picture = image.convert("RGB")
    factor = min(6, max(2, round(360 / max(picture.width, 1))))
    upscaled = picture.resize(
        (picture.width * factor, picture.height * factor),
        Image.Resampling.LANCZOS)
    framed = ImageOps.expand(upscaled, border=16, fill="white")
    stream = io.BytesIO()
    framed.save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _parse_response(message):
    if not isinstance(message, dict):
        return None
    parts = message.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
    if not texts:
        return None
    try:
        return json.loads("".join(texts))
    except (ValueError, TypeError):
        return None


class GeminiClient:
    """Backend REST com limite firme de requisicoes por analise."""
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL,
                 max_requests: int = MAX_REQUESTS_PER_ANALYSIS, transport=None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise GeminiError("Chave Gemini nao configurada.")
        if model not in ALLOWED_MODELS:
            raise GeminiError("Modelo Gemini nao permitido.")
        if not 1 <= int(max_requests) <= 300:
            raise GeminiError("Limite de chamadas deve estar entre 1 e 300.")
        self._key = api_key.strip()
        self.model = model
        self.limit = int(max_requests)
        self.used = 0
        self.disabled_reason = None
        self._transport = transport or urllib.request.urlopen

    def _request(self, parts, max_output=256):
        if self.disabled_reason is not None:
            raise GeminiLimitError(self.disabled_reason)
        if self.used >= self.limit:
            self.disabled_reason = "Limite local de chamadas Gemini atingido."
            raise GeminiLimitError(self.disabled_reason)
        self.used += 1  # reservar ANTES de enviar para evitar loops ilimitados
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0,
                "maxOutputTokens": max_output
            }
        }
        request = urllib.request.Request(
            API_ENDPOINT + self.model + ":generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._key
            },
            method="POST",
        )
        try:
            with self._transport(request, timeout=45) as result:
                response = json.loads(result.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Nunca incluir URL, headers, body ou chave em mensagens.
            if exc.code in (400, 401, 403, 404, 429):
                self.disabled_reason = f"Gemini HTTP {exc.code}: reveja modelo, chave ou cota."
                raise GeminiLimitError(self.disabled_reason) from None
            raise GeminiError(f"Gemini HTTP {exc.code}.") from None
        except (TimeoutError, OSError, ValueError) as exc:
            raise GeminiError("Falha de conexao ou resposta invalida da API Gemini.") from None
        return _parse_response(response)

    def read_pair(self, before_images, after_images, bb=1.0,
                  max_stack_bb=5000.0):
        if len(before_images) != 2 or len(after_images) != 2:
            return None
        parts = [{
            "text": (
                "Voce faz APENAS OCR literal de numeros de fichas/BB "
                "em quatro recortes de tela de poker, na ordem: "
                "ANTES1, ANTES2, DEPOIS1, DEPOIS2. "
                "Cada imagem mostra a regiao do saldo de um unico jogador. "
                "Leia cada imagem INDEPENDENTEMENTE. "
                "Nao calcule perdas. Nao adivinhe valores ausentes. "
                "Se o numero estiver ilegivel ou cortado, use null. "
                "Se houver mais de um saldo, use null. "
                "Preserve numeros e decimais, separador decimal como ponto. "
                "Responda SOMENTE JSON neste formato exato: "
                '{"before":[114.0,114.0],"after":[74.0,74.0]}. '
                "Use null para valores nao confiaveis."
            )
        }]
        for name, image in zip(("ANTES1", "ANTES2", "DEPOIS1", "DEPOIS2"),
                               [*before_images, *after_images]):
            parts.append({"text": name})
            parts.append({"inline_data": {
                "mime_type": "image/png", "data": _image_png(image)}})
        payload = self._request(parts)
        return interpret_stack_response(payload, bb, max_stack_bb)

    def ping(self):
        """Teste minimo de credencial; conta como uma requisicao."""
        response = self._request([{
            "text": 'Responda apenas este JSON: {"status":"ok"}'
        }], max_output=64)
        return isinstance(response, dict) and response.get("status") == "ok"
