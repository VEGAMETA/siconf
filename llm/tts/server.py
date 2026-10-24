"""Локальный сервер озвучки для Open WebUI: Piper (CPU), API в формате OpenAI /v1/audio/speech.

Запуск: D:\\llm\\tts\\.venv\\Scripts\\python.exe server.py  (слушает 127.0.0.1:5005)
Голоса: denis, dmitri, irina, ruslan (D:\\llm\\tts\\voices). Перед озвучкой текст очищается от
разметки, а числа переводятся в слова — сам Piper читает цифры плохо.
"""
import io
import re
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from num2words import num2words
from piper import PiperVoice, SynthesisConfig
from pydantic import BaseModel

VOICES_DIR = Path(__file__).parent / "voices"
VOICES = {p.name.split("-")[1]: p for p in VOICES_DIR.glob("ru_RU-*-medium.onnx")}
DEFAULT_VOICE = "dmitri"
_loaded: dict[str, PiperVoice] = {}

app = FastAPI(title="piper-openai")


class SpeechRequest(BaseModel):
    input: str
    model: str = "piper"
    voice: str = DEFAULT_VOICE
    response_format: str = "wav"
    speed: float = 1.0


def _voice(name: str) -> PiperVoice:
    name = name if name in VOICES else DEFAULT_VOICE  # «alloy» и прочие голоса OpenAI → голос по умолчанию
    if name not in _loaded:
        _loaded[name] = PiperVoice.load(VOICES[name])
    return _loaded[name]


def _number(match: re.Match) -> str:
    raw = match.group(0).replace("\u00a0", "").replace("\u202f", "").replace(" ", "")
    try:
        if "." in raw:  # \u0447\u0435\u0440\u0435\u0437 \u0442\u043e\u0447\u043a\u0443 \u0432 \u0440\u0443\u0441\u0441\u043a\u043e\u043c \u0442\u0435\u043a\u0441\u0442\u0435 \u043f\u0438\u0448\u0443\u0442 \u0432\u0435\u0440\u0441\u0438\u0438: 3.12 \u2192 \u00ab\u0442\u0440\u0438 \u0442\u043e\u0447\u043a\u0430 \u0434\u0432\u0435\u043d\u0430\u0434\u0446\u0430\u0442\u044c\u00bb
            return " " + " \u0442\u043e\u0447\u043a\u0430 ".join(num2words(int(p), lang="ru") for p in raw.split(".")) + " "
        if "," in raw:  # 82,6 \u2192 \u0434\u0440\u043e\u0431\u044c
            return " " + num2words(float(raw.replace(",", ".")), lang="ru") + " "
        return " " + num2words(int(raw), lang="ru") + " "
    except (ValueError, OverflowError, NotImplementedError):
        return raw


def normalize(text: str) -> str:
    """Убирает то, что не надо читать вслух, и превращает числа в слова."""
    text = re.sub(r"```.*?```", " (фрагмент кода пропущен) ", text, flags=re.S)
    text = re.sub(r"\$\$.*?\$\$", " (формула) ", text, flags=re.S)
    text = re.sub(r"\$[^$\n]{1,200}\$", " (формула) ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # картинки
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)  # ссылки → текст ссылки
    text = re.sub(r"https?://\S+", " ссылка ", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)  # заголовки
    text = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", text, flags=re.M)  # маркеры списков
    text = re.sub(r"^\s*\|?[-:| ]{3,}\|?\s*$", " ", text, flags=re.M)  # разделители таблиц
    text = text.replace("|", ", ")
    text = re.sub(r"[*_~>#]+", " ", text)
    text = text.replace("%", " процентов ").replace("±", " плюс-минус ").replace("×", " на ")
    text = re.sub(r"(?<=\d)\s*[–—]\s*(?=\d)", " — ", text)  # 15–25 → пауза между числами
    # 128 000 / 82,6 / 3.12 / 2.5.1 → словами; числа, слитые с буквами (b11852, 26B, RTX4060), не трогаем
    text = re.sub(r"(?<![\d.,])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![\d])|(?<![\w.,])\d+(?:\.\d+)+(?![\w])|(?<![\w.,])\d+(?:,\d+)?(?![\w.])", _number, text)
    text = re.sub(r"\s+", " ", text)
    # пробел перед знаком препинания («пять .») Piper понимает как конец текста и обрывает фразу
    return re.sub(r"\s+([.,!?;:…])", r"\1", text).strip()


@app.post("/v1/audio/speech")
def speech(req: SpeechRequest):
    text = normalize(req.input)
    if not text:
        return Response(status_code=400, content="empty input")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        _voice(req.voice).synthesize_wav(text, wav, syn_config=SynthesisConfig(length_scale=1.0 / max(0.25, min(req.speed, 4.0))))
    return Response(content=buf.getvalue(), media_type="audio/wav")


@app.get("/v1/models")
def models():
    return {"data": [{"id": "piper", "object": "model"}]}


@app.get("/v1/audio/voices")
def voices():
    return JSONResponse({"voices": [{"id": v, "name": v} for v in sorted(VOICES)]})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5005, log_level="warning")
