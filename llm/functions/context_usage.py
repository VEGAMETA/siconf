"""
title: Расход контекста
description: После каждого ответа показывает строку состояния: сколько контекста занято (из 256K), сколько токенов в ответе, сколько он шёл и примерную скорость. Без внешних зависимостей: берёт usage из ответа llama.cpp.
author: local
version: 0.1.0
"""

import time

from pydantic import BaseModel, Field


def _k(n):
    """12345 -> «12,3K» (русская запятая)."""
    return f"{n / 1000:.1f}K".replace(".", ",") if n >= 1000 else str(n)


class Filter:
    class Valves(BaseModel):
        context_size: int = Field(default=262144, description="Размер контекста модели в токенах (пресет llama.cpp)")
        warn_percent: int = Field(default=75, description="С какого заполнения предупреждать, что скоро сработает сжатие беседы")

    def __init__(self):
        self.valves = self.Valves()
        self.started = {}  # message_id ответа -> время начала

    def inlet(self, body: dict, __metadata__: dict = None) -> dict:
        key = (__metadata__ or {}).get("message_id") or (__metadata__ or {}).get("chat_id")
        if key:
            self.started[key] = time.time()
            if len(self.started) > 500:
                self.started.clear()
        return body

    async def outlet(self, body: dict, __metadata__: dict = None, __event_emitter__=None) -> dict:
        if not __event_emitter__:
            return body
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "assistant"), None)
        usage = (last or {}).get("usage") or ((last or {}).get("info") or {}).get("usage") or {}
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
        completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
        if not (prompt or completion):
            return body
        used = prompt + completion
        percent = 100 * used / self.valves.context_size
        parts = [f"контекст {_k(used)} / {_k(self.valves.context_size)} ({percent:.1f} %)".replace(".", ","),
                 f"ответ {_k(completion)} ток."]
        key = (__metadata__ or {}).get("message_id") or (__metadata__ or {}).get("chat_id")
        started = self.started.pop(key, None) if key else None
        if started:
            seconds = time.time() - started
            parts.append(f"{seconds:.0f} с")
            if seconds > 0 and completion:
                # вместе с чтением промпта и вызовами инструментов, поэтому «≈»
                parts.append(f"≈{completion / seconds:.0f} ток/с")
        if percent >= self.valves.warn_percent:
            parts.append("скоро сжатие беседы")
        await __event_emitter__({"type": "status", "data": {"description": " · ".join(parts), "done": True}})
        return body
