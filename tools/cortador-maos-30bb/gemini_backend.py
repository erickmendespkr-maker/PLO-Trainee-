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


def _context_jpeg(image: Image.Image):
    """Reduz trafego de muitas telas, preservando texto nas mesas e HUD."""
    pic = image.convert("RGB")
    width, height = pic.size
    if width < 460 and height < 420:
        factor = min(3, max(1, 720 // max(width, 1)))
        size = (width * factor, height * factor)
    else:
        factor = min(1.0, 1150 / max(width, 1), 1350 / max(height, 1))
        size = (max(1, round(width * factor)), max(1, round(height * factor)))
    if size != pic.size:
        pic = pic.resize(size, Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    pic.save(stream, format="JPEG", quality=88, optimize=True)
    return {"mime_type": "image/jpeg",
            "data": base64.b64encode(stream.getvalue()).decode("ascii")}


def _parse_response(message):
    if not isinstance(message, dict):
        return None
    candidates = message.get("candidates") or []
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
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
        self.last_pair_nick_verified = False

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
                  max_stack_bb=5000.0, expected_nick=None):
        self.last_pair_nick_verified = False
        if len(before_images) != 2 or len(after_images) != 2:
            return None
        parts = [{
            "text": (
                "Voce faz APENAS OCR literal de numeros de fichas/BB "
                "em quatro imagens do HUD VERDE COMPLETO de um jogador, "
                "na ordem: ANTES1, ANTES2, DEPOIS1, DEPOIS2. "
                "Em cada HUD aparecem CARTAS, NICK e SALDO (em BB). "
                "Encontre a linha do nick do heroi e LEIA O SALDO associado "
                "ao nick, geralmente imediatamente abaixo dele. "
                "Ignore numeros nas cartas, botees, pote e apostas. "
                + (f"O nick esperado e {expected_nick}. " if expected_nick else "") +
                "Leia cada imagem INDEPENDENTEMENTE. "
                "Nao calcule perdas. Nao adivinhe valores ausentes. "
                "Se o numero estiver ilegivel ou cortado, use null. "
                "Se houver mais de um saldo, use null. "
                "Preserve numeros e decimais, separador decimal como ponto. "
                "Responda SOMENTE JSON neste formato exato: "
                '{"before":[114.0,114.0],"after":[74.0,74.0],'
                '"nicks":["~Pulgar~","~Pulgar~","~Pulgar~","~Pulgar~"]}. '
                "Em nicks escreva o nick visto em cada imagem ou null. "
                "Use null para valores nao confiaveis."
            )
        }]
        for name, image in zip(("ANTES1", "ANTES2", "DEPOIS1", "DEPOIS2"),
                               [*before_images, *after_images]):
            parts.append({"text": name})
            parts.append({"inline_data": {
                "mime_type": "image/png", "data": _image_png(image)}})
        payload = self._request(parts)
        if isinstance(payload, dict) and expected_nick:
            names = payload.get("nicks")
            def norm(value):
                return re.sub(r"[^a-z0-9]", "", str(value).casefold())
            target = norm(expected_nick)
            self.last_pair_nick_verified = bool(
                target and isinstance(names, list) and len(names) == 4 and
                all(isinstance(name, str) and norm(name) == target
                    for name in names))
        return interpret_stack_response(payload, bb, max_stack_bb)

    def read_hand_context(self, overview, table_frames, hud_frames,
                          expected_nick, threshold=30):
        """Le mesa inteira ao longo da mao; nao apenas o stack do HUD.

        A perda fica inconclusiva se a contribuicao do heroi ou o destino
        do pote nao puderem ser confirmados em quadros visiveis.
        """
        from poker_contexto import validate_pot_result
        if len(table_frames) != 8 or len(hud_frames) != 2:
            raise GeminiError("A analise da mao exige 8 quadros da mesa e 2 HUDs.")
        prompt = (
            "Voce esta REVISANDO UMA GRAVACAO ENCERRADA de cash game PLO5. "
            "Sua tarefa e identificar uma mao PERDIDA por um jogador. "
            "Primeiro ha uma imagem da tela inteira para localizar a mesa; "
            "em seguida oito imagens DA MESMA MESA em ordem cronologica "
            "ao longo da mao e dois recortes do HUD do jogador. "
            "O heroi joga na posicao inferior da mesa. "
            f"Nick do heroi a encontrar VISUALMENTE: {expected_nick}. "
            "Veja as cartas privativas (5 cartas), cartas comunitarias, "
            "fichas apostas, pote total, vencedores e movimentacoes do pote. "
            "CRITERIO: quanto O PROPRIO HEROI INVESTIU NO POTE NESTA MAO, "
            "na unidade BB, e se a integralidade desse investimento foi "
            "PERDIDA porque outro jogador recebeu o pote. "
            "Um pote de 60BB NAO prova que o heroi investiu 60BB. "
            "O heroi pode jogar 40BB e recuperar parte do investimento em "
            "side pot: nesse caso hero_won_any_pot=true. "
            "O jogador usa REBUY AUTOMATICO e pode voltar a 100BB logo "
            "apos perder. Essa recarga NAO e um ganho nem prova perda, e "
            "NUNCA deve ser usada como stack inicial fixo de 100BB. "
            "So informe hero_invested_bb quando conseguir IDENTIFICAR "
            "o valor acumulado contribuido pelo heroi, por apostas/"
            "contribuicoes visiveis e fases da mao; caso contrario use null. "
            "So marque investment_visibly_verified=true quando o valor "
            "foi sustentado pelas imagens, nao estimado pelo pote total. "
            "Se nao conseguir ver a transferencia do pote PARA OUTRO "
            "JOGADOR, pot_awarded_to_opponent=null. "
            "Se nao conseguir identificar um vencedor com nome, "
            "winner_nick=null; nao invente. "
            "Se nao conseguir confirmar se o heroi ganhou um side pot, "
            "hero_won_any_pot=null, nao false. "
            "same_hand e hand_finished so devem ser true quando evidentes. "
            "Nao assuma informacoes que nao estao visiveis. "
            "Retorne APENAS JSON com exatamente estes campos: "
            '{"hero_nick":"~Pulgar~","same_hand":true,'
            '"hand_finished":true,"hero_invested_bb":40.0,'
            '"investment_visibly_verified":true,'
            '"pot_awarded_to_opponent":true,"winner_nick":"adversario",'
            '"hero_won_any_pot":false,"auto_rebuy_seen":true,'
            '"evidence":"jogador apostou 40 BB e o pote foi para adversario"}. '
            "Use null para quaisquer campos inseguros. "
        )
        parts = [{"text": prompt}, {"text": "VISÃO GERAL DA TELA DA GRAVACAO:"},
                 {"inline_data": {"mime_type": "image/png",
                                  "data": _context_jpeg(overview)["data"]}}]
        for i, image in enumerate(table_frames):
            parts.append({"text": f"MESA COMPLETA, MOMENTO {i+1}/8 EM ORDEM:"})
            parts.append({"inline_data": {
                "mime_type": "image/jpeg", "data": _context_jpeg(image)["data"]}})
        for i, image in enumerate(hud_frames):
            parts.append({"text": f"HUD DO HEROI, REFERENCIA {i+1}/2:"})
            parts.append({"inline_data": {
                "mime_type": "image/jpeg", "data": _context_jpeg(image)["data"]}})
        payload = self._request(parts, max_output=780)
        return validate_pot_result(payload, expected_nick, threshold=threshold)

    def read_hud_fields(self, image, bb=1.0, max_stack_bb=5000.0,
                        expected_nick=None):
        """Le NICK e SALDO do HUD completo na mesma chamada da API."""
        instructions = (
            "Analise um HUD de poker da parte inferior da mesa. "
            "A imagem inclui cartas do jogador, seu nick e seu saldo em BB. "
            "Identifique somente o nick do JOGADOR QUE RECEBEU AS CARTAS "
            "e o saldo mostrado junto a esse nick, geralmente logo abaixo. "
            "Ignore numeros das cartas, potes, botoes de acao e apostas. "
            "Nao adivinhe texto ilegivel: use null. "
        )
        if expected_nick:
            instructions += (
                f"O nick esperado e {expected_nick}. Se ele nao estiver visivel, "
                "use null para o nick e saldo. "
            )
        instructions += (
            'Responda somente JSON: {"nick":"~Pulgar~","value":125.7} '
            'ou {"nick":null,"value":null}.'
        )
        payload = self._request([
            {"text": instructions},
            {"inline_data": {
                "mime_type": "image/png", "data": _image_png(image)}},
        ])
        if not isinstance(payload, dict):
            return {"nick": None, "value": None}
        name = payload.get("nick")
        return {
            "nick": name.strip() if isinstance(name, str) and name.strip() else None,
            "value": normalize_amount(payload.get("value"), max_stack_bb * bb),
        }

    def read_single(self, image, bb=1.0, max_stack_bb=5000.0):
        """Compatibilidade com a tela antiga de teste de um saldo."""
        return self.read_hud_fields(
            image, bb=bb, max_stack_bb=max_stack_bb)["value"]

    def ping(self):
        """Teste minimo de credencial; conta como uma requisicao."""
        response = self._request([{
            "text": 'Responda apenas este JSON: {"status":"ok"}'
        }], max_output=64)
        return isinstance(response, dict) and response.get("status") == "ok"
